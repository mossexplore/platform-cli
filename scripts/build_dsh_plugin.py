"""Build a local-installable DSH bundle, optionally wrapped in the legacy ZIP."""
import argparse
from datetime import datetime
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
from uuid import uuid4
import zipfile

from sync_versions import read_versions, sync


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "dsh-plugin/wiserec-cli"


def digest(content):
    return hashlib.sha256(content).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def bundle(manifest, metadata=None):
    files = {}
    for name in ["package.json", *manifest["files"]]:
        source = ROOT / name if name == "LICENSE" else PLUGIN / name
        files[name] = source.read_bytes()
    if metadata is not None:
        files["release.json"] = json_bytes(metadata)

    content = io.BytesIO()
    with gzip.GzipFile(fileobj=content, mode="wb", mtime=0) as compressed:
        with tarfile.open(fileobj=compressed, mode="w") as archive:
            for name, data in sorted(files.items()):
                entry = tarfile.TarInfo(f"package/{name}")
                entry.size = len(data)
                archive.addfile(entry, io.BytesIO(data))
    return content.getvalue()


def source_revision():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--verify", "HEAD"], cwd=ROOT, text=True,
        ).strip()
    except (FileNotFoundError, subprocess.CalledProcessError) as error:
        raise ValueError("Git could not read HEAD. Use a Git checkout with Git on PATH.") from error


def create_build_directory(output):
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    while True:
        directory = output / f"dsh-{timestamp}-{uuid4().hex[:8]}"
        try:
            directory.mkdir()
        except FileExistsError:
            continue
        return directory


def write_legacy_zip(path, bundle_name, packaged, metadata):
    files = {
        bundle_name: packaged,
        "release.json": json_bytes({**metadata, "bundle_sha256": digest(packaged)}),
        "README.md": (PLUGIN / "README.md").read_bytes(),
        "stage-wiserec-dsh-plugin.ps1": (PLUGIN / "stage-wiserec-dsh-plugin.ps1").read_bytes(),
    }
    files["SHA256SUMS"] = "".join(f"{digest(data)}  {name}\n" for name, data in sorted(files.items())).encode()
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            entry = zipfile.ZipInfo(name)
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data)


def build(output, revision=None, *, bundle_only=False, new_output_directory=False, verbose=False):
    def progress(message):
        if verbose:
            print(message, flush=True)

    progress("[1/5] Read the source commit")
    if revision is None:
        revision = source_revision()
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("source revision must be the full commit SHA")
    progress(f"      Git commit: {revision}")

    progress("[2/5] Check component and package versions")
    sync(ROOT, check=True)
    versions, _ = read_versions(ROOT)
    package = json.loads((PLUGIN / "package.json").read_text(encoding="utf-8"))
    stem = f"dsh-wiserec-cli-{versions['dsh_plugin']}"
    bundle_name = f"{stem}.tgz"

    progress("[3/5] Prepare release metadata")
    metadata = {
        "version": versions["dsh_plugin"],
        "cli_version": versions["cli_go"],
        "cli_protocol": "dsh-keepalive-v1",
        "dsh_version": package["engines"]["dsh"],
        "platform": "windows-x64",
        "revision": revision,
    }

    progress(f"[4/5] Build the {bundle_name} plugin bundle")
    packaged = bundle(package, metadata if bundle_only else None)

    filename = bundle_name if bundle_only else f"{stem}-windows.zip"
    progress(f"[5/5] Write {filename}")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as work:
        candidate = Path(work) / filename
        if bundle_only:
            candidate.write_bytes(packaged)
        else:
            write_legacy_zip(candidate, bundle_name, packaged, metadata)
        directory = create_build_directory(output) if new_output_directory else output
        path = directory / filename
        candidate.replace(path)
    if bundle_only:
        progress(f"SHA256: {digest(packaged)}")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", help="full Git commit SHA, defaults to local HEAD")
    parser.add_argument("--bundle-only", action="store_true", help="write the installable .tgz directly")
    parser.add_argument("--new-output-directory", action="store_true", help="use a separate directory for each build")
    parser.add_argument("--verbose", action="store_true", help="print packaging stages")
    args = parser.parse_args()
    try:
        path = build(args.output, args.revision, bundle_only=args.bundle_only,
                     new_output_directory=args.new_output_directory, verbose=args.verbose)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Build error: {error}\n")
    print(path)
