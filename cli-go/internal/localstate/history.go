package localstate

import (
	"bufio"
	"bytes"
	"crypto/sha256"
	"encoding/json"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"sort"
)

type HistoryEntry struct {
	Key       string  `json:"_key,omitempty"`
	Time      string  `json:"time"`
	Started   float64 `json:"started_at"`
	Finished  float64 `json:"finished_at"`
	Duration  int64   `json:"duration_ms"`
	Command   string  `json:"command"`
	Before    *string `json:"env"`
	After     *string `json:"env_after"`
	Config    string  `json:"config"`
	CWD       string  `json:"cwd"`
	Business  *string `json:"business_id"`
	Version   string  `json:"version"`
	ExitCode  int     `json:"exit_code"`
	Status    string  `json:"status"`
	Redacted  bool    `json:"redacted"`
	Truncated bool    `json:"truncated"`
}

func (p Paths) CurrentEnvironment() *string {
	cfg, err := LoadConfig(p)
	if err != nil || cfg.Current == "" {
		return nil
	}
	return &cfg.Current
}

func (p Paths) ReadHistory() ([]HistoryEntry, int, error) {
	path := filepath.Join(p.Dir, "history.jsonl")
	rows := []HistoryEntry{}
	file, err := os.Open(path)
	if errors.Is(err, os.ErrNotExist) {
		return rows, 0, nil
	}
	if err != nil {
		return nil, 0, err
	}
	defer file.Close()
	scanner := bufio.NewScanner(file)
	scanner.Buffer(make([]byte, 4096), 1<<20)
	damaged := 0
	for line := 0; scanner.Scan(); line++ {
		var entry HistoryEntry
		raw := scanner.Bytes()
		if json.Unmarshal(raw, &entry) != nil || entry.Command == "" || entry.Time == "" || entry.Status == "" {
			damaged++
			continue
		}
		if entry.Key == "" {
			entry.Key = fmt.Sprintf("%x", sha256.Sum256(fmt.Appendf(nil, "%d:%s", line, raw)))
		}
		rows = append(rows, entry)
	}
	return rows, damaged, scanner.Err()
}

func (p Paths) writeHistory(rows []HistoryEntry) error {
	var file bytes.Buffer
	encoder := json.NewEncoder(&file)
	encoder.SetEscapeHTML(false)
	for _, row := range rows {
		if err := encoder.Encode(row); err != nil {
			return err
		}
	}
	return WritePrivate(filepath.Join(p.Dir, "history.jsonl"), file.Bytes())
}

func (p Paths) AppendHistory(entry HistoryEntry) error {
	unlock, err := p.lock("history.lock")
	if err != nil {
		return err
	}
	defer unlock()
	rows, _, err := p.ReadHistory()
	if err != nil {
		return err
	}
	entry.Key = NewID()
	rows = append(rows, entry)
	sort.SliceStable(rows, func(i, j int) bool { return rows[i].Started < rows[j].Started })
	if len(rows) > 1000 {
		rows = rows[len(rows)-1000:]
	}
	return p.writeHistory(rows)
}

func (p Paths) ClearHistory(keys map[string]bool) (int, error) {
	unlock, err := p.lock("history.lock")
	if err != nil {
		return 0, err
	}
	defer unlock()
	rows, _, err := p.ReadHistory()
	if err != nil {
		return 0, err
	}
	remaining := rows[:0]
	for _, row := range rows {
		if !keys[row.Key] {
			remaining = append(remaining, row)
		}
	}
	return len(rows) - len(remaining), p.writeHistory(remaining)
}
