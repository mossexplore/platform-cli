"""Build the standalone Windows ZIP and its local-installable DSH bundle."""
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


def build(output, revision=None, *, new_output_directory=False, verbose=False):
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

    progress(f"[3/5] Build the {stem} bundle")
    packaged = bundle(package)

    progress("[4/5] Generate release metadata and SHA256 checksums")
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

    progress("[5/5] Write the Windows offline ZIP")
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    zip_name = f"{stem}-windows.zip"
    with tempfile.TemporaryDirectory(dir=output) as work:
        candidate = Path(work) / zip_name
        with zipfile.ZipFile(candidate, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(files.items()):
                entry = zipfile.ZipInfo(name)
                entry.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(entry, data)
        directory = create_build_directory(output) if new_output_directory else output
        path = directory / zip_name
        candidate.replace(path)
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--revision", help="full Git commit SHA, defaults to local HEAD")
    parser.add_argument("--new-output-directory", action="store_true", help="use a separate directory for each ZIP")
    parser.add_argument("--verbose", action="store_true", help="print packaging stages")
    args = parser.parse_args()
    try:
        path = build(args.output, args.revision, new_output_directory=args.new_output_directory, verbose=args.verbose)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Build error: {error}\n")
    print(path)
