package redact

import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"regexp"
	"strconv"
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

func attributes(raw []Attribute) []Attribute {
	accepted := raw[:0]
	seen := make(map[string]bool)
	for _, entry := range raw {
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

func Traces(payload []byte) ([]byte, int, error) {
	var doc Document
	decoder := json.NewDecoder(bytes.NewReader(payload))
	if err := decoder.Decode(&doc); err != nil || doc.Resources == nil ||
		decoder.Decode(new(json.RawMessage)) != io.EOF {
		return nil, 0, errors.New("invalid OTLP request")
	}

	count := 0
	for i := range doc.Resources {
		resource := &doc.Resources[i]
		resource.Resource.Attributes = attributes(resource.Resource.Attributes)
		if len(resource.Scopes) == 0 {
			return nil, 0, errors.New("missing OTLP scope")
		}
		for j := range resource.Scopes {
			scope := &resource.Scopes[j]
			scope.Scope.Name = Text(scope.Scope.Name)
			scope.Scope.Version = Text(scope.Scope.Version)
			if len(scope.Spans) == 0 {
				return nil, 0, errors.New("missing OTLP spans")
			}
			for k := range scope.Spans {
				span := &scope.Spans[k]
				count++
				if count > 4096 || !validID(span.TraceID, 32) || !validID(span.SpanID, 16) ||
					(span.ParentID != "" && !validID(span.ParentID, 16)) ||
					span.Start == 0 || span.End < span.Start || len(span.Name) == 0 || len(span.Name) > 256 ||
					span.Kind < 0 || span.Kind > 5 || (span.Status != nil && (span.Status.Code < 0 || span.Status.Code > 2)) {
					return nil, 0, errors.New("invalid OTLP span")
				}
				span.Name = Text(span.Name)
				span.Attributes = attributes(span.Attributes)
			}
		}
	}
	if count == 0 {
		return nil, 0, nil
	}
	clean, err := json.Marshal(doc)
	return clean, count, err
}
