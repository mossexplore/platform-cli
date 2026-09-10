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
[[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ && "$revision" =~ ^[a-f0-9]{40}$ ]] || {
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
import json, os
from pathlib import Path
out = Path(os.environ['OUTPUT_DIR'])
metadata = {key.lower(): os.environ[key] for key in (
    'IMAGE_REFERENCE', 'IMAGE_ID', 'IMAGE_TAG', 'IMAGE_FILE', 'IMAGE_VERSION', 'IMAGE_REVISION')}
metadata['platform'] = 'linux/amd64'
(out/'manifest.json').write_text(json.dumps(metadata, indent=2)+'\n')
template = Path('docs/权限管理系统Docker离线导入与运行.md').read_text()
for key, value in metadata.items():
    template = template.replace('{{'+key+'}}', value)
(out/'README.md').write_text(template)
PY
(cd "$OUTPUT_DIR" && sha256sum "$filename" service.env.example manifest.json README.md > SHA256SUMS)
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
