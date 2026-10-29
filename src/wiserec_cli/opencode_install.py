"""Internal installer for bundled agent resources; no CLI command registration."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from . import messages as msg
from .opencode_permissions import (
    OpenCodeVersionError,
    detect_permission_format,
    install_opencode_permissions,
    preflight_opencode_permissions,
    rollback_opencode_permissions,
    uninstall_opencode_permissions,
    validate_opencode_config,
)


RESOURCE_ROOT = Path(__file__).with_name("opencode_resources")


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def install_resources(target: Path, source: Path | None = None) -> None:
    """Validate before deletion, then replace only the two owned resources."""
    source = RESOURCE_ROOT if source is None else source
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    required = {"commands/ml.md", "skills/wiserec-platform/SKILL.md"}
    if not isinstance(manifest, dict) or not required.issubset(manifest):
        raise ValueError("Incomplete OpenCode resource manifest")
    with tempfile.TemporaryDirectory(prefix="wiserec-opencode-") as temporary:
        staged = Path(temporary)
        for relative, digest in manifest.items():
            path = PurePosixPath(relative)
            if ("\\" in relative or path.is_absolute() or ".." in path.parts
                    or not (relative == "commands/ml.md"
                            or relative.startswith("skills/wiserec-platform/"))):
                raise ValueError("Invalid OpenCode resource path")
            data = (source / relative).read_bytes()
            if hashlib.sha256(data).hexdigest() != digest:
                raise ValueError(f"OpenCode resource checksum failed: {relative}")
            destination = staged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        owned = [target / "skills/wiserec-platform", target / "commands/ml.md"]
        # Refuse redirected parent directories; do not delete unrelated resources.
        parents = [target, target / "skills", target / "commands"]
        for parent in parents:
            if parent.is_symlink():
                raise ValueError(f"OpenCode directory must not be a symlink: {parent}")
        backup = Path(tempfile.mkdtemp(prefix="wiserec-opencode-backup-"))
        try:
            _preserve_previous(target, owned, backup)
            try:
                for destination in owned:
                    _remove(destination)
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
                _restore_previous(target, owned, backup)
                raise
        finally:
            shutil.rmtree(backup, ignore_errors=True)


def _preserve_previous(target: Path, owned: list, backup: Path) -> None:
    for destination in owned:
        if not destination.exists() and not destination.is_symlink():
            continue
        saved = backup / destination.relative_to(target)
        saved.parent.mkdir(parents=True, exist_ok=True)
        if destination.is_dir() and not destination.is_symlink():
            shutil.copytree(destination, saved)
        else:
            shutil.copyfile(destination, saved)


def _restore_previous(target: Path, owned: list, backup: Path) -> None:
    for destination in owned:
        _remove(destination)
        saved = backup / destination.relative_to(target)
        if not saved.exists() and not saved.is_symlink():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        if saved.is_dir() and not saved.is_symlink():
            shutil.copytree(saved, destination)
        else:
            shutil.copyfile(saved, destination)


_PERMISSION_NEXT = (
    "Nothing new was installed. An existing skill and /ml command were left unchanged. "
    "The WiseRec CLI remains usable. Fix the error above, then rerun the official installer."
)


def _announce_resources(label: str, directory: Path) -> None:
    msg.detail(f"{label} resource directory: {directory}")
    msg.detail(f"{label} skill directory: {directory / 'skills/wiserec-platform'}")
    msg.detail(f"{label} /ml command file: {directory / 'commands/ml.md'}")


def _codeagent_directory() -> Path:
    return Path.home() / ".cac"


def _owned_resources(directory: Path) -> list:
    return [directory / "skills/wiserec-platform", directory / "commands/ml.md"]


def _snapshot_codeagent() -> Path:
    """Remember the codeagent skill and /ml command from before this run."""
    directory = _codeagent_directory()
    backup = Path(tempfile.mkdtemp(prefix="wiserec-codeagent-backup-"))
    _preserve_previous(directory, _owned_resources(directory), backup)
    return backup


def _restore_codeagent(backup: Path) -> None:
    """Put the codeagent skill and /ml command back, or remove them if none existed."""
    directory = _codeagent_directory()
    _restore_previous(directory, _owned_resources(directory), backup)


def _install_codeagent_resources() -> bool:
    """Copy the skill and /ml command into ``~/.cac``. No OpenCode permission file."""
    directory = _codeagent_directory()
    _announce_resources("codeagent", directory)
    try:
        install_resources(directory)
    except Exception as error:
        msg.warning(f"codeagent resource installation failed: {error}")
        msg.detail("CLI remains usable. Rerun the official installer to retry.")
        return False
    msg.success("codeagent resources installed.")
    return True


def main(argv: list[str] | None = None) -> int:
    args = [] if argv is None else list(argv)
    target = Path(os.environ.get("OPENCODE_CONFIG_DIR") or Path.home() / ".config/opencode")
    if args == ["--uninstall"]:
        msg.detail(f"OpenCode resource directory: {target}")
        try:
            uninstall_opencode_permissions(target)
        except Exception as error:
            msg.error(f"OpenCode permission removal failed: {error}")
            msg.detail("opencode.json was left unchanged. CLI remains usable.")
            return 1
        msg.success("WiseRec OpenCode permission rules removed.")
        return 0
    if args:
        msg.warning("Usage: python -m wiserec_cli.opencode_install [--uninstall]")
        return 2
    _announce_resources("OpenCode", target)
    msg.detail("WiseRec skill and /ml command are replaced on every installation; do not edit these files.")
    msg.detail(
        "OpenCode permission rules are merged into opencode.json. Other settings are kept. "
        "The shell * ask rule applies to every shell command, not only ml."
    )
    # codeagent has no permission file. Copy it only after OpenCode rules and /ml succeed,
    # and put the previous copy back if this run fails after writing it.
    codeagent_backup = _snapshot_codeagent()
    try:
        result = _install_opencode_then_codeagent(target)
        if result != 0:
            _restore_codeagent(codeagent_backup)
        return result
    finally:
        shutil.rmtree(codeagent_backup, ignore_errors=True)


def _install_opencode_then_codeagent(target: Path) -> int:
    try:
        rule_format = detect_permission_format()
    except OpenCodeVersionError as error:
        msg.error(str(error))
        msg.detail("opencode.json was left unchanged.")
        msg.detail(_PERMISSION_NEXT)
        return 1
    try:
        validate_opencode_config(target)
        preflight_opencode_permissions(target, rule_format=rule_format)
        install_opencode_permissions(target, rule_format=rule_format)
    except Exception as error:
        msg.error(f"OpenCode permission installation failed: {error}")
        msg.detail("opencode.json was left unchanged or restored from the backup.")
        msg.detail(_PERMISSION_NEXT)
        return 1
    try:
        install_resources(target)
    except Exception as error:
        msg.error(f"OpenCode skill and /ml command installation failed: {error}")
        try:
            kept_manifest = rollback_opencode_permissions(target)
        except Exception as rollback_error:
            msg.detail(str(rollback_error))
            return 1
        if kept_manifest:
            manifest_note = "wiserec-managed.json was restored to its pre-install content."
        else:
            manifest_note = "wiserec-managed.json was removed."
        msg.detail(
            "Permission changes from this run were restored from the backup, "
            f"and {manifest_note} "
            "The previous OpenCode skill and /ml command were restored when a previous copy existed. "
            "The codeagent skill and /ml command were not installed, or were restored to the copy from before this run."
        )
        msg.detail(
            "Nothing new was left installed for OpenCode. An existing skill and /ml command were restored "
            "from the backup taken before replacement. "
            "The WiseRec CLI remains usable. Fix the error above, then rerun the official installer."
        )
        return 1
    if not _install_codeagent_resources():
        return 1
    msg.success(
        "OpenCode skill, /ml command, and permission rules installed. "
        "codeagent resources installed. Reopen your agent session."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
