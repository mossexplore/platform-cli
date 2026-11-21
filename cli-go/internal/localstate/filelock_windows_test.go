package localstate

import (
	"errors"
	"path/filepath"
	"testing"

	"golang.org/x/sys/windows"
)

func TestWindowsExclusiveOpenIsReportedAsLockContention(t *testing.T) {
	paths := Paths{Dir: t.TempDir()}
	path, err := windows.UTF16PtrFromString(filepath.Join(paths.Dir, "ping-go.lock"))
	if err != nil {
		t.Fatal(err)
	}
	handle, err := windows.CreateFile(path, windows.GENERIC_READ|windows.GENERIC_WRITE, 0,
		nil, windows.OPEN_ALWAYS, windows.FILE_ATTRIBUTE_NORMAL, 0)
	if err != nil {
		t.Fatal(err)
	}
	unlock, lockErr := paths.LockPingWithin(0)
	if err := windows.CloseHandle(handle); err != nil {
		t.Fatal(err)
	}
	if unlock != nil {
		unlock()
	}
	if !errors.Is(lockErr, ErrLockBusy) {
		t.Fatalf("exclusive open was not reported as temporary contention: %v", lockErr)
	}
	unlock, err = paths.LockPingWithin(0)
	if err != nil {
		t.Fatalf("lock did not become available after closing the other handle: %v", err)
	}
	unlock()
}
