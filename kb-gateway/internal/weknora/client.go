package weknora

import (
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode"
	"unicode/utf8"
)

type Client struct {
	Base, Key  string
	Visibility Visibility
	HTTP       *http.Client
	MaxBytes   int64
	Preview    int
}
type Failure struct {
	Status int
	Code   string
}

func (f Failure) Error() string { return f.Code }

var upstream = Failure{502, "UPSTREAM_FAILURE"}
var invalid = Failure{400, "INVALID_PARAMETERS"}

type obj = map[string]any
type page struct {
	Slug    string
	Title   string
	Summary string
	Content string
	Status  string
	Refs    []string `json:"source_refs"`
	Updated string   `json:"updated_at"`
}
type library struct {
	ID, Name, Description string
	Updated               string `json:"updated_at"`
	Strategy              struct {
		Wiki bool `json:"wiki_enabled"`
	} `json:"indexing_strategy"`
}

func (c *Client) get(ctx context.Context, path string, q url.Values, out any) error {
	req, e := http.NewRequestWithContext(ctx, "GET", c.Base+"/api/v1/"+path, nil)
	if e != nil {
		return upstream
	}
	req.URL.RawQuery = q.Encode()
	req.Header.Set("X-API-Key", c.Key)
	resp, e := c.HTTP.Do(req)
	if e != nil {
		return upstream
	}
	defer resp.Body.Close()
	if resp.StatusCode == 404 {
		return Failure{404, "NOT_FOUND"}
	}
	if resp.StatusCode != 200 {
		return upstream
	}
	data, e := io.ReadAll(io.LimitReader(resp.Body, c.MaxBytes+1))
	if e != nil {
		return upstream
	}
	if int64(len(data)) > c.MaxBytes {
		return Failure{502, "UPSTREAM_RESPONSE_TOO_LARGE"}
	}
	if json.Unmarshal(data, out) != nil {
		return upstream
	}
	return nil
}

var zone = time.FixedZone("UTC+8", 8*3600)

func stamp(raw string) string {
	v, e := time.Parse(time.RFC3339Nano, raw)
	if e != nil {
		return ""
	}
	return v.In(zone).Format(time.DateTime)
}
func number(q url.Values, k string, fallback, maxValue int) (int, error) {
	if !q.Has(k) {
		return fallback, nil
	}
	n, e := strconv.Atoi(q.Get(k))
	if e != nil || n < 1 || n > maxValue {
		return 0, invalid
	}
	return n, nil
}
func slugPath(raw string) (string, error) {
	if raw == "" || !utf8.ValidString(raw) || utf8.RuneCountInString(raw) > 255 {
		return "", invalid
	}
	parts := strings.Split(raw, "/")
	for i, p := range parts {
		if p == "" || p == "." || p == ".." || strings.ContainsAny(p, "\\%") || strings.IndexFunc(p, unicode.IsControl) >= 0 {
			return "", invalid
		}
		parts[i] = url.PathEscape(p)
	}
	return strings.Join(parts, "/"), nil
}
func summary(p page) obj {
	return obj{"slug": p.Slug, "title": p.Title, "summary": p.Summary, "updated_at": stamp(p.Updated)}
}
func (c *Client) Read(ctx context.Context, action, env, user string, q url.Values) (obj, error) {
	var list struct{ Data *[]library }
	if e := c.get(ctx, "knowledge-bases", nil, &list); e != nil {
		return nil, e
	}
	if list.Data == nil {
		return nil, upstream
	}
	items := []obj{}
	visible := []library{}
	for _, k := range *list.Data {
		if c.Visibility.allows(k.ID, env, user) && k.Strategy.Wiki {
			visible = append(visible, k)
			items = append(items, obj{"id": k.ID, "name": k.Name, "description": k.Description, "updated_at": stamp(k.Updated)})
		}
	}
	if action == "kb_list" {
		return obj{"items": items}, nil
	}
	target := q.Get("kb")
	var matches []library
	for _, k := range visible {
		if target == k.ID {
			matches = []library{k}
			break
		}
		if target == "" || target == k.Name {
			matches = append(matches, k)
		}
	}
	if len(matches) == 0 {
		return nil, Failure{404, "KB_NOT_FOUND"}
	}
	if len(matches) > 1 {
		candidates := make([]obj, 0, len(matches))
		for _, match := range matches {
			candidates = append(candidates, obj{"name": match.Name, "id": match.ID})
		}
		return obj{"candidates": candidates}, Failure{400, "AMBIGUOUS_KB_USE_ID"}
	}
	k := matches[0]
	base := "knowledgebase/" + url.PathEscape(k.ID) + "/wiki/"
	result := obj{"kb_id": k.ID, "kb_name": k.Name}
	switch action {
	case "kb_page_show":
		slug, e := slugPath(q.Get("slug"))
		if e != nil {
			return nil, e
		}
		var p page
		if e = c.get(ctx, base+"pages/"+slug, nil, &p); e != nil {
			return nil, e
		}
		if p.Status != "published" || p.Slug != q.Get("slug") {
			return nil, Failure{404, "NOT_FOUND"}
		}
		result["slug"] = p.Slug
		result["title"] = p.Title
		result["updated_at"] = stamp(p.Updated)
		if p.Refs == nil {
			p.Refs = []string{}
		}
		result["source_refs"] = p.Refs
		result["content_bytes"] = len(p.Content)
		result["truncated"] = len(p.Content) > c.Preview
		if len(p.Content) > c.Preview {
			n := c.Preview
			for n > 0 && !utf8.RuneStart(p.Content[n]) {
				n--
			}
			p.Content = p.Content[:n]
		}
		result["content"] = p.Content
	case "kb_page_list", "kb_search":
		var data struct {
			Pages json.RawMessage
			Total int
		}
		params := url.Values{}
		route := "pages"
		limit := 0
		window := 0
		if action == "kb_search" {
			route = "search"
			query := strings.TrimSpace(q.Get("q"))
			if query == "" || utf8.RuneCountInString(query) > 512 {
				return nil, invalid
			}
			var e error
			limit, e = number(q, "limit", 5, 20)
			if e != nil {
				return nil, e
			}
			window = min(limit*3, 50)
			params.Set("limit", strconv.Itoa(window))
			params.Set("q", regexp.QuoteMeta(query))
			result["query"] = query
			result["limit"] = limit
		} else {
			n, e := number(q, "page", 1, 1<<30)
			if e != nil {
				return nil, e
			}
			size, e := number(q, "page_size", 20, 50)
			if e != nil {
				return nil, e
			}
			params.Set("page", strconv.Itoa(n))
			params.Set("page_size", strconv.Itoa(size))
			params.Set("status", "published")
			result["page"] = n
			result["page_size"] = size
		}
		if e := c.get(ctx, base+route, params, &data); e != nil {
			return nil, e
		}
		var pages []page
		if len(data.Pages) == 0 || json.Unmarshal(data.Pages, &pages) != nil {
			return nil, upstream
		}
		rows := []obj{}
		for _, p := range pages {
			if p.Status == "published" {
				rows = append(rows, summary(p))
				if limit > 0 && len(rows) == limit {
					break
				}
			}
		}
		result["items"] = rows
		if limit > 0 {
			result["candidate_window_exhausted"] = len(pages) >= window && len(rows) < limit
		} else {
			result["total"] = data.Total
		}
	default:
		return nil, errors.New("unknown KB action")
	}
	return result, nil
}
