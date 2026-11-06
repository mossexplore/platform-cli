#!/usr/bin/env bash
# Export an existing immutable image; never rebuild it or embed live credentials.
set -euo pipefail
: "${IMAGE_REFERENCE:?Set IMAGE_REFERENCE to a ghcr.io image digest}"
: "${OUTPUT_DIR:?Set OUTPUT_DIR to a new export directory}"
[[ "$IMAGE_REFERENCE" =~ ^ghcr\.io/[a-z0-9._-]+/cli-access@sha256:[a-f0-9]{64}$ ]] || {
  echo 'Expected immutable cli-access GHCR digest' >&2; exit 1;
}
source_dir=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR=$(cd "$OUTPUT_DIR" && pwd)
export OUTPUT_DIR
[[ -z "$(ls -A "$OUTPUT_DIR")" ]] || { echo 'Export directory must be empty' >&2; exit 1; }
docker pull --platform linux/amd64 "$IMAGE_REFERENCE"
image_id=$(docker image inspect --format '{{.Id}}' "$IMAGE_REFERENCE")
version=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.version"}}' "$IMAGE_REFERENCE")
revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$IMAGE_REFERENCE")
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+(\.[0-9]+)?$ && "$revision" =~ ^[a-f0-9]{40}$ ]] || {
  echo 'Missing valid version/revision labels' >&2; exit 1;
}
[[ $(docker image inspect --format '{{.Os}}/{{.Architecture}}' "$IMAGE_REFERENCE") == linux/amd64 ]]
tag="cli-access:$version-${revision:0:12}"
filename="cli-access-$version-${revision:0:12}-linux-amd64.tar.gz"
if [[ "${FORMAL_RELEASE:-false}" == true ]]; then
  tag="cli-access:$version"
  filename="cli-access-$version-linux-amd64.tar.gz"
fi
docker tag "$IMAGE_REFERENCE" "$tag"
docker save "$tag" | gzip -n > "$OUTPUT_DIR/$filename"
# Verify the actual download format can be loaded back without registry access.
docker image rm "$tag"
docker load -i "$OUTPUT_DIR/$filename"
[[ $(docker image inspect --format '{{.Id}}' "$tag") == "$image_id" ]]
[[ $(docker run --rm --pull=never --network none "$tag" python -c 'import os; print(os.getuid())') == 10001 ]]
cp "$source_dir/docker/service.env.example" "$OUTPUT_DIR/service.env.example"
export IMAGE_REFERENCE IMAGE_ID="$image_id" IMAGE_TAG="$tag" IMAGE_FILE="$filename" IMAGE_VERSION="$version" IMAGE_REVISION="$revision"
python - <<'PY'
import json, os, subprocess
from pathlib import Path
out = Path(os.environ['OUTPUT_DIR'])
metadata = {key.lower(): os.environ[key] for key in (
    'IMAGE_REFERENCE', 'IMAGE_ID', 'IMAGE_TAG', 'IMAGE_FILE', 'IMAGE_VERSION', 'IMAGE_REVISION')}
metadata['platform'] = 'linux/amd64'
(out/'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
# Always use documents from the exported image's exact source commit.
def source_text(relative):
    return subprocess.check_output(['git', 'show', metadata['image_revision'] + ':' + relative]).decode('utf-8')

def rendered(text):
    for key, value in metadata.items():
        text = text.replace('{{'+key+'}}', value)
    return text

(out/'service.env.example').write_text(source_text('access-service/docker/service.env.example'))
(out/'README.md').write_text(rendered(source_text('docs/权限管理系统Docker离线导入与运行.md')))
runbook = source_text('docs/权限管理系统Docker安装部署与调试指南.md')
runbook = runbook.replace('cli-access:' + metadata['image_version'], metadata['image_tag'])
runbook = runbook.replace('cli-access-' + metadata['image_version'] + '-linux-amd64.tar.gz', metadata['image_file'])
runbook = runbook.replace('权限管理系统结构12升级至' + metadata['image_version'] + '指南.md', 'Docker-upgrade-' + metadata['image_version'] + '.md')
(out/'Docker-runbook.md').write_text(runbook)
files = subprocess.check_output(['git', 'ls-tree', '-rz', '--name-only', metadata['image_revision'], 'docs']).decode().split('\0')
guides = [name for name in files if name.endswith('升级至' + metadata['image_version'] + '指南.md')]
if len(guides) > 1:
    raise RuntimeError('More than one upgrade guide for target image')
for guide in guides:
    text = source_text(guide)
    text = text.replace('cli-access:' + metadata['image_version'], metadata['image_tag'])
    text = text.replace('cli-access-' + metadata['image_version'] + '-linux-amd64.tar.gz', metadata['image_file'])
    (out/('Docker-upgrade-' + metadata['image_version'] + '.md')).write_text(text)
notes = 'docs/ACCESS_RELEASE_NOTES_' + metadata['image_version'] + '.md'
if notes in files:
    notes_text = source_text(notes)
    migration_notes = 'docs/环境禁止命令开发与迁移说明.md'
    if migration_notes in files:
        (out/'Migration-notes.md').write_text(source_text(migration_notes))
        notes_text = notes_text.replace('环境禁止命令开发与迁移说明.md', 'Migration-notes.md')
    (out/'RELEASE_NOTES.md').write_text(notes_text)
metadata['export_run_id'] = os.environ.get('GITHUB_RUN_ID', '')
metadata['documents_source_revision'] = metadata['image_revision']
(out/'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
PY
(cd "$OUTPUT_DIR" && find . -maxdepth 1 -type f ! -name SHA256SUMS -printf '%f\n' | sort | xargs sha256sum > SHA256SUMS)
if [[ -n "${GITHUB_STEP_SUMMARY:-}" ]]; then
  {
    echo '### Offline Docker download'
    echo "Source: \`$IMAGE_REFERENCE\`"
    echo "Loaded tag: \`$tag\`"
    echo "File: \`$filename\` (linux/amd64)"
    echo 'Download the offline-image artifact, unzip it, then follow README.md.'
    echo 'Archive SHA256 and image ID are recorded separately; neither is the registry index digest.'
  } >> "$GITHUB_STEP_SUMMARY"
fi
