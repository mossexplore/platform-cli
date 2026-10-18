#!/bin/sh
set -eu
DEMO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec "$DEMO_ROOT/runtime/bin/python" -I -m wiserec_cli_mock.manage --workspace "$DEMO_ROOT/workspace" "$@"
