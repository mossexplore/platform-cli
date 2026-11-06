import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from wiserec_cli.opencode_install import install_resources, main, remove_legacy_skills


@pytest.fixture
def resources(tmp_path):
    source = tmp_path / "bundle"
    manifest = {}
    for relative in ("skills/wiserec-platform/SKILL.md",
                     "skills/wiserec-platform/references/session.md", "commands/ml.md"):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(relative, encoding="utf-8")
        manifest[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    (source / "manifest.json").write_text(json.dumps(manifest))
    return source


def test_reinstall_removes_old_and_modified_files(resources, tmp_path):
    target = tmp_path / "用户 配置"
    install_resources(target, resources)
    (target / "skills/wiserec-platform/old.md").write_text("obsolete")
    (target / "commands/ml.md").write_text("custom edit")
    unrelated = target / "commands/custom.md"
    unrelated.write_text("keep")
    install_resources(target, resources)
    assert not (target / "skills/wiserec-platform/old.md").exists()
    assert (target / "commands/ml.md").read_text() == "commands/ml.md"
    assert unrelated.read_text() == "keep"


def test_corrupt_bundle_does_not_delete_old_resources(resources, tmp_path):
    target = tmp_path / "config"
    install_resources(target, resources)
    (resources / "commands/ml.md").write_text("broken")
    with pytest.raises(ValueError, match="checksum"):
        install_resources(target, resources)
    assert (target / "commands/ml.md").read_text() == "commands/ml.md"


def test_copy_failure_cleans_partial_resources(resources, tmp_path):
    target = tmp_path / "config"
    install_resources(target, resources)
    with patch("wiserec_cli.opencode_install.shutil.copyfile", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            install_resources(target, resources)
    assert not (target / "commands/ml.md").exists()
    assert not (target / "skills/wiserec-platform").exists()
    assert not (target / 'skills/wiserec-platform-detailed').exists()
    assert not (target / 'commands/ml-lab.md').exists()


def test_failure_reports_cli_still_usable(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    with patch("wiserec_cli.opencode_install.install_resources", side_effect=PermissionError("denied")):
        assert main() == 1
    assert "CLI remains usable" in capsys.readouterr().err


def test_redirected_parent_is_not_modified(resources, tmp_path):
    target = tmp_path / "config"
    external = tmp_path / "external"
    external.mkdir()
    target.mkdir()
    (target / "skills").symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        install_resources(target, resources)
    assert list(external.iterdir()) == []


def test_codeagent_reinstall_updates_owned_resources_only(resources, tmp_path):
    target = tmp_path / ".cac"
    install_resources(target, resources)
    skill = target / "skills/wiserec-platform"
    (skill / "old.md").write_text("obsolete")
    other = target / "skills/other/SKILL.md"
    other.parent.mkdir()
    other.write_text("keep")
    commands = target / "commands"
    unrelated = commands / "custom.md"
    unrelated.write_text("keep command")
    (commands / "ml.md").write_text("custom command")
    install_resources(target, resources)
    assert not (skill / "old.md").exists()
    assert (skill / "references/session.md").read_bytes() == (
        resources / "skills/wiserec-platform/references/session.md"
    ).read_bytes()
    assert (commands / "ml.md").read_bytes() == (resources / "commands/ml.md").read_bytes()
    assert unrelated.read_text() == "keep command"
    assert other.read_text() == "keep"


@pytest.mark.parametrize("failed_target", [None, "OpenCode", "codeagent"])
def test_main_installs_both_targets_independently(
    resources, tmp_path, monkeypatch, failed_target,
):
    home = tmp_path / "用户"
    opencode = tmp_path / "custom-opencode"
    cac = home / ".cac"
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(opencode))
    monkeypatch.setattr(Path, "home", lambda: home)

    def install(directory, **kwargs):
        if directory == {"OpenCode": opencode, "codeagent": cac}.get(failed_target):
            raise PermissionError("denied")
        install_resources(directory, resources, **kwargs)

    with patch("wiserec_cli.opencode_install.install_resources", side_effect=install) as mocked, \
            patch("wiserec_cli.opencode_install.msg.detail") as detail:
        assert main() == (1 if failed_target else 0)
    assert mocked.call_count == 2
    for label, directory in (("OpenCode", opencode), ("codeagent", cac)):
        skills_directory = home / ".agents" if label == "OpenCode" else directory
        assert (skills_directory / "skills/wiserec-platform/SKILL.md").exists() == (
            label != failed_target
        )
        assert not (skills_directory / "skills/wiserec-platform-detailed/SKILL.md").exists()
        assert not (directory / "commands/ml-lab.md").exists()
        command = directory / "commands/ml.md"
        assert command.exists() == (label != failed_target)
        if command.exists():
            assert command.read_bytes() == (resources / "commands/ml.md").read_bytes()
    output = "\n".join(call.args[0] for call in detail.call_args_list)
    assert str(home / ".agents/skills/wiserec-platform") in output
    assert not (opencode / "skills").exists()
    assert str(cac / "skills/wiserec-platform") in output
    assert str(opencode / "commands/ml.md") in output
    assert str(cac / "commands/ml.md") in output


def test_upgrade_and_reinstall_lab_preserve_unrelated(resources, tmp_path):
    target = tmp_path / 'config'
    old = target / 'skills/wiserec-platform/SKILL.md'
    old.parent.mkdir(parents=True)
    old.write_text('old installation')
    unrelated = target / 'commands/custom.md'
    unrelated.parent.mkdir()
    unrelated.write_text('keep')
    install_resources(target, resources)
    lab = target / 'skills/wiserec-platform-detailed'
    lab.mkdir(parents=True)
    (lab / 'stale.md').write_text('obsolete')
    (target / 'commands/ml-lab.md').write_text('modified')
    install_resources(target, resources)
    assert not (lab / 'stale.md').exists()
    assert not lab.exists()
    assert not (target / 'commands/ml-lab.md').exists()
    assert unrelated.read_text() == 'keep'


@pytest.mark.parametrize('problem', ['missing', 'corrupt', 'traversal', 'sibling', 'validation'])
def test_invalid_lab_bundle_preserves_both_skills(resources, tmp_path, problem):
    target = tmp_path / 'config'
    install_resources(target, resources)
    before = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()}
    manifest_file = resources / 'manifest.json'
    manifest = json.loads(manifest_file.read_text())
    if problem == 'missing':
        del manifest['commands/ml.md']
    elif problem == 'corrupt':
        (resources / 'commands/ml.md').write_text('corrupt')
    else:
        invalid = {'traversal': 'skills/wiserec-platform-detailed/references/../outside.md',
                   'sibling': 'skills/wiserec-platform-detailed-other/SKILL.md',
                   'validation': 'skills/wiserec-platform-detailed/validation/verify.py'}[problem]
        manifest[invalid] = '0' * 64
    manifest_file.write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        install_resources(target, resources)
    after = {str(p.relative_to(target)): p.read_bytes() for p in target.rglob('*') if p.is_file()}
    assert after == before


@pytest.mark.parametrize("custom_config", [False, True])
def test_shared_install_migrates_old_skills_and_preserves_other_agents(
    resources, tmp_path, monkeypatch, custom_config,
):
    home = tmp_path / "用户"
    monkeypatch.setattr(Path, "home", lambda: home)
    opencode = home / ("custom" if custom_config else ".config/opencode")
    if custom_config:
        monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(opencode))
    else:
        monkeypatch.delenv("OPENCODE_CONFIG_DIR", raising=False)
    install_resources(opencode, resources)
    shared = home / ".agents"
    other = shared / "skills/other/SKILL.md"
    other.parent.mkdir(parents=True)
    other.write_text("personal")
    legacy_other = opencode / "skills/other/SKILL.md"
    legacy_other.parent.mkdir()
    legacy_other.write_text("legacy personal")
    real_install = install_resources
    def install(directory, **kwargs):
        real_install(directory, resources, **kwargs)
    with patch("wiserec_cli.opencode_install.install_resources", side_effect=install):
        assert main() == 0
        stale = shared / "skills/wiserec-platform/stale.md"
        stale.write_text("old")
        assert main() == 0
    assert not stale.exists()
    assert other.read_text() == "personal"
    assert legacy_other.read_text() == "legacy personal"
    for name in ("wiserec-platform", "wiserec-platform-detailed"):
        assert not (opencode / "skills" / name).exists()
        assert (shared / "skills" / name / "SKILL.md").exists() == (name == "wiserec-platform")
        assert (home / ".cac/skills" / name / "SKILL.md").exists() == (name == "wiserec-platform")
    assert not (shared / "commands").exists()
    assert (opencode / "commands/ml.md").exists()


