"""Build a local-installable DSH bundle, optionally wrapped in the legacy ZIP."""
import argparse
from datetime import datetime
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
from uuid import uuid4
from urllib.parse import urlsplit
import zipfile

from sync_versions import read_versions, sync


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "dsh-plugin/wiserec-cli"
TELEMETRY_FILES = (
    "telemetry/index.js", "telemetry/collector.js", "telemetry/context.js",
    "telemetry/exporter.js", "telemetry/mapper.js", "telemetry/redact.js",
)


def digest(content):
    return hashlib.sha256(content).hexdigest()


def json_bytes(value):
    return (json.dumps(value, indent=2) + "\n").encode()


def plugin_files(manifest, settings, token):
    if not isinstance(settings, dict):
        raise ValueError("config.json must contain an object")
    build_config = settings.get("build", {})
    if not isinstance(build_config, dict):
        raise ValueError("build in config.json must be an object")
    include_telemetry = build_config.get("includeTelemetry", True)
    if not isinstance(include_telemetry, bool):
        raise ValueError("build.includeTelemetry must be a boolean")

    sources = {"LICENSE": ROOT / "LICENSE", "README.md": PLUGIN / "INSTALL.md"}
    files = {name: sources.get(name, PLUGIN / name).read_bytes() for name in manifest["files"]}
    files["config.json"] = json_bytes({key: value for key, value in settings.items() if key != "build"})
    if include_telemetry:
        files.update({name: (PLUGIN / name).read_bytes() for name in TELEMETRY_FILES})
        manifest = {
            **manifest,
            "files": [*manifest["files"], *TELEMETRY_FILES],
            "exports": {**manifest["exports"], "./telemetry": "./telemetry/index.js"},
        }
        files["cordis.patch.yml"] += telemetry_patch(build_config, token)
    files["package.json"] = json_bytes(manifest)
    return files, include_telemetry


def telemetry_patch(settings, token):
    endpoint = settings.get("telemetryEndpoint")
    try:
        if not isinstance(endpoint, str) or any(ord(c) <= 32 or c == "\\" for c in endpoint):
            raise ValueError
        parsed = urlsplit(endpoint)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.path != "/v1/traces" or "?" in endpoint or "#" in endpoint
                or parsed.port == 0):
            raise ValueError
    except ValueError:
        raise ValueError("build.telemetryEndpoint must be an absolute HTTP(S) URL ending in /v1/traces") from None
    if token and not re.fullmatch(r"[!-~]{1,1024}", token):
        raise ValueError("DSH_TELEMETRY_INGEST_TOKEN contains invalid characters or exceeds its limit")
    environments = settings.get("telemetryContentEnvironments", [])
    if not isinstance(environments, list) or len(environments) > 64 or any(
        not isinstance(env, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", env)
        for env in environments
    ):
        raise ValueError("build.telemetryContentEnvironments must be a list of environment names")
    if environments and parsed.scheme != "https":
        raise ValueError("telemetry content collection requires an HTTPS endpoint")
    return (
        "\n- id: session-telemetry-otel\n"
        "  disabled: true\n"
        "- insert:\n"
        "    - id: wiserec-cli-telemetry\n"
        "      name: dsh-wiserec-cli/telemetry\n"
        "      disabled: false\n"
        "      config:\n"
        '        mode: "full"\n'
        f"        endpoint: {json.dumps(endpoint)}\n"
        f"        contentEnvironments: {json.dumps(environments)}\n"
        + (f"        ingestToken: {json.dumps(token)}\n" if token else "")
    ).encode("utf-8")


def bundle(files, metadata):
    files = {**files, "release.json": json_bytes(metadata)}
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


def write_legacy_zip(path, bundle_name, packaged, metadata, readme):
    files = {
        bundle_name: packaged,
        "release.json": json_bytes({**metadata, "bundle_sha256": digest(packaged)}),
        "README.md": readme,
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
    settings = json.loads((PLUGIN / "config.json").read_text(encoding="utf-8-sig"))
    files, include_telemetry = plugin_files(package, settings, os.getenv("DSH_TELEMETRY_INGEST_TOKEN", ""))
    stem = f"dsh-wiserec-cli-{versions['dsh_plugin']}"
    bundle_name = f"{stem}.tgz"

    progress("[3/5] Prepare release metadata")
    progress(f"      includeTelemetry: {str(include_telemetry).lower()}")
    metadata = {
        "version": versions["dsh_plugin"],
        "cli_version": versions["cli_go"],
        "cli_protocol": "dsh-keepalive-v1",
        "dsh_version": package["engines"]["dsh"],
        "platform": "windows-x64",
        "revision": revision,
        "includeTelemetry": include_telemetry,
    }

    progress(f"[4/5] Build the {bundle_name} plugin bundle")
    packaged = bundle(files, metadata)

    filename = bundle_name if bundle_only else f"{stem}-windows.zip"
    progress(f"[5/5] Write {filename}")
    output = output.resolve()
    if not new_output_directory:
        output /= "complete" if include_telemetry else "keepalive"
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as work:
        candidate = Path(work) / filename
        if bundle_only:
            candidate.write_bytes(packaged)
        else:
            write_legacy_zip(candidate, bundle_name, packaged, metadata, files["README.md"])
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
