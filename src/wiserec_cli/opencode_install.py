"""Internal installer for bundled OpenCode resources; no CLI command registration."""

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
    OpenCodeConflictError,
    OpenCodeVersionError,
    detect_permission_format,
    install_opencode_permissions,
    preflight_opencode_permissions,
    uninstall_opencode_permissions,
    validate_opencode_config,
)


RESOURCE_ROOT = Path(__file__).with_name("opencode_resources")


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def install_resources(target: Path, source: Path = RESOURCE_ROOT) -> None:
    """Validate before deletion, then replace only the two owned resources."""
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
        for parent in (target, target / "skills", target / "commands"):
            if parent.is_symlink():
                raise ValueError(f"OpenCode directory must not be a symlink: {parent}")
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
    override_conflicts = False
    if args == ["--override-conflicts"]:
        override_conflicts = True
    elif args:
        msg.warning("Usage: python -m wiserec_cli.opencode_install [--uninstall] [--override-conflicts]")
        return 2
    msg.detail(f"OpenCode resource directory: {target}")
    msg.detail("WiseRec skill and /ml command are replaced on every installation; do not edit these files.")
    msg.detail(
        "OpenCode permission rules are merged into opencode.json. Other settings are kept. "
        "The shell * ask rule applies to every shell command, not only ml."
    )
    try:
        rule_format = detect_permission_format()
    except OpenCodeVersionError as error:
        msg.error(str(error))
        return 1
    try:
        validate_opencode_config(target)
        preflight_opencode_permissions(
            target,
            rule_format=rule_format,
            override_conflicts=override_conflicts,
        )
    except OpenCodeConflictError as error:
        msg.error(str(error))
        msg.detail("opencode.json was left unchanged. CLI remains usable. Rerun the official installer to retry.")
        return 1
    except Exception as error:
        msg.error(f"OpenCode permission installation failed: {error}")
        msg.detail("opencode.json was left unchanged. CLI remains usable. Rerun the official installer to retry.")
        return 1
    try:
        install_resources(target)
    except Exception as error:
        msg.warning(f"OpenCode resource installation failed: {error}")
        msg.detail("CLI remains usable. Rerun the official installer to retry.")
        return 1
    try:
        install_opencode_permissions(
            target,
            rule_format=rule_format,
            override_conflicts=override_conflicts,
        )
    except OpenCodeConflictError as error:
        msg.error(str(error))
        msg.detail("opencode.json was left unchanged. CLI remains usable. Rerun the official installer to retry.")
        return 1
    except Exception as error:
        msg.warning(f"OpenCode permission installation failed: {error}")
        msg.detail("opencode.json was left unchanged. CLI remains usable. Rerun the official installer to retry.")
        return 1
    msg.success("OpenCode skill, /ml command, and permission rules installed. Reopen your OpenCode session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
