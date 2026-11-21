package keepalive

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

type ownerRef struct {
	PID      int                    `json:"pid,omitempty"`
	Identity string                 `json:"identity,omitempty"`
	Mode     localstate.SessionMode `json:"session_mode,omitempty"`
	ID       string                 `json:"session_id,omitempty"`
}

type owner struct {
	ownerRef
	Seen time.Time `json:"last_seen,omitzero"`
}

type Entry struct {
	Owner          []owner   `json:"owners"`
	Endpoint       string    `json:"api_endpoint"`
	Username       string    `json:"username"`
	WorkerPID      int       `json:"worker_pid"`
	WorkerIdentity string    `json:"worker_identity"`
	WorkerToken    string    `json:"worker_token"`
	Version        string    `json:"worker_version"`
	Protocol       int       `json:"worker_protocol,omitempty"`
	LastOwner      ownerRef  `json:"last_confirmed_owner,omitzero"`
	Status         string    `json:"status"`
	ManualStop     bool      `json:"manual_stop"`
	LastActivity   time.Time `json:"last_activity"`
	LastConfirmed  time.Time `json:"last_confirmed"`
	LastAttempt    time.Time `json:"last_attempt"`
	RequestID      string    `json:"last_request_id"`
	Success        int       `json:"success_count"`
	Failure        int       `json:"failure_count"`
	Error          string    `json:"last_error"`
}

type entryFile struct {
	Profiles map[string]Entry `json:"profiles"`
}

func load(paths localstate.Paths) (entryFile, error) {
	data := entryFile{Profiles: make(map[string]Entry)}
	raw, err := os.ReadFile(filepath.Join(paths.Dir, "ping-go.json"))
	if errors.Is(err, os.ErrNotExist) {
		return data, nil
	}
	if err != nil || json.Unmarshal(raw, &data) != nil || data.Profiles == nil {
		return entryFile{}, errors.New("无法读取 Go 保活状态")
	}
	return data, nil
}

func update(paths localstate.Paths, change func(map[string]Entry) error) error {
	return updateWithin(paths, localstate.DefaultLockWait, change)
}

func updateWithin(paths localstate.Paths, wait time.Duration, change func(map[string]Entry) error) error {
	unlock, err := paths.LockPingWithin(wait)
	if err != nil {
		return err
	}
	defer unlock()
	data, err := load(paths)
	if err != nil {
		return err
	}
	if err := change(data.Profiles); err != nil {
		return err
	}
	result, err := json.Marshal(data)
	if err != nil {
		return err
	}
	return localstate.WritePrivate(filepath.Join(paths.Dir, "ping-go.json"), result)
}

func alive(entry Entry) bool {
	return entry.WorkerIdentity != "" && identity(entry.WorkerPID) == entry.WorkerIdentity
}
func validOwners(entry Entry, now time.Time, interval time.Duration) []owner {
	items := []owner{}
	for _, candidate := range entry.Owner {
		if candidate.live(now, interval) {
			items = append(items, candidate)
		}
	}
	return items
}
func View(paths localstate.Paths, profile string, interval time.Duration) (Entry, bool, error) {
	data, err := load(paths)
	if err != nil {
		return Entry{}, false, err
	}
	entry := data.Profiles[profile]
	entry.Owner = validOwners(entry, time.Now(), interval)
	return entry, alive(entry), nil
}
func Stop(paths localstate.Paths, profile string, all bool) error {
	return update(paths, func(profiles map[string]Entry) error {
		for key, entry := range profiles {
			if all || key == profile {
				entry.Owner = nil
				entry.Status, entry.ManualStop = "stopping", true
				profiles[key] = entry
			}
		}
		return nil
	})
}
func detachOwner(entries map[string]Entry, paths localstate.Paths, profile string) error {
	entry, exists := entries[profile]
	if !exists {
		return nil
	}
	if paths.IsSessionIsolated() {
		state, _, err := paths.LoadSessionState()
		if err != nil {
			return err
		}
		if state.Current == profile {
			return nil
		}
	}
	pid := os.Getppid()
	owners := []owner{}
	for _, item := range entry.Owner {
		if !item.belongsTo(paths.Session, pid) {
			owners = append(owners, item)
		}
	}
	entry.Owner = owners
	entries[profile] = entry
	return nil
}

func DetachTerminal(paths localstate.Paths, profile string) error {
	return update(paths, func(entries map[string]Entry) error {
		return detachOwner(entries, paths, profile)
	})
}

func MaintainSessions(paths localstate.Paths, interval time.Duration) {
	file, err := load(paths)
	if err != nil {
		return
	}
	now := time.Now()
	var active []localstate.SessionScope
	for _, entry := range file.Profiles {
		for _, item := range validOwners(entry, now, interval) {
			if scoped, ok := item.paths(paths); ok && scoped.IsSessionIsolated() {
				active = append(active, scoped.Session)
			}
		}
	}
	paths.MaintainSessions(now, active)
}
func Touch(paths localstate.Paths, profile, username, endpoint string) {
	file, err := load(paths)
	if err != nil {
		return
	}
	entry, ok := file.Profiles[profile]
	if !ok || entry.WorkerToken == "" {
		return
	}
	_ = update(paths, func(entries map[string]Entry) error {
		entry, ok := entries[profile]
		if ok && entry.Username == username && entry.Endpoint == endpoint {
			entry.LastActivity = time.Now()
			entries[profile] = entry
		}
		return nil
	})
}
