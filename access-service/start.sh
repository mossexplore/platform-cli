#!/usr/bin/env bash
# Run directly from the extracted package, with no root/systemd requirement.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/bootstrap.sh"
exec .venv/bin/python -m app.portable
