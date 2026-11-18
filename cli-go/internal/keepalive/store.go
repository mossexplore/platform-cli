package keepalive

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

type owner struct {
	PID      int    `json:"pid"`
	Identity string `json:"identity"`
}

type Entry struct {
	Owner          []owner   `json:"owners"`
	Endpoint       string    `json:"api_endpoint"`
	Username       string    `json:"username"`
	WorkerPID      int       `json:"worker_pid"`
	WorkerIdentity string    `json:"worker_identity"`
	WorkerToken    string    `json:"worker_token"`
	Version        string    `json:"worker_version"`
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
	unlock, err := paths.LockPing()
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
func validOwners(entry Entry) []owner {
	items := []owner{}
	for _, candidate := range entry.Owner {
		if candidate.Identity != "" && identity(candidate.PID) == candidate.Identity {
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
func Detach(paths localstate.Paths, profile string) error {
	pid := os.Getppid()
	return update(paths, func(entries map[string]Entry) error {
		entry, exists := entries[profile]
		if !exists {
			return nil
		}
		owners := []owner{}
		for _, item := range validOwners(entry) {
			if item.PID != pid {
				owners = append(owners, item)
			}
		}
		entry.Owner = owners
		entries[profile] = entry
		return nil
	})
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
