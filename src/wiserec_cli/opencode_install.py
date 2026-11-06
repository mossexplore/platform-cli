"""Internal installer for bundled agent resources; no CLI command registration."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import tempfile

from . import messages as msg


RESOURCE_ROOT = Path(__file__).with_name("opencode_resources")
SKILLS = ("wiserec-platform",)
COMMANDS = ("ml",)
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


def install_resources(
    target: Path, source: Path = RESOURCE_ROOT, *, skills_target: Path | None = None,
) -> None:
    """Validate before deletion, then replace only the selected owned resources."""
    skills_target = skills_target if skills_target is not None else target

    def destination_for(relative):
        root = skills_target if relative.startswith("skills/") else target
        return root / relative

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
        owned = [destination_for(relative) for relative in OWNED]
        # Refuse redirected parent directories; do not delete unrelated resources.
        parents = [target, target / "commands", skills_target, skills_target / "skills"]
        for parent in parents:
            if parent.is_symlink():
                raise ValueError(f"Resource directory must not be a symlink: {parent}")
        replacement_started = False
        try:
            for destination in owned:
                _remove(destination)
            replacement_started = True
            for relative, destination in zip(OWNED, owned):
                destination.parent.mkdir(parents=True, exist_ok=True)
                origin = staged / relative
                if origin.is_dir():
                    shutil.copytree(origin, destination)
                else:
                    shutil.copyfile(origin, destination)
            for relative, digest in manifest.items():
                if hashlib.sha256(destination_for(relative).read_bytes()).hexdigest() != digest:
                    raise ValueError(f"Installed resource checksum failed: {relative}")
            # 只清理历史受管理的 lab 副本；共享目录和旧 OpenCode 目录均覆盖。
            for root in {target, skills_target}:
                remove_retired_lab(root)
        except Exception:
            if replacement_started:
                for destination in owned:
                    _remove(destination)
            raise


def remove_retired_lab(root: Path) -> None:
    """安装成功后清理废弃详细版，拒绝沿父目录符号链接删除。"""
    for parent in (root, root / "skills", root / "commands"):
        if parent.is_symlink():
            raise ValueError(f"Retired resource directory must not be a symlink: {parent}")
    _remove(root / "skills/wiserec-platform-detailed")
    _remove(root / "commands/ml-lab.md")


def remove_legacy_skills(target: Path, skills_target: Path) -> None:
    """Remove only old managed skills after the shared installation succeeds."""
    if target.resolve() == skills_target.resolve():
        return
    for parent in (target, target / "skills"):
        if parent.is_symlink():
            raise ValueError(f"Legacy resource directory must not be a symlink: {parent}")
    for name in SKILLS:
        _remove(target / "skills" / name)


def main() -> int:
    target = Path(os.environ.get("OPENCODE_CONFIG_DIR") or Path.home() / ".config/opencode")
    shared_target = Path.home() / ".agents"
    cac_target = Path.home() / ".cac"
    msg.detail("WiseRec skill and /ml command are replaced on every installation; do not edit these files.")
    failed = False
    for label, directory, skills_directory in (
        ("OpenCode", target, shared_target), ("codeagent", cac_target, cac_target),
    ):
        msg.detail(f"{label} resource directory: {directory}")
        for name in SKILLS:
            msg.detail(f"{label} skill directory: {skills_directory / 'skills' / name}")
        for name in COMMANDS:
            msg.detail(f"{label} /{name} command file: {directory / 'commands' / (name + '.md')}")
        try:
            install_resources(directory, skills_target=skills_directory)
            if label == "OpenCode":
                remove_legacy_skills(directory, skills_directory)
        except Exception as error:
            failed = True
            msg.warning(f"{label} resource installation failed: {error}")
        else:
            msg.success(f"{label} resources installed.")
    if failed:
        msg.detail("CLI remains usable. Rerun the official installer to retry.")
        return 1
    msg.success("WiseRec skill and /ml command installed in both directories. Reopen your agent session.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
