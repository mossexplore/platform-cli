"""Build the standalone Windows ZIP and its local-installable DSH bundle."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import zipfile

from sync_versions import read_versions, sync


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "dsh-plugin/wiserec-cli"


def digest(content):
    return hashlib.sha256(content).hexdigest()


def bundle(manifest):
    content = io.BytesIO()
    with gzip.GzipFile(fileobj=content, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name in sorted(["package.json", *manifest["files"]]):
                source = ROOT / name if name == "LICENSE" else PLUGIN / name
                data = source.read_bytes()
                entry = tarfile.TarInfo(f"package/{name}")
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
    return content.getvalue()


def build(output, revision):
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("source revision must be the full commit SHA")
    sync(ROOT, check=True)
    versions, _ = read_versions(ROOT)
    package = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))
    stem = f"dsh-wiserec-cli-{versions['dsh_plugin']}"
    packaged = bundle(package)
    metadata = {
        "version": versions["dsh_plugin"],
        "cli_version": versions["cli_go"],
        "cli_protocol": "dsh-keepalive-v1",
        "dsh_version": package["engines"]["dsh"],
        "platform": "windows-x64",
        "revision": revision,
        "bundle_sha256": digest(packaged),
    }
    files = {
        f"{stem}.tgz": packaged,
        "release.json": (json.dumps(metadata, indent=2) + "\n").encode(),
        "README.md": (PLUGIN / "README.md").read_bytes(),
        "stage-wiserec-dsh-plugin.ps1": (PLUGIN / "stage-wiserec-dsh-plugin.ps1").read_bytes(),
    }
    files["SHA256SUMS"] = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(files.items())).encode()
    output.mkdir(parents=True, exist_ok=True)
    path = output / f"{stem}-windows.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name)
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    print(build(args.output, args.revision))
