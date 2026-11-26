//go:build accesscontract

package platform

import (
	"context"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"io"
	"os"
	"testing"
)

func TestLiveAccessContract(t *testing.T) {
	session := Session{Paths: localstate.Paths{Dir: t.TempDir()}}
	session.Config.Access = localstate.Access{URL: os.Getenv("ACCESS_CONTRACT_URL"), TimeoutSecs: 10}
	profile := localstate.Profile{Name: "prod", Endpoint: "https://platform.example.com"}
	for _, username := range []string{"alice", "unregistered"} {
		meta := invocation{version: os.Getenv("ACCESS_CONTRACT_CLI_VERSION"), id: localstate.NewID(), stderr: io.Discard}
		err := session.requireAccess(context.Background(), &meta, profile, username, "contract-business", "kb search", "ml kb search query")
		if username == "unregistered" {
			if err == nil || meta.ticket != nil {
				t.Fatal("denied user was admitted or received a ticket")
			}
			continue
		}
		if err != nil {
			t.Fatal(err)
		}
		ticket := meta.ticket
		if ticket == nil || ticket.Username != username || ticket.Environment != profile.Name || ticket.Action != "kb_search" || ticket.AK != "contract" || ticket.ID == "" || ticket.Sig == "" || ticket.Exp <= 0 {
			t.Fatal("missing or incompatible knowledge-base ticket")
		}
	}
}
