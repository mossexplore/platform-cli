package keepalive

import (
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"slices"
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
}

type Entry struct {
	InFlight       probeLease    `json:"in_flight,omitzero"`
	RetryAt        time.Time     `json:"retry_at,omitzero"`
	RetryDelay     time.Duration `json:"retry_delay,omitempty"`
	ExpiredState   string        `json:"expired_state,omitempty"`
	Owner          []owner       `json:"owners"`
	Endpoint       string        `json:"api_endpoint"`
	Username       string        `json:"username"`
	WorkerPID      int           `json:"worker_pid"`
	WorkerIdentity string        `json:"worker_identity"`
	WorkerToken    string        `json:"worker_token"`
	Version        string        `json:"worker_version"`
	Protocol       int           `json:"worker_protocol,omitempty"`
	LastOwner      ownerRef      `json:"last_confirmed_owner,omitzero"`
	Status         string        `json:"status"`
	ManualStop     bool          `json:"manual_stop"`
	LastActivity   time.Time     `json:"last_activity"`
	LastConfirmed  time.Time     `json:"last_confirmed"`
	LastAttempt    time.Time     `json:"last_attempt"`
	RequestID      string        `json:"last_request_id"`
	Success        int           `json:"success_count"`
	Failure        int           `json:"failure_count"`
	Error          string        `json:"last_error"`
}

type entryFile struct {
	Profiles map[string]Entry            `json:"profiles"`
	Hosts    map[string]hostRegistration `json:"hosts,omitempty"`
}

func load(paths localstate.Paths) (entryFile, error) {
	data := entryFile{Profiles: make(map[string]Entry), Hosts: make(map[string]hostRegistration)}
	raw, err := os.ReadFile(filepath.Join(paths.Dir, "ping-go.json"))
	if errors.Is(err, os.ErrNotExist) {
		return data, nil
	}
	if err != nil {
		return entryFile{}, fmt.Errorf("无法读取 Go 保活状态：%w", err)
	}
	if json.Unmarshal(raw, &data) != nil || data.Profiles == nil {
		return entryFile{}, errors.New("Go 保活状态文件 ping-go.json 格式无效")
	}
	return data, nil
}

func update(paths localstate.Paths, change func(map[string]Entry) error) error {
	return updateWithin(paths, localstate.DefaultLockWait, change)
}

func updateWithin(paths localstate.Paths, wait time.Duration, change func(map[string]Entry) error) error {
	return updateRegistry(paths, wait, func(data entryFile) error { return change(data.Profiles) })
}

func updateRegistry(paths localstate.Paths, wait time.Duration, change func(entryFile) error) error {
	unlock, err := paths.LockPingWithin(wait)
	if err != nil {
		return err
	}
	defer unlock()
	data, err := load(paths)
	if err != nil {
		return err
	}
	for key, entry := range data.Profiles {
		entry.Owner = slices.DeleteFunc(entry.Owner, func(candidate owner) bool {
			return candidate.Mode == localstate.SessionModeDSH
		})
		data.Profiles[key] = entry
	}
	if data.Hosts == nil {
		data.Hosts = make(map[string]hostRegistration)
	}
	for key, host := range data.Hosts {
		if time.Since(host.Seen) >= time.Hour {
			delete(data.Hosts, key)
		}
	}
	if err := change(data); err != nil {
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
func validOwners(entry Entry) []owner {
	items := []owner{}
	for _, candidate := range entry.Owner {
		if candidate.live() {
			items = append(items, candidate)
		}
	}
	return items
}
func View(paths localstate.Paths, profile string) (Entry, bool, error) {
	data, err := load(paths)
	if err != nil {
		return Entry{}, false, err
	}
	entry := data.Profiles[profile]
	entry.Owner = validOwners(entry)
	return entry, entry.Protocol == workerProtocol && alive(entry), nil
}
func Stop(paths localstate.Paths, name string) error {
	return update(paths, func(profiles map[string]Entry) error {
		stopProfile(profiles, name)
		return nil
	})
}

func StopAll(paths localstate.Paths, configured []localstate.Profile) error {
	return update(paths, func(profiles map[string]Entry) error {
		for name := range profiles {
			stopProfile(profiles, name)
		}
		for _, profile := range configured {
			stopProfile(profiles, profile.Name)
		}
		return nil
	})
}

func stopProfile(profiles map[string]Entry, name string) {
	entry := profiles[name]
	entry.Owner = nil
	entry.Status, entry.ManualStop = "stopping", true
	entry.InFlight.Cancelled = entry.InFlight.ID != ""
	profiles[name] = entry
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

func MaintainSessions(paths localstate.Paths) {
	file, err := load(paths)
	if err != nil {
		return
	}
	now := time.Now()
	var active []localstate.SessionScope
	for _, entry := range file.Profiles {
		for _, item := range validOwners(entry) {
			if scoped, ok := item.paths(paths); ok && scoped.IsSessionIsolated() {
				active = append(active, scoped.Session)
			}
		}
	}
	for _, registration := range file.Hosts {
		if registration.active(now) {
			active = append(active, registration.scope())
		}
	}
	paths.MaintainSessions(now, active)
}
func Touch(paths localstate.Paths, profile, username, endpoint string) {
	_ = update(paths, func(entries map[string]Entry) error {
		entry := entries[profile]
		if entry.Endpoint != endpoint || entry.Username != username {
			if alive(entry) {
				return nil
			}
			entry = resetLogin(entry, username, endpoint)
		}
		entry.LastActivity = time.Now()
		entries[profile] = entry
		return nil
	})
}

func resetLogin(entry Entry, username, endpoint string) Entry {
	return Entry{Endpoint: endpoint, Username: username, ManualStop: entry.ManualStop, InFlight: entry.InFlight}
}
