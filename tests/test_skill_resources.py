"""OpenCode skill 内容与当前命令树、打包范围保持一致。"""

from pathlib import Path
import re
import runpy

import click

SCRIPT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/sync_skill_index.py"))
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
    missing = [" ".join(path) for path in _leaf_paths(SCRIPT["go_cli_tree"]())
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


def test_only_formal_skill_has_an_active_entry():
    root = SKILL_DIR.parents[1]
    assert not (root / 'skill/commands/ml-lab.md').exists()
    from wiserec_cli.opencode_install import SKILLS, COMMANDS
    assert SKILLS == ('wiserec-platform',)
    assert COMMANDS == ('ml',)


def test_slash_commands_load_separate_skills():
    directory = SKILL_DIR.parent / 'commands'
    for command, skill in [('ml', 'wiserec-platform')]:
        content = (directory / f'{command}.md').read_text()
        assert f'先通过 skill 工具加载 `{skill}`' in content
        assert '$ARGUMENTS' in content


def test_packaged_kb_matches_build_configuration(tmp_path):
    root = SKILL_DIR.parents[1]
    stage = runpy.run_path(str(root / "scripts/stage_skill_resources.py"))["stage_skill_resources"]
    for enabled in (True, False):
        resources = tmp_path / str(enabled)
        manifest = stage(root, resources, "test", kb_enabled=enabled)
        package = resources / "skills/wiserec-platform"
        assert (package / "references/kb.md").exists() == enabled
        assert ("skills/wiserec-platform/references/kb.md" in manifest) == enabled
        assert ("references/kb.md" in (package / "SKILL.md").read_text()) == enabled
        commands = (package / "references/commands.md").read_text()
        for command in ("ml kb search", "ml kb file list", "ml kb file download"):
            assert (command in commands) == enabled


def test_crlf_checkout_stages_identical_skill_bytes(tmp_path):
    import shutil
    import hashlib
    import json

    root = SKILL_DIR.parents[1]
    stage = runpy.run_path(str(root / "scripts/stage_skill_resources.py"))["stage_skill_resources"]
    checkout = tmp_path / "checkout"
    shutil.copytree(root / "skill", checkout / "skill")
    for doc in (checkout / "skill").rglob("*.md"):
        doc.write_bytes(doc.read_text(encoding="utf-8").replace("\n", "\r\n").encode())
    for enabled in (True, False):
        target = tmp_path / f"crlf-{enabled}"
        expected = stage(root, tmp_path / f"baseline-{enabled}", "test", enabled)
        assert stage(checkout, target, "test", enabled) == expected
        manifest = json.loads((target / "manifest.json").read_bytes())
        assert manifest == {path: hashlib.sha256((target / path).read_bytes()).hexdigest()
                            for path in expected}
