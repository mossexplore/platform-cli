package auth

import (
	"encoding/json"
	"net/http"
	"os"
	"strconv"
	"testing"
	"time"
)

func TestIssuerCompatibility(t *testing.T) {
	data, err := os.ReadFile("../../testdata/ticket.json")
	if err != nil {
		t.Fatal(err)
	}
	var v struct {
		Key, AK, Username, Environment, Action, Sig string
		ID                                          string `json:"ticket_id"`
		Exp                                         int64
	}
	if err := json.Unmarshal(data, &v); err != nil {
		t.Fatal(err)
	}
	keys := map[string]string{v.AK: v.Key}
	h := http.Header{}
	for k, s := range map[string]string{"AK": v.AK, "Ticket-ID": v.ID, "User": v.Username, "Env": v.Environment, "Action": v.Action, "Signature": v.Sig, "Exp": strconv.FormatInt(v.Exp, 10)} {
		h.Set("X-KB-"+k, s)
	}
	for _, offset := range []int64{-316, -315, -300, 15, 16} {
		_, ok := Verify(h, keys, time.Unix(v.Exp+offset, 0))
		if ok != (offset >= -315 && offset <= 15) {
			t.Fatalf("unexpected validity at offset %d", offset)
		}
	}
	for _, header := range []string{"AK", "Ticket-ID", "User", "Env", "Action", "Exp", "Signature"} {
		altered := h.Clone()
		altered.Set("X-KB-"+header, "changed")
		if _, ok := Verify(altered, keys, time.Unix(v.Exp, 0)); ok {
			t.Fatal(header)
		}
	}
}
