#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .. -e .
if [ ! -f config.local.json ]; then cp config.example.json config.local.json; fi
printf '%s\n' '填写 config.local.json，创建 MySQL 数据库，再执行迁移与启动。请预先安装 Microsoft Edge。'
