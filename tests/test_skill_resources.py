"""OpenCode skill 内容与当前命令树、打包范围保持一致。"""

from pathlib import Path
import re

import click
import typer

from wiserec_cli.cli import app

SKILL_DIR = Path(__file__).resolve().parents[1] / "skill" / "wiserec-platform"
REFERENCES = SKILL_DIR / "references"
LINK = re.compile(r"\]\(([^)#\s]+)(?:#[^)]*)?\)")


def _leaf_paths(group: click.Group, prefix: tuple[str, ...] = ()) -> list[tuple[str, ...]]:
    paths = []
    for name, command in sorted(group.commands.items()):
        if isinstance(command, click.Group):
            paths += _leaf_paths(command, prefix + (name,))
        else:
            paths.append(prefix + (name,))
    return paths


def _indexed(path: tuple[str, ...], lines: list[str]) -> bool:
    full = "ml " + " ".join(path)
    parent = " ".join(("ml",) + path[:-1]) + " "
    leaf = re.compile(rf"`{re.escape(path[-1])}[` ]")
    return any(re.search(rf"{re.escape(full)}(?![\w-])", line)
               or (parent in line and leaf.search(line)) for line in lines)


def test_command_index_covers_every_command():
    lines = (REFERENCES / "commands.md").read_text(encoding="utf-8").splitlines()
    missing = [" ".join(path) for path in _leaf_paths(typer.main.get_command(app))
               if not _indexed(path, lines)]
    assert not missing, f"commands.md 缺少命令: {missing}"


def test_skill_links_resolve_to_packaged_files():
    packaged = {SKILL_DIR / "SKILL.md", *REFERENCES.glob("*.md")}
    for document in packaged:
        for target in LINK.findall(document.read_text(encoding="utf-8")):
            if "://" in target:
                continue
            resolved = (document.parent / target).resolve()
            assert resolved in packaged, f"{document.name} 链接到未随包安装的 {target}"


def test_every_reference_is_reachable_from_skill():
    skill = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")
    for reference in REFERENCES.glob("*.md"):
        assert f"](references/{reference.name})" in skill


def test_skill_name_matches_directory():
    header = (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8").split("---")[1]
    assert re.search(r"^name: (\S+)$", header, re.M).group(1) == SKILL_DIR.name
