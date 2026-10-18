#!/bin/sh
set -eu
DEMO_ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export WISEREC_DEMO_WORKSPACE="$DEMO_ROOT/workspace"
export ML_CONFIG="$DEMO_ROOT/workspace/config.json"
export PATH="$DEMO_ROOT/bin:$PATH"
test -x "$DEMO_ROOT/bin/ml"
"$DEMO_ROOT/runtime/bin/python" -I -m wiserec_cli_mock.bootstrap context --json >/dev/null
cd "$DEMO_ROOT/workspace"
exec bash --noprofile --norc
