package server

import (
	"encoding/json"
	"errors"
	"net/http"
	"net/netip"
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"time"

	"github.com/mossexplore/platform-cli/kb-gateway/internal/auth"
	"github.com/mossexplore/platform-cli/kb-gateway/internal/weknora"
)

type Server struct {
	Client         *weknora.Client
	Keys           map[string]string
	Networks       []netip.Prefix
	TrustedProxies []netip.Prefix
	Dir            string
	rate           limiter
	mu             sync.Mutex
	slots          chan struct{}
}

func New(c *weknora.Client, keys map[string]string, nets []netip.Prefix, dir string, rate, burst int) *Server {
	return &Server{Client: c, Keys: keys, Networks: nets, Dir: dir, rate: limiter{rate: float64(rate), burst: float64(burst), buckets: map[netip.Addr]bucket{}}, slots: make(chan struct{}, 16)}
}

var auditZone = time.FixedZone("UTC+8", 28800)

var routes = map[string]string{"/v1/kb/list": "kb_list", "/v1/kb/pages": "kb_page_list", "/v1/kb/page": "kb_page_show", "/v1/kb/search": "kb_search"}
var sensitive = regexp.MustCompile("(?i)cookie|csrf|authorization|token|password|secret|api[-_ ]?key|密钥|密码")

func redact(s string) string {
	if i := sensitive.FindStringIndex(s); i != nil {
		s = s[:i[0]] + "[已脱敏]"
	}
	r := []rune(s)
	return string(r[:min(256, len(r))])
}
func reply(w http.ResponseWriter, status int, v any) {
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}
func (s *Server) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("Cache-Control", "no-store")
	if r.Method != "GET" {
		reply(w, 405, map[string]string{"code": "METHOD_NOT_ALLOWED"})
		return
	}
	path := r.URL.EscapedPath()
	if path == "/health" {
		reply(w, 200, map[string]string{"status": "ok"})
		return
	}
	action, ok := routes[path]
	if !ok {
		reply(w, 404, map[string]string{"code": "NOT_FOUND"})
		return
	}
	peer, e := netip.ParseAddrPort(r.RemoteAddr)
	ip := peer.Addr().Unmap()
	if e != nil || !containsIP(s.Networks, ip) {
		s.deny(w, 403, "SOURCE_DENIED", action, ip, auth.Identity{})
		return
	}
	if containsIP(s.TrustedProxies, ip) {
		if values := r.Header.Values("X-Real-IP"); len(values) > 0 {
			forwarded, err := netip.ParseAddr(values[0])
			if len(values) != 1 || err != nil || forwarded.Zone() != "" {
				reply(w, 400, map[string]string{"code": "INVALID_CLIENT_IP"})
				return
			}
			ip = forwarded.Unmap()
		}
	}
	start := time.Now()
	if !s.rate.allow(ip, start) {
		reply(w, 429, map[string]string{"code": "RATE_LIMITED"})
		return
	}
	id, ok := auth.Verify(r.Header, s.Keys, start)
	if !ok {
		s.deny(w, 401, "INVALID_TICKET", action, ip, auth.Identity{})
		return
	}
	if action != id.Action {
		s.deny(w, 403, "ACTION_DENIED", action, ip, id)
		return
	}
	select {
	case s.slots <- struct{}{}:
		defer func() { <-s.slots }()
	default:
		reply(w, 503, map[string]string{"code": "BUSY"})
		return
	}
	q := r.URL.Query()
	data, e := s.Client.Read(r.Context(), action, id.Env, id.User, q)
	status := 200
	if e != nil {
		var f weknora.Failure
		if !errors.As(e, &f) {
			f = weknora.Failure{Status: 502, Code: "UPSTREAM_FAILURE"}
		}
		status = f.Status
		if data == nil {
			data = map[string]any{}
		}
		data["code"] = f.Code
	}
	hits := 0
	if rows, ok := data["items"].([]map[string]any); ok {
		hits = len(rows)
	} else if status == 200 && action == "kb_page_show" {
		hits = 1
	}
	now := time.Now().In(auditZone)
	entry := map[string]any{"timestamp": now.Format(time.DateTime), "actor": id.User, "env": id.Env, "ticket_id": id.ID, "action": action, "kb_id": data["kb_id"], "query": redact(q.Get("q")), "slug": redact(q.Get("slug")), "status": status, "duration_ms": time.Since(start).Milliseconds(), "hit_count": hits, "client_ip": ip.String(), "candidate_window_exhausted": data["candidate_window_exhausted"], "request_id": strings.TrimSpace(r.Header.Get("X-Request-ID"))}
	if s.log(now, entry) != nil {
		reply(w, 503, map[string]string{"code": "AUDIT_UNAVAILABLE"})
		return
	}
	reply(w, status, data)
}
func containsIP(prefixes []netip.Prefix, ip netip.Addr) bool {
	for _, prefix := range prefixes {
		if prefix.Contains(ip) {
			return true
		}
	}
	return false
}

// Only a verified ticket may supply audit identity fields.
func (s *Server) deny(w http.ResponseWriter, status int, code, action string, ip netip.Addr, id auth.Identity) {
	now := time.Now().In(auditZone)
	entry := map[string]any{"timestamp": now.Format(time.DateTime), "status": status, "code": code, "action": action, "client_ip": ip.String()}
	if id.ID != "" {
		entry["actor"] = id.User
		entry["ticket_id"] = id.ID
		entry["env"] = id.Env
		entry["ticket_action"] = id.Action
	}
	if err := s.log(now, entry); err != nil {
		reply(w, 503, map[string]string{"code": "AUDIT_UNAVAILABLE"})
		return
	}
	reply(w, status, map[string]string{"code": code})
}
func (s *Server) log(t time.Time, entry any) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	f, e := os.OpenFile(filepath.Join(s.Dir, "kb-audit-"+t.Format(time.DateOnly)+".jsonl"), os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0640)
	if e != nil {
		return e
	}
	e = json.NewEncoder(f).Encode(entry)
	return errors.Join(e, f.Close())
}
