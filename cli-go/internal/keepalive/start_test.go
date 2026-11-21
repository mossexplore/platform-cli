package keepalive

import (
	"context"
	"errors"
	"io/fs"
	"os"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func TestConfirmWorkerRetriesTemporaryReadFailure(t *testing.T) {
	calls := 0
	err := confirmWorker(context.Background(), "worker", 3*time.Second, func() (Entry, bool, error) {
		calls++
		switch calls {
		case 1:
			return Entry{}, false, fs.ErrPermission
		case 2:
			return Entry{WorkerToken: "worker", Status: "starting"}, true, nil
		default:
			return Entry{WorkerToken: "worker", Status: "running"}, true, nil
		}
	})
	if err != nil || calls != 3 {
		t.Fatalf("confirmation returned %v after %d reads", err, calls)
	}
}

func TestConfirmWorkerReportsUnconfirmedWithLastReadError(t *testing.T) {
	err := confirmWorker(context.Background(), "worker", 0, func() (Entry, bool, error) {
		return Entry{}, false, fs.ErrPermission
	})
	if !errors.Is(err, fs.ErrPermission) || !strings.Contains(err.Error(), "自动保活未能确认启动") {
		t.Fatalf("confirmation lost the underlying error: %v", err)
	}
}

func TestConfirmWorkerDistinguishesStoppedAndReplaced(t *testing.T) {
	for _, token := range []string{"", "other"} {
		err := confirmWorker(context.Background(), "worker", 0, func() (Entry, bool, error) {
			return Entry{WorkerToken: token}, false, nil
		})
		if err == nil || errors.Is(err, errReplaced) != (token == "other") {
			t.Fatalf("unexpected confirmation result for token %q: %v", token, err)
		}
	}
}

func TestLoadDistinguishesReadFailureAndInvalidRegistry(t *testing.T) {
	for _, test := range []struct {
		name   string
		create func(string) error
	}{
		{"read failure", func(path string) error { return os.Mkdir(path, 0700) }},
		{"invalid registry", func(path string) error { return os.WriteFile(path, []byte("{"), 0600) }},
	} {
		t.Run(test.name, func(t *testing.T) {
			paths := localstate.Paths{Dir: t.TempDir()}
			if err := test.create(filepath.Join(paths.Dir, "ping-go.json")); err != nil {
				t.Fatal(err)
			}
			_, err := load(paths)
			var pathErr *os.PathError
			switch test.name {
			case "read failure":
				if !errors.As(err, &pathErr) || !strings.Contains(err.Error(), "无法读取 Go 保活状态") {
					t.Fatalf("read failure lost its underlying cause: %v", err)
				}
			case "invalid registry":
				if err == nil || errors.As(err, &pathErr) || !strings.Contains(err.Error(), "格式无效") {
					t.Fatalf("invalid registry was not distinguished: %v", err)
				}
			}
		})
	}
}
