#!/usr/bin/env bash
# Called by smoke.sh after its database has been seeded.
set -euo pipefail
: "${CLI_ACCESS_IMAGE:?}"
: "${COMPOSE_PROJECT_NAME:?}"
config_dir=$(mktemp -d)
container="${COMPOSE_PROJECT_NAME}-mounted"
cleanup() {
  docker logs "$container" >> "${RUNNER_TEMP:-/tmp}/cli-access-smoke.log" 2>&1 || true
  docker rm -f "$container" >/dev/null 2>&1 || true
  rm -rf "$config_dir"
}
trap cleanup EXIT
cat > "$config_dir/service.env" <<'CONFIG'
DATABASE_URL=mysql+pymysql://ci:ci-test-only@mysql:3306/cli_access?charset=utf8mb4
COOKIE_SECURE=false
LISTEN_PORT=8008
CONFIG
chmod 755 "$config_dir"
chmod 644 "$config_dir/service.env"
args=(--network "${COMPOSE_PROJECT_NAME}_default" -v "$config_dir:/run/cli-access:ro"
  --read-only --tmpfs /tmp:size=64m,mode=1777 --cap-drop ALL
  --security-opt no-new-privileges:true)
docker run --rm "${args[@]}" "$CLI_ACCESS_IMAGE" python -m app.manage migrate
docker run -d --name "$container" "${args[@]}" -p 127.0.0.1:18009:8008 -p 127.0.0.1:18010:8009 "$CLI_ACCESS_IMAGE"
# The password must not be present in the Docker container environment metadata.
if docker inspect --format '{{json .Config.Env}}' "$container" | grep -q 'ci-test-only'; then
  echo 'Mounted database password leaked into Docker environment metadata' >&2
  exit 1
fi
wait_healthy() {
  for attempt in {1..60}; do
    if [[ $(docker inspect --format '{{.State.Health.Status}}' "$container") == healthy ]]; then
      return 0
    fi
    sleep 2
  done
  echo 'Mounted service did not become healthy' >&2
  return 1
}
wait_healthy
python ci/smoke.py http://127.0.0.1:18009
# Replace the file atomically to verify a directory mount picks up edits on restart.
sed 's/LISTEN_PORT=8008/LISTEN_PORT=8009/' "$config_dir/service.env" > "$config_dir/new.env"
echo 'HEALTHCHECK_URL=http://127.0.0.1:8009/cli-permission/healthz' >> "$config_dir/new.env"
mv "$config_dir/new.env" "$config_dir/service.env"
docker restart "$container"
wait_healthy
python ci/smoke.py http://127.0.0.1:18010
