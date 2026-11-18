package localstate

import (
	"bytes"
	"encoding/json"
	"errors"
	"fmt"
	"os"
)

type environmentSelection struct {
	Current string `json:"current"`
}

func (p Paths) loadConfig() (Config, bool, error) {
	if p.packaged == nil {
		return Config{}, false, errors.New("Go CLI 未加载内置配置")
	}
	cfg := *p.packaged
	data, err := os.ReadFile(p.Config())
	if errors.Is(err, os.ErrNotExist) {
		return cfg, true, nil
	}
	if err != nil {
		return Config{}, false, fmt.Errorf("无法读取环境选择文件 %s: %w", p.Config(), err)
	}

	// Legacy files may contain the entire editable configuration. Only current
	// is read, even when other fields are present or have incompatible types.
	var fields map[string]json.RawMessage
	var current string
	if json.Unmarshal(bytes.TrimPrefix(data, []byte("\xef\xbb\xbf")), &fields) == nil &&
		json.Unmarshal(fields["current"], &current) == nil && current != "" {
		selected := cfg
		selected.Current = current
		if selected.Profile().Name != "" {
			canonical, _ := json.Marshal(environmentSelection{Current: current})
			return selected, !bytes.Equal(bytes.TrimSpace(data), canonical), nil
		}
	}
	return cfg, true, nil
}

// LoadOrInitializeConfig migrates the selection at the foreground entry point,
// before commands take state locks or check a previously established target.
func (p Paths) LoadOrInitializeConfig() (Config, error) {
	cfg, rewrite, err := p.loadConfig()
	if err != nil || !rewrite {
		return cfg, err
	}
	unlock, err := p.LockState()
	if err != nil {
		return Config{}, err
	}
	defer unlock()

	// Respect a selection saved by another process while we waited for the lock.
	cfg, rewrite, err = p.loadConfig()
	if err == nil && rewrite {
		err = p.writeCurrent(cfg.Current)
	}
	return cfg, err
}

func (p Paths) writeCurrent(name string) error {
	return writeState(p.Config(), environmentSelection{Current: name})
}
