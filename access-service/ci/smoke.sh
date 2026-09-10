#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${CLI_ACCESS_IMAGE:?Set CLI_ACCESS_IMAGE to the image under test}"
export BIND_IP=127.0.0.1 HTTP_PORT=${HTTP_PORT:-18008}
compose=(docker compose -f compose.yaml -f compose.ci.yaml)
# This file is ignored by Git. Never run CI against production deployment files.
if [[ -e docker/service.env ]]; then
  echo 'Refusing to overwrite an existing docker/service.env' >&2
  exit 1
fi
cp docker/service.env.example docker/service.env
cleanup() {
  result=$?
  "${compose[@]}" logs --no-color --tail=200 > "${RUNNER_TEMP:-/tmp}/cli-access-smoke.log" 2>&1 || true
  "${compose[@]}" down --volumes --remove-orphans || true
  rm -f docker/service.env
  exit "$result"
}
trap cleanup EXIT
"${compose[@]}" up -d --wait --wait-timeout 240 mysql
"${compose[@]}" run --rm cli-access python -m app.manage migrate
"${compose[@]}" run --rm cli-access python -m app.manage migrate
"${compose[@]}" up -d --wait --wait-timeout 120 cli-access
"${compose[@]}" exec -T cli-access python - <<'PY'
import os
from app.models import Admin, Environment, Grant, User, database
from app.security import password_hash
assert os.getuid() == 10001
engine, sessions = database(os.environ['DATABASE_URL'])
with sessions() as db:
    db.add(Admin(username='ci-admin', password_hash=password_hash('ci-password-123456'), role='super_admin'))
    user = User(username='ci-user', display_name='CI User')
    environment = Environment(name='ci', display_name='CI', platform_origin='https://platform.example.com')
    db.add_all([user, environment])
    db.flush()
    db.add(Grant(user_id=user.id, environment_id=environment.id))
    db.commit()
engine.dispose()
PY
python ci/smoke.py "http://127.0.0.1:$HTTP_PORT"
# Restart must preserve MySQL data and restore a healthy service.
"${compose[@]}" restart cli-access
"${compose[@]}" up -d --wait --wait-timeout 120 cli-access
python ci/smoke.py "http://127.0.0.1:$HTTP_PORT"
