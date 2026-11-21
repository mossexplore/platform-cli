package localstate

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"time"
)

var ErrLockBusy = errors.New("本地状态正在使用，请稍后重试")

const DefaultLockWait = 3 * time.Second

func (p Paths) lock(name string) (func(), error) {
	return p.lockWithin(name, DefaultLockWait)
}

func (p Paths) lockWithin(name string, wait time.Duration) (func(), error) {
	path := filepath.Join(p.Dir, name)
	label := filepath.Base(path)
	if err := os.MkdirAll(filepath.Dir(path), 0700); err != nil {
		return nil, fmt.Errorf("无法创建 Go 预览状态目录: %w", err)
	}
	deadline := time.Now().Add(wait)
	var file *os.File
	for {
		if file == nil {
			var err error
			file, err = os.OpenFile(path, os.O_CREATE|os.O_RDWR, 0600)
			if err != nil && !lockSharingViolation(err) {
				return nil, fmt.Errorf("无法打开本地状态锁 %s: %w", label, err)
			}
		}
		if file != nil {
			acquired, err := lockFile(file)
			if err != nil {
				_ = file.Close()
				return nil, fmt.Errorf("无法获取本地状态锁 %s: %w", label, err)
			}
			if acquired {
				return func() {
					_ = unlockFile(file)
					_ = file.Close()
				}, nil
			}
		}
		left := time.Until(deadline)
		if left <= 0 {
			if file != nil {
				_ = file.Close()
			}
			return nil, fmt.Errorf("%w %s", ErrLockBusy, label)
		}
		time.Sleep(min(left, 50*time.Millisecond))
	}
}
