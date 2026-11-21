package localstate

import (
	"encoding/hex"
	"encoding/json"
	"os"
	"path/filepath"
	"strings"
	"time"
)

const SessionCleanupInterval = time.Hour

func (p Paths) MaintainSessions(now time.Time, inUse []SessionScope) {
	if _, err := os.Stat(p.SessionsDir()); err != nil {
		return
	}
	marker := filepath.Join(p.SessionsDir(), ".last-cleanup")
	recentlyCleaned := func() bool {
		info, err := os.Stat(marker)
		return err == nil && now.Sub(info.ModTime()) < SessionCleanupInterval
	}
	if recentlyCleaned() {
		return
	}
	unlock, err := p.lockWithin(filepath.Join("sessions", "cleanup.lock"), 0)
	if err != nil {
		return
	}
	defer unlock()
	if recentlyCleaned() {
		return
	}

	entries, err := os.ReadDir(p.SessionsDir())
	if err != nil {
		return
	}
	protected := map[string]bool{}
	if p.IsSessionIsolated() {
		protected[filepath.Base(p.SessionFile())] = true
	}
	for _, scope := range inUse {
		if scope.Isolated() {
			protected[filepath.Base(p.WithSession(scope).SessionFile())] = true
		}
	}
	cutoff := now.Add(-defaultSessionTTL)
	for _, entry := range entries {
		if !entry.Type().IsRegular() || protected[entry.Name()] || !isSessionStateFile(entry.Name()) {
			continue
		}
		info, err := entry.Info()
		if err == nil && info.ModTime().Before(cutoff) {
			p.removeExpiredSession(entry.Name(), cutoff)
		}
	}
	_ = WritePrivate(marker, nil)
}

func isSessionStateFile(name string) bool {
	id, ok := strings.CutSuffix(name, ".json")
	if !ok || len(id) != 32 || id != strings.ToLower(id) {
		return false
	}
	_, err := hex.DecodeString(id)
	return err == nil
}

func (p Paths) removeExpiredSession(name string, cutoff time.Time) {
	unlock, err := p.lockWithin(sessionLockName(name), 0)
	if err != nil {
		return
	}
	defer unlock()
	path := filepath.Join(p.SessionsDir(), name)
	info, err := os.Lstat(path)
	if err != nil || !info.Mode().IsRegular() || !info.ModTime().Before(cutoff) {
		return
	}
	data, err := os.ReadFile(path)
	if err != nil {
		return
	}
	var state SessionState
	if json.Unmarshal(data, &state) == nil && !state.UpdatedAt.IsZero() && !state.UpdatedAt.Before(cutoff) {
		return
	}
	// Keep the lock file's identity stable for callers waiting on it.
	_ = os.Remove(path)
}
