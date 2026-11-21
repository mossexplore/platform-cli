package keepalive

import (
	"os"
	"slices"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func currentOwner(scope localstate.SessionScope, now time.Time) owner {
	item := owner{ownerRef: ownerRef{ID: scope.ID, Mode: scope.EffectiveMode()}}
	if scope.Mode == localstate.SessionModeDSH {
		item.Seen = now
		return item
	}
	if !scope.Isolated() {
		item.Mode = "" // Legacy terminal owners have no session fields.
	}
	item.PID = os.Getppid()
	item.Identity = identity(item.PID)
	return item
}

func (o owner) live(now time.Time, interval time.Duration) bool {
	if o.Mode == localstate.SessionModeDSH {
		return o.ID != "" && !o.Seen.IsZero() && interval > 0 && now.Sub(o.Seen)/interval < 3
	}
	return o.Identity != "" && identity(o.PID) == o.Identity
}

func (o owner) belongsTo(scope localstate.SessionScope, pid int) bool {
	if scope.Isolated() {
		return o.Mode == scope.Mode && o.ID == scope.ID
	}
	return o.Mode == "" && o.PID == pid
}

func (o owner) paths(base localstate.Paths) (localstate.Paths, bool) {
	switch o.Mode {
	case localstate.SessionModeDSH, localstate.SessionModeEnv:
		if o.ID == "" {
			return localstate.Paths{}, false
		}
		return base.WithSession(localstate.SessionScope{Mode: o.Mode, ID: o.ID}), true
	case "":
		return base.WithoutSession(), o.ID == ""
	}
	return localstate.Paths{}, false
}

func registerOwner(entry *Entry, item owner) {
	index := slices.IndexFunc(entry.Owner, func(registered owner) bool {
		return registered.ownerRef == item.ownerRef
	})
	if index == -1 {
		entry.Owner = append(entry.Owner, item)
	} else {
		entry.Owner[index] = item
	}
}

func TerminalCount(entry Entry) int {
	return len(entry.Owner) - SessionCount(entry)
}

func SessionCount(entry Entry) int {
	count := 0
	for _, item := range entry.Owner {
		if item.Mode == localstate.SessionModeDSH {
			count++
		}
	}
	return count
}
