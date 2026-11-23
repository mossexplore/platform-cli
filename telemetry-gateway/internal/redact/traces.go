package redact

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"regexp"
	"strconv"
	"strings"

	"github.com/mossexplore/platform-cli/telemetry-gateway/internal/config"
)

type Document struct {
	Resources []ResourceSpans `json:"resourceSpans"`
}

type ResourceSpans struct {
	Resource struct {
		Attributes []Attribute `json:"attributes,omitempty"`
	} `json:"resource"`
	Scopes []struct {
		Scope struct {
			Name    string `json:"name,omitempty"`
			Version string `json:"version,omitempty"`
		} `json:"scope"`
		Spans []Span `json:"spans"`
	} `json:"scopeSpans"`
}

type Span struct {
	TraceID  string       `json:"traceId"`
	SpanID   string       `json:"spanId"`
	ParentID string       `json:"parentSpanId,omitempty"`
	Name     string       `json:"name"`
	Kind     int          `json:"kind,omitempty"`
	Start    uint64String `json:"startTimeUnixNano"`
	End      uint64String `json:"endTimeUnixNano"`
	Status   *struct {
		Code int `json:"code"`
	} `json:"status,omitempty"`
	Attributes []Attribute `json:"attributes,omitempty"`
}

type uint64String uint64

func (n *uint64String) UnmarshalJSON(raw []byte) error {
	if len(raw) >= 2 && raw[0] == '"' {
		raw = raw[1 : len(raw)-1]
	}
	value, err := strconv.ParseUint(string(raw), 10, 64)
	*n = uint64String(value)
	return err
}

func (n uint64String) MarshalJSON() ([]byte, error) {
	return strconv.AppendQuote(nil, strconv.FormatUint(uint64(n), 10)), nil
}

type Attribute struct {
	Key   string `json:"key"`
	Value struct {
		Text    *string      `json:"stringValue,omitempty"`
		Integer *int64String `json:"intValue,omitempty"`
	} `json:"value"`
}

type int64String int64

func (n *int64String) UnmarshalJSON(raw []byte) error {
	if len(raw) >= 2 && raw[0] == '"' {
		raw = raw[1 : len(raw)-1]
	}
	value, err := strconv.ParseInt(string(raw), 10, 64)
	*n = int64String(value)
	return err
}

func (n int64String) MarshalJSON() ([]byte, error) {
	return strconv.AppendQuote(nil, strconv.FormatInt(int64(n), 10)), nil
}

var (
	validHex     = regexp.MustCompile(`^[a-fA-F0-9]+$`)
	validTextKey = regexp.MustCompile(`^(?:service\.(?:name|version)|os\.type|langfuse\.(?:user\.id|session\.id|environment|trace\.metadata\.wiserec_(?:business_id|cli_version)|observation\.(?:type|input|output|metadata\.(?:turn_reason|tool_name|tool_status)))|gen_ai\.(?:operation\.name|request\.model|provider\.name))$`)
	validIntKey  = regexp.MustCompile(`^(?:langfuse\.observation\.metadata\.(?:tool_exit_code|tool_duration_ms)|gen_ai\.usage\.(?:input_tokens|output_tokens|cache_read\.input_tokens|cache_creation\.input_tokens))$`)
)

func validID(id string, length int) bool {
	return len(id) == length && validHex.MatchString(id) && len(bytes.Trim([]byte(id), "0")) != 0
}

func attributes(raw []Attribute, allowContent bool) []Attribute {
	accepted := raw[:0]
	seen := make(map[string]bool)
	for _, entry := range raw {
		if !allowContent && (entry.Key == "langfuse.observation.input" || entry.Key == "langfuse.observation.output") {
			continue
		}
		if seen[entry.Key] {
			continue
		}
		switch {
		case validTextKey.MatchString(entry.Key) && entry.Value.Text != nil && entry.Value.Integer == nil:
			if len(*entry.Value.Text) > 128<<10 {
				continue
			}
			safe := Text(*entry.Value.Text)
			entry.Value.Text = &safe
		case validIntKey.MatchString(entry.Key) && entry.Value.Integer != nil && entry.Value.Text == nil:
		default:
			continue
		}
		seen[entry.Key] = true
		accepted = append(accepted, entry)
	}
	return accepted
}

type Counts struct {
	Received, Filtered int
}

func spanEnvironment(attrs []Attribute) string {
	name := ""
	found := false
	for _, attr := range attrs {
		if attr.Key != "langfuse.environment" {
			continue
		}
		if found || attr.Value.Text == nil || attr.Value.Integer != nil {
			return ""
		}
		found, name = true, config.NormalizeEnvironment(*attr.Value.Text)
	}
	return name
}

func Traces(payload []byte, allowed, content config.EnvironmentSet) ([]byte, Counts, error) {
	var doc Document
	var counts Counts
	decoder := json.NewDecoder(bytes.NewReader(payload))
	if err := decoder.Decode(&doc); err != nil || doc.Resources == nil ||
		decoder.Decode(new(json.RawMessage)) != io.EOF {
		return nil, counts, errors.New("invalid OTLP request")
	}

	environments := make(map[string]string)
	for i := range doc.Resources {
		resource := &doc.Resources[i]
		if len(resource.Scopes) == 0 {
			return nil, Counts{}, errors.New("missing OTLP scope")
		}
		for j := range resource.Scopes {
			scope := &resource.Scopes[j]
			if len(scope.Spans) == 0 {
				return nil, Counts{}, errors.New("missing OTLP spans")
			}
			for k := range scope.Spans {
				span := &scope.Spans[k]
				counts.Received++
				if counts.Received > 4096 || !validID(span.TraceID, 32) || !validID(span.SpanID, 16) ||
					(span.ParentID != "" && !validID(span.ParentID, 16)) ||
					span.Start == 0 || span.End < span.Start || len(span.Name) == 0 || len(span.Name) > 256 ||
					span.Kind < 0 || span.Kind > 5 || (span.Status != nil && (span.Status.Code < 0 || span.Status.Code > 2)) {
					return nil, Counts{}, errors.New("invalid OTLP span")
				}
				key := strings.ToLower(span.TraceID)
				env := spanEnvironment(span.Attributes)
				if previous, seen := environments[key]; seen && previous != env {
					env = ""
				}
				environments[key] = env
			}
		}
	}
	// Decide for the whole trace in the batch before forwarding any of its spans.
	resources := doc.Resources[:0]
	for _, resource := range doc.Resources {
		scopes := resource.Scopes[:0]
		for _, scope := range resource.Scopes {
			spans := scope.Spans[:0]
			for _, span := range scope.Spans {
				env := environments[strings.ToLower(span.TraceID)]
				if !allowed.Allows(env) {
					counts.Filtered++
					continue
				}
				span.Name = Text(span.Name)
				span.Attributes = attributes(span.Attributes, env != "" && content.Allows(env))
				spans = append(spans, span)
			}
			if len(spans) > 0 {
				scope.Scope.Name = Text(scope.Scope.Name)
				scope.Scope.Version = Text(scope.Scope.Version)
				scope.Spans = spans
				scopes = append(scopes, scope)
			}
		}
		if len(scopes) > 0 {
			resource.Resource.Attributes = attributes(resource.Resource.Attributes, false)
			resource.Scopes = scopes
			resources = append(resources, resource)
		}
	}
	if len(resources) == 0 {
		return nil, counts, nil
	}
	doc.Resources = resources
	clean, err := json.Marshal(doc)
	return clean, counts, err
}
