package server

import (
	"io"
	"mime"
	"net/http"
	"net/netip"
	"path"
	"strconv"
	"strings"
	"time"

	"github.com/mossexplore/platform-cli/kb-gateway/internal/auth"
)

func (s *Server) download(w http.ResponseWriter, r *http.Request, id auth.Identity, ip netip.Addr, start time.Time) {
	q := r.URL.Query()
	file, name, data, err := s.Client.OpenFile(r.Context(), id.Env, id.User, q)
	if file != nil {
		defer file.Body.Close()
	}
	status, data := resultStatus(data, err)
	now := time.Now().In(auditZone)
	entry := map[string]any{"timestamp": now.Format(time.DateTime), "actor": id.User, "env": id.Env,
		"ticket_id": id.ID, "action": id.Action, "kb_id": data["kb_id"], "knowledge_id": redact(q.Get("id")),
		"status": status, "duration_ms": time.Since(start).Milliseconds(), "client_ip": ip.String(),
		"request_id": strings.TrimSpace(r.Header.Get("X-Request-ID"))}
	if err == nil {
		entry["transfer"] = "started"
		entry["file_size"] = file.ContentLength
	}
	if s.log(now, entry) != nil {
		reply(w, 503, map[string]string{"code": "AUDIT_UNAVAILABLE"})
		return
	}
	if err != nil {
		reply(w, status, data)
		return
	}
	w.Header().Set("Content-Type", "application/octet-stream")
	name = path.Base(strings.ReplaceAll(name, "\\", "/"))
	w.Header().Set("Content-Disposition", mime.FormatMediaType("attachment", map[string]string{"filename": name}))
	w.Header().Set("Content-Length", strconv.FormatInt(file.ContentLength, 10))
	err = copyFile(w, file.Body, file.ContentLength)
	now = time.Now().In(auditZone)
	entry["timestamp"] = now.Format(time.DateTime)
	entry["duration_ms"] = time.Since(start).Milliseconds()
	entry["transfer"] = "complete"
	if err != nil {
		entry["status"] = http.StatusBadGateway
		entry["transfer"] = "interrupted"
	}
	_ = s.log(now, entry)
	if err != nil {
		panic(http.ErrAbortHandler)
	}
}

// Hold the final byte until EOF is confirmed so a bad upstream size always
// reaches the CLI as an incomplete transfer.
func copyFile(dst io.Writer, src io.Reader, size int64) error {
	if size > 0 {
		if _, err := io.CopyN(dst, src, size-1); err != nil {
			return err
		}
	}
	var last [2]byte
	n, err := io.ReadFull(src, last[:])
	if size == 0 && n == 0 && err == io.EOF {
		return nil
	}
	if size > 0 && n == 1 && err == io.ErrUnexpectedEOF {
		_, err = dst.Write(last[:1])
		return err
	}
	return io.ErrUnexpectedEOF
}