def test_failed_shared_install_keeps_legacy_skills(resources, tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    monkeypatch.delenv("OPENCODE_CONFIG_DIR", raising=False)
    opencode = home / ".config/opencode"
    install_resources(opencode, resources)
    real_install = install_resources
    def install(directory, **kwargs):
        if directory == opencode:
            raise OSError("disk full")
        real_install(directory, resources, **kwargs)
    with patch("wiserec_cli.opencode_install.install_resources", side_effect=install):
        assert main() == 1
    assert (opencode / "skills/wiserec-platform/SKILL.md").exists()
    assert (home / ".cac/skills/wiserec-platform/SKILL.md").exists()


def test_redirected_shared_directory_preserves_old_resources(resources, tmp_path):
    target = tmp_path / "opencode"
    shared = tmp_path / ".agents"
    external = tmp_path / "external"
    external.mkdir()
    shared.symlink_to(external, target_is_directory=True)
    install_resources(target, resources)
    with pytest.raises(ValueError, match="symlink"):
        install_resources(target, resources, skills_target=shared)
    assert (target / "skills/wiserec-platform/SKILL.md").exists()
    assert (target / "commands/ml.md").exists()
    assert list(external.iterdir()) == []


def test_legacy_cleanup_does_not_remove_shared_install(resources, tmp_path):
    target = tmp_path / ".agents"
    install_resources(target, resources)
    remove_legacy_skills(target, target)
    assert (target / "skills/wiserec-platform/SKILL.md").exists()


def test_legacy_cleanup_refuses_redirected_skills(resources, tmp_path):
    target = tmp_path / "opencode"
    shared = tmp_path / ".agents"
    install_resources(shared, resources)
    target.mkdir()
    (target / "skills").symlink_to(shared / "skills", target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        remove_legacy_skills(target, shared)
    assert (shared / "skills/wiserec-platform/SKILL.md").exists()


def test_install_cleans_retired_lab_in_all_managed_locations(resources, tmp_path, monkeypatch):
    home = tmp_path / 'home'
    opencode = tmp_path / 'custom-opencode'
    shared, cac = home / '.agents', home / '.cac'
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setenv('OPENCODE_CONFIG_DIR', str(opencode))
    for root in (shared, opencode, cac):
        lab = root / 'skills/wiserec-platform-detailed'
        lab.mkdir(parents=True)
        (lab / 'SKILL.md').write_text('old')
        commands = root / 'commands'
        commands.mkdir()
        (commands / 'ml-lab.md').write_text('old command')
        (commands / 'personal.md').write_text('keep')
    with patch('wiserec_cli.opencode_install.install_resources',
               side_effect=lambda directory, **kw: install_resources(directory, resources, **kw)):
        assert main() == 0
    for root in (shared, opencode, cac):
        assert not (root / 'skills/wiserec-platform-detailed').exists()
        assert not (root / 'commands/ml-lab.md').exists()
        assert (root / 'commands/personal.md').read_text() == 'keep'


def test_retired_symlink_removes_link_only(resources, tmp_path):
    target = tmp_path / 'config'
    external = tmp_path / 'personal'
    external.mkdir()
    (external / 'SKILL.md').write_text('keep')
    (target / 'skills').mkdir(parents=True)
    (target / 'skills/wiserec-platform-detailed').symlink_to(external, target_is_directory=True)
    install_resources(target, resources)
    assert not (target / 'skills/wiserec-platform-detailed').is_symlink()
    assert (external / 'SKILL.md').read_text() == 'keep'
