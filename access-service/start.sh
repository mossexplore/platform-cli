#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
exec .venv/bin/python -c 'from dotenv import load_dotenv; load_dotenv(); from app.serve import main; main()'
