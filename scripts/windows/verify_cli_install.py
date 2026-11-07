"""Remove verified editable installs and verify the CLI Wheel installation."""

import argparse
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import re
import site
import subprocess
import sys
import sysconfig


PACKAGE = "wiserec-cli"
EDITABLE_FILE = re.compile(
    r"__editable__\.wiserec_cli-[\w.+!-]+\.pth|"
    r"__editable___wiserec_cli_[\w]+_finder\.py"
)


def package_distributions(roots):
    return [
        dist for dist in metadata.distributions(path=[str(root) for root in roots])
        if re.sub(r"[-_.]+", "-", dist.metadata.get("Name", "")).lower() == PACKAGE
    ]


def is_editable(dist):
    direct_url = dist.read_text("direct_url.json")
    return bool(direct_url and json.loads(direct_url).get("dir_info", {}).get("editable"))


def editable_files(roots):
    return [path for root in roots for path in root.iterdir() if EDITABLE_FILE.fullmatch(path.name)]


def cleanup(roots):
    installed = package_distributions(roots)
    editable = [dist for dist in installed if is_editable(dist)]
    if editable:
        if len(installed) != 1:
            raise ValueError("Multiple wiserec-cli installs found alongside an editable install. "
                             f"Resolve the conflicting installations in: {', '.join(map(str, roots))}")
        active = metadata.distribution(PACKAGE)
        if (not is_editable(active)
                or Path(active.locate_file("")).resolve() != Path(editable[0].locate_file("")).resolve()):
            raise ValueError("The active wiserec-cli does not match the detected editable installation")
        # Use pip's RECORD to remove this distribution and its launcher.
        subprocess.run([sys.executable, "-E", "-m", "pip", "uninstall", "--yes", PACKAGE], check=True)
        if any(is_editable(dist) for dist in package_distributions(roots)):
            raise ValueError(f"Editable wiserec-cli metadata remains in: {', '.join(map(str, roots))}")
    for path in editable_files(roots):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"Cannot safely remove editable install artifact: {path}")
        path.unlink()


def verify(roots, version):
    installed = package_distributions(roots)
    if len(installed) != 1 or is_editable(installed[0]) or editable_files(roots):
        raise ValueError("Expected one non-editable wiserec-cli installation without editable artifacts")
    dist = installed[0]
    import wiserec_cli
    expected = Path(dist.locate_file("wiserec_cli/__init__.py")).resolve()
    if (dist.read_text("WHEEL") is None or dist.version != version
            or wiserec_cli.__version__ != version or Path(wiserec_cli.__file__).resolve() != expected):
        raise ValueError(f"Expected wiserec-cli {version} from Wheel at {expected}")


def verify_launcher(launcher, version):
    executable = str(Path(launcher).resolve())
    environment = {**os.environ, "PYTHONIOENCODING": "utf-8", "ML_HISTORY": "0"}
    args = dict(check=True, stdout=subprocess.PIPE, encoding="utf-8", env=environment)
    actual = subprocess.run([executable, "--version"], **args).stdout.strip()
    if actual != f"ml {version}":
        raise ValueError(f"Unexpected CLI version: {actual}")
    context = subprocess.run([executable, "context", "--json"], **args).stdout
    expected = (Path(os.environ["APPDATA"]) / "ml" / "config.json").resolve()
    actual_config = Path(json.loads(context)["配置路径"]).resolve()
    if actual_config != expected:
        raise ValueError(f"Unexpected configuration path: {actual_config}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["cleanup", "verify", "verify-launcher"])
    parser.add_argument("--version")
    parser.add_argument("--launcher")
    args = parser.parse_args()
    paths = sysconfig.get_paths()
    roots = {Path(paths[key]).resolve() for key in ("purelib", "platlib")}
    if sys.prefix == sys.base_prefix:
        roots.add(Path(site.getusersitepackages()).resolve())
    roots = sorted(path for path in roots if path.is_dir())
    try:
        if args.action == "cleanup":
            cleanup(roots)
        elif args.action == "verify":
            verify(roots, args.version)
        else:
            verify_launcher(args.launcher, args.version)
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"{exc}\n")


if __name__ == "__main__":
    main()
