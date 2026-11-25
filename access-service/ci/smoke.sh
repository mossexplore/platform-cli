#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
: "${CLI_ACCESS_IMAGE:?Set CLI_ACCESS_IMAGE to the image under test}"
export COMPOSE_PROJECT_NAME="cli-access-ci-${GITHUB_RUN_ID:-$$}"
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
"${compose[@]}" run --rm -T cli-access python - <<'PY'
import os
from app.models import Admin, CallLog, Environment, Grant, User, database
from app.version_models import VersionPolicy
from sqlalchemy import text
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
    db.add(VersionPolicy(name='legacy-ci-policy', environment='ci', created_by='ci-admin'))
    db.add(CallLog(actor='ci-user', environment='ci', business_id='ci-business', command='ml jupyter exec',
                   full_command='ml jupyter exec -- print(1)', source_ip='', allowed=True, reason='ALLOWED'))
    db.commit()
# Restore the previous formal schema in the disposable CI database.
# This isolated MySQL database is never a production database.
with engine.begin() as connection:
    connection.execute(text('ALTER TABLE cli_call_logs MODIFY COLUMN full_command TEXT NULL'))
    connection.execute(text('ALTER TABLE cli_version_policies DROP COLUMN additional_environments'))
    connection.execute(text('UPDATE schema_versions SET version=13'))
engine.dispose()
PY
"${compose[@]}" run --rm cli-access python -m app.manage migrate
"${compose[@]}" run --rm cli-access python -m app.manage migrate
"${compose[@]}" up -d --wait --wait-timeout 120 cli-access
"${compose[@]}" exec -T cli-access python - <<'PY'
import os
from sqlalchemy import select
from app.migrations import SCHEMA_VERSION
from app.models import CallLog, Environment, Grant, SchemaVersion, database, now
from app.version_models import VersionPolicy
from app.version_policy import policies_for
engine, sessions = database(os.environ['DATABASE_URL'])
with sessions() as db:
    assert db.scalar(select(SchemaVersion.version)) == SCHEMA_VERSION
    environment = db.scalar(select(Environment))
    assert environment.default_grant is False
    assert environment.command_policy_revision == 0
    assert environment.forbidden_commands == []
    assert db.scalar(select(Grant)) is not None
    legacy = db.scalar(select(VersionPolicy))
    assert legacy.environments == ['ci']
    assert db.scalar(select(CallLog.full_command)) == 'ml jupyter exec -- print(1)'
    legacy.additional_environments = ['ci-stage']
    db.flush()
    assert [item.id for item in policies_for(db, 'ci-stage', 'ci-business', now())] == [legacy.id]
    assert policies_for(db, 'ci-stage-other', 'ci-business', now()) == []
    log = db.scalar(select(CallLog))
    log.full_command = 'ml jupyter exec -- ' + '合成参数' * 20000
    db.flush()
    db.refresh(log)
    assert len(log.full_command) > 80000
    db.rollback()
engine.dispose()
PY
python ci/smoke.py "http://127.0.0.1:$HTTP_PORT"
# Restart must preserve MySQL data and restore a healthy service.
"${compose[@]}" restart cli-access
"${compose[@]}" up -d --wait --wait-timeout 120 cli-access
python ci/smoke.py "http://127.0.0.1:$HTTP_PORT"

bash ci/smoke-mounted.sh
