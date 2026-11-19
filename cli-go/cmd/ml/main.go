package main

import (
	"context"
	"os"
	"os/signal"

	"github.com/mossexplore/platform-cli/cli-go/internal/command"
	"github.com/mossexplore/platform-cli/cli-go/internal/keepalive"
	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func main() {
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt)
	defer stop()
	if len(os.Args) == 4 && os.Args[1] == keepalive.WorkerArg {
		paths, err := localstate.DefaultPaths()
		if err == nil {
			_ = keepalive.RunWorker(ctx, paths.WithoutSession(), os.Args[2], os.Args[3], version)
		}
		return
	}
	code := command.Run(ctx, command.Options{
		Version: version, Args: os.Args[1:], Stdout: os.Stdout, Stderr: os.Stderr,
	})
	if code != 0 {
		stop()
		os.Exit(code)
	}
}
