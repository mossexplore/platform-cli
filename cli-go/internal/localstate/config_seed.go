package localstate

import (
	"errors"
	"fmt"
	"os"
)

// LoadOrInitializeConfig is used at the foreground command entry point before
// callers can acquire state locks or check a previously established target.
func (p Paths) LoadOrInitializeConfig() (Config, error) {
	data, err := os.ReadFile(p.Config())
	if !errors.Is(err, os.ErrNotExist) || p.configTemplate == "" {
		return decodeConfig(p.Config(), data, err)
	}
	seed, err := os.ReadFile(p.configTemplate)
	if errors.Is(err, os.ErrNotExist) {
		return decodeConfig(p.Config(), nil, err)
	}
	cfg, err := decodeConfig(p.configTemplate, seed, err)
	if err != nil {
		return Config{}, err
	}
	unlock, err := p.LockState()
	if err != nil {
		return Config{}, err
	}
	defer unlock()

	// Another ml process may have initialized or selected an environment while
	// we were validating the template. Keep its configuration in that case.
	data, err = os.ReadFile(p.Config())
	if !errors.Is(err, os.ErrNotExist) {
		return decodeConfig(p.Config(), data, err)
	}
	if err := WritePrivate(p.Config(), seed); err != nil {
		return Config{}, fmt.Errorf("无法初始化配置文件 %s: %w", p.Config(), err)
	}
	return cfg, nil
}
