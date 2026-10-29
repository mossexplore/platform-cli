"""Internal installer for bundled agent resources; no CLI command registration."""

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from . import messages as msg


RESOURCE_ROOT = Path(__file__).with_name("opencode_resources")
SKILLS = ("wiserec-platform", "wiserec-platform-detailed")
COMMANDS = ("ml", "ml-lab")
OWNED = tuple(f"skills/{name}" for name in SKILLS) + tuple(
    f"commands/{name}.md" for name in COMMANDS)
REQUIRED = {f"skills/{name}/SKILL.md" for name in SKILLS} | {
    f"commands/{name}.md" for name in COMMANDS}


def _allowed(relative: str) -> bool:
    path = PurePosixPath(relative)
    return ("\\" not in relative and not path.is_absolute()
            and ".." not in path.parts and path.as_posix() == relative
            and (relative in REQUIRED or (path.suffix == ".md" and any(
                relative.startswith(f"skills/{name}/references/") for name in SKILLS))))


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def install_resources(target: Path, source: Path = RESOURCE_ROOT) -> None:
    """Validate before deletion, then replace only the selected owned resources."""
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not REQUIRED.issubset(manifest):
        raise ValueError("Incomplete OpenCode resource manifest")
    with tempfile.TemporaryDirectory(prefix="wiserec-opencode-") as temporary:
        staged = Path(temporary)
        for relative, digest in manifest.items():
            if not _allowed(relative):
                raise ValueError("Invalid OpenCode resource path")
            data = (source / relative).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"OpenCode resource checksum failed: {relative}")
            destination = staged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        owned = [target / relative for relative in OWNED]
        # Refuse redirected parent directories; do not delete unrelated resources.
        parents = [target, target / "skills", target / "commands"]
        for parent in parents:
            if parent.is_symlink():
                raise ValueError(f"Resource directory must not be a symlink: {parent}")
        replacement_started = False
        try:
            for destination in owned:
                _remove(destination)
            replacement_started = True
            for destination in owned:
                destination.parent.mkdir(parents=True, exist_ok=True)
                origin = staged / destination.relative_to(target)
                if origin.is_dir():
                    shutil.copytree(origin, destination)
                else:
                    shutil.copyfile(origin, destination)
            for relative, digest in manifest.items():
                if hashlib.sha256((target / relative).read_bytes()).hexdigest() != digest:
                    raise ValueError(f"Installed resource checksum failed: {relative}")
        except Exception:
            if replacement_started:
                for destination in owned:
                    _remove(destination)
            raise


def main() -> int:
    target = Path(os.environ.get("OPENCODE_CONFIG_DIR") or Path.home() / ".config/opencode")
    cac_target = Path.home() / ".cac"
    msg.detail("WiseRec skills and /ml, /ml-lab commands are replaced on every installation; do not edit these files.")
    failed = False
    for label, directory in (
        ("OpenCode", target), ("codeagent", cac_target),
    ):
        msg.detail(f"{label} resource directory: {directory}")
        for name in SKILLS:
            msg.detail(f"{label} skill directory: {directory / 'skills' / name}")
        for name in COMMANDS:
            msg.detail(f"{label} /{name} command file: {directory / 'commands' / (name + '.md')}")
        try:
            install_resources(directory)
        except Exception as error:
            failed = True
            msg.warning(f"{label} resource installation failed: {error}")
        else:
            msg.success(f"{label} resources installed.")
    if failed:
        msg.detail("CLI remains usable. Rerun the official installer to retry.")
        return 1
    msg.success("WiseRec skills and /ml, /ml-lab commands installed in both directories. Reopen your agent session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
