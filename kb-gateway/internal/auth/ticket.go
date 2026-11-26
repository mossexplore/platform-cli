package auth

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"
	"regexp"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"
)

var akPattern = regexp.MustCompile("^[A-Za-z0-9_-]{1,64}$")
var uuid = regexp.MustCompile("^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$")

func Keys(raw string) (map[string]string, error) {
	keys := map[string]string{}
	for _, pair := range strings.Split(raw, ",") {
		ak, sk, ok := strings.Cut(pair, ":")
		if !ok || !akPattern.MatchString(ak) || len(sk) < 32 || keys[ak] != "" {
			return nil, errors.New("invalid KB_TICKET_KEYS")
		}
		keys[ak] = sk
	}
	return keys, nil
}

type Identity struct{ ID, User, Env, Action string }

func encode(s string) string {
	const digits = "0123456789ABCDEF"
	var b strings.Builder
	for i := 0; i < len(s); i++ {
		c := s[i]
		if c >= 'a' && c <= 'z' || c >= 'A' && c <= 'Z' || c >= '0' && c <= '9' || strings.IndexByte("-._~", c) >= 0 {
			b.WriteByte(c)
		} else {
			b.WriteByte('%')
			b.WriteByte(digits[c>>4])
			b.WriteByte(digits[c&15])
		}
	}
	return b.String()
}
func Verify(h http.Header, keys map[string]string, now time.Time) (Identity, bool) {
	fields := []string{"v1"}
	for _, k := range []string{"AK", "Ticket-ID", "User", "Env", "Action", "Exp"} {
		v := h.Values("X-KB-" + k)
		if len(v) != 1 || v[0] == "" || !utf8.ValidString(v[0]) {
			return Identity{}, false
		}
		fields = append(fields, v[0])
	}
	key := keys[fields[1]]
	exp, e := strconv.ParseInt(fields[6], 10, 64)
	if key == "" || !uuid.MatchString(fields[2]) || e != nil || strconv.FormatInt(exp, 10) != fields[6] || exp < now.Unix()-15 || exp > now.Unix()+315 {
		return Identity{}, false
	}
	id := Identity{fields[2], fields[3], fields[4], fields[5]}
	for i, v := range fields {
		fields[i] = encode(v)
	}
	mac := hmac.New(sha256.New, []byte(key))
	mac.Write([]byte(strings.Join(fields, "\n")))
	sig, e := hex.DecodeString(h.Get("X-KB-Signature"))
	return id, e == nil && len(h.Values("X-KB-Signature")) == 1 && hmac.Equal(sig, mac.Sum(nil))
}
