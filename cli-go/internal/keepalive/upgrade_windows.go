package keepalive

import (
	"context"
	"errors"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

// PauseForUpgrade lets workers exit without changing the user's manual stop preference.
func PauseForUpgrade(ctx context.Context, paths localstate.Paths) error {
	var workers []Entry
	if err := update(paths, func(profiles map[string]Entry) error {
		for name, entry := range profiles {
			if alive(entry) {
				workers = append(workers, entry)
				entry.Status = "stopping"
				profiles[name] = entry
			}
		}
		return nil
	}); err != nil {
		return err
	}

	ticker := time.NewTicker(100 * time.Millisecond)
	defer ticker.Stop()
	for _, worker := range workers {
		for alive(worker) {
			select {
			case <-ctx.Done():
				return errors.New("后台保活进程尚未退出，请稍后重试升级")
			case <-ticker.C:
			}
		}
	}
	return nil
}
