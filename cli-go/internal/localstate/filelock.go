package localstate

import (
	"errors"
	"os"
	"path/filepath"
	"time"
)

func (p Paths) lock(name string) (func(), error) {
	if err := os.MkdirAll(p.Dir, 0700); err != nil {
		return nil, errors.New("无法创建 Go 预览状态目录")
	}
	file, err := os.OpenFile(filepath.Join(p.Dir, name), os.O_CREATE|os.O_RDWR, 0600)
	if err != nil {
		return nil, errors.New("无法打开本地状态锁 " + name)
	}
	deadline := time.Now().Add(3 * time.Second)
	for {
		acquired, err := lockFile(file)
		if err != nil || !acquired && !time.Now().Before(deadline) {
			_ = file.Close()
			return nil, errors.New("本地状态正在使用，请稍后重试 " + name)
		}
		if acquired {
			return func() {
				_ = unlockFile(file)
				_ = file.Close()
			}, nil
		}
		time.Sleep(50 * time.Millisecond)
	}
}
