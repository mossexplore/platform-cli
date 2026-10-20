import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from wiserec_cli.opencode_install import install_resources, main


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


def test_failure_reports_cli_still_usable(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr("wiserec_cli.opencode_install.detect_permission_format", lambda: "permissions")
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

    def install(directory):
        if directory == {"OpenCode": opencode, "codeagent": cac}.get(failed_target):
            raise PermissionError("denied")
        install_resources(directory, resources)

    with patch("wiserec_cli.opencode_install.install_resources", side_effect=install) as mocked, \
            patch("wiserec_cli.opencode_install.msg.detail") as detail:
        assert main() == (1 if failed_target else 0)
    assert mocked.call_count == 2
    for label, directory in (("OpenCode", opencode), ("codeagent", cac)):
        assert (directory / "skills/wiserec-platform/SKILL.md").exists() == (
            label != failed_target
        )
        command = directory / "commands/ml.md"
        assert command.exists() == (label != failed_target)
        if command.exists():
            assert command.read_bytes() == (resources / "commands/ml.md").read_bytes()
    output = "\n".join(call.args[0] for call in detail.call_args_list)
    assert str(opencode / "skills/wiserec-platform") in output
    assert str(cac / "skills/wiserec-platform") in output
    assert str(opencode / "commands/ml.md") in output
    assert str(cac / "commands/ml.md") in output
