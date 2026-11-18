// check-config validates a configuration file before it is put into a package.
package main

import (
	"fmt"
	"os"

	"github.com/mossexplore/platform-cli/cli-go/internal/localstate"
)

func main() {
	if len(os.Args) != 2 {
		fmt.Fprintln(os.Stderr, "usage: check-config CONFIG_PATH")
		os.Exit(2)
	}
	if err := localstate.ValidateConfigFile(os.Args[1]); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
