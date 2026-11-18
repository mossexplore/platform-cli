//go:build !windows

package updater

import (
	"context"
	"io"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
	"github.com/mossexplore/platform-cli/cli-go/internal/platform"
)

func Offer(context.Context, io.Reader, io.Writer, io.Writer, func() (localstate.Paths, error), string, *platform.VersionDenial) {
}
