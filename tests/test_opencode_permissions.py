"""OpenCode permission merge, rollback, and the 2026-10-20 bypass regression."""

import hashlib
import json
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

from wiserec_cli import __version__
from wiserec_cli import opencode_permissions as permission_module
from wiserec_cli.opencode_install import main
from wiserec_cli.opencode_managed import manifest_path, public_debug_failure, restrict_backup
from wiserec_cli.opencode_permissions import (
    MARKER,
    MARKER_VALUE,
    SHELL_RULES,
    combined_shell_effect,
    conflicting_allow_rules,
    detect_permission_format,
    fresh_bash_config,
    fresh_opencode_config,
    install_opencode_permissions,
    layered_rules,
    merge_opencode_config,
    permission_effect,
    permission_format_for_version,
    uninstall_opencode_permissions,
    wildcard_match,
    OpenCodeVersionError,
)

_DEBUG_CONFIG = permission_module._opencode_debug_config


@pytest.fixture(autouse=True)
def _accept_opencode_debug_config(monkeypatch, tmp_path):
    monkeypatch.setenv("WISEREC_HOME", str(tmp_path / "wiserec-home"))
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))
    monkeypatch.setattr(
        permission_module,
        "_opencode_debug_config",
        lambda target, expected=None: None,
    )


ROOT = Path(__file__).resolve().parents[1]
SKILL_README = ROOT / "skill" / "wiserec-platform" / "README.md"

# Command segments recorded by the 2026-10-20 report. They come from OpenCode's
# portable scanner at main@d814879; this test re-evaluates those segments with
# the ported wildcard matcher. .NET calls and ${} variables produced no command.
REPORT_CASES = [
    (
        "a exec --help suffix",
        ["ml jupyter exec --cwd x -- sh -c 'echo pwned' --help"],
        "ask",
    ),
    (
        "a2 powershell --help suffix",
        ["ml jupyter exec --cwd x -- powershell -c 'gc c' --help"],
        "ask",
    ),
    ("b tree and echo", ["ml tree", "echo pwned"], "ask"),
    ("c tree then cat credentials", ["ml tree", "cat ~/.x/credentials.json"], "deny"),
    ("d cat credentials", ["cat ./credentials.json"], "deny"),
    ("e show secrets", ["ml login --show-secrets"], "deny"),
    ("type credentials", ["type credentials.json"], "deny"),
    ("Get-Content credentials", ["Get-Content credentials.json"], "deny"),
    ("gc credentials", ["gc credentials.json"], "deny"),
    (
        "tree then Get-Content",
        ["ml tree", r"Get-Content $HOME\.x\credentials.json"],
        "deny",
    ),
    ("tree redirect windows", [r"ml tree > C:\out.txt"], "ask"),
    ("tree redirect bashrc", ["ml tree > ~/.bashrc"], "ask"),
    ("tree append redirect", ["ml tree >> ~/.bashrc"], "ask"),
    ("tree then gc substitution", ["ml tree", "gc credentials.json"], "deny"),
    ("tree then cat substitution", ["ml tree", "cat credentials.json"], "deny"),
    ("Copy-Item credentials", [r"Copy-Item .\credentials.json .\x"], "deny"),
    ("sls credentials", ["sls token credentials.json"], "deny"),
    ("findstr credentials", ["findstr /s secret credentials.json"], "deny"),
    ("GET-CONTENT credentials", ["GET-CONTENT credentials.json"], "deny"),
    ("exact tree", ["ml tree"], "allow"),
    ("exact version", ["ml --version"], "allow"),
    ("exact env list", ["ml env list"], "allow"),
    ("exact jupyter exec help", ["ml jupyter exec --help"], "allow"),
    ("json flag is not exact", ["ml env list -o json"], "ask"),
    ("new command asks", ["ml feature-task list"], "ask"),
    ("product env", ["ml env use product"], "ask"),
    ("deploy dry-run", ["ml model deploy m1 --template t1 --dry-run"], "ask"),
    ("train start", ["ml train start task1"], "ask"),
    ("yes flag", ["ml train list --yes"], "ask"),
    ("parameterized read asks", ["ml model detail model-id"], "ask"),
]

UNCHECKED_CASES = [
    ("dotnet expression only", []),
    ("provider variable only", []),
]


def _rules():
    return fresh_opencode_config()["permissions"]


def test_wildcard_matches_opencode_pattern_language():
    assert wildcard_match("ml tree", "ml tree")
    assert not wildcard_match("ml tree --json", "ml tree")
    assert wildcard_match("ml tree --json", "ml tree*")
    assert wildcard_match("git status", "git status *")
    assert wildcard_match("git status --short", "git status *")
    assert not wildcard_match("git statusx", "git status *")
    assert wildcard_match(r"Get-Content $HOME\.x\credentials.json", "*credentials.json*")
    assert wildcard_match("GET-CONTENT credentials.json", "get-content *credentials*")
    assert not wildcard_match(
        "GET-CONTENT credentials.json", "get-content *credentials*", windows=False
    )
    assert wildcard_match("ml tree > C:/out.txt", "* > *")
    assert not wildcard_match("ml tree >> file", "* > *")
    assert wildcard_match("ml tree >> file", "* >> *")
    assert wildcard_match("ml jupyter exec --help", "ml jupyter exec*")
    assert not wildcard_match(
        "ml jupyter exec --cwd x -- sh -c 'echo pwned' --help", "ml jupyter exec --help"
    )


def test_allow_rules_are_exact_and_drop_trailing_wildcards():
    resources = {resource for resource, _effect in SHELL_RULES}
    assert "ml * --help*" not in resources
    assert "ml tree*" not in resources
    assert "ml --version*" not in resources
    for resource, effect in SHELL_RULES:
        if effect == "allow":
            assert "*" not in resource and "?" not in resource
    assert SHELL_RULES[0] == ("ml *", "ask")
    help_at = resources_index("ml jupyter exec --help")
    exec_at = resources_index("ml jupyter exec*")
    redirect_at = resources_index("* > *")
    assert help_at > exec_at
    assert help_at > redirect_at


def resources_index(resource):
    return [item for item, _effect in SHELL_RULES].index(resource)


@pytest.mark.parametrize("name,segments,expected", REPORT_CASES, ids=[case[0] for case in REPORT_CASES])
def test_report_cases_match_expected_effect(name, segments, expected):
    assert expected in {"ask", "deny", "allow"}
    assert combined_shell_effect(segments, _rules()) == expected


@pytest.mark.parametrize("name,segments", UNCHECKED_CASES, ids=[case[0] for case in UNCHECKED_CASES])
def test_unscanned_powershell_expressions_are_not_permission_checks(name, segments):
    assert combined_shell_effect(segments, _rules()) == "unchecked"


def test_compound_dotnet_read_is_only_the_parsed_tree_command():
    # The report's scanner kept only ``ml tree`` for this statement, so the
    # ReadAllText call never becomes a resource. Rules cannot deny it.
    assert combined_shell_effect(["ml tree"], _rules()) == "allow"


def test_fresh_install_writes_fallback_and_managed_rules(tmp_path):
    install_opencode_permissions(tmp_path)
    document = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert document == fresh_opencode_config()
    assert document["permissions"][0] == {"action": "shell", "resource": "*", "effect": "ask"}
    assert MARKER not in document
    assert all(MARKER not in rule for rule in document["permissions"] if isinstance(rule, dict))
    assert not (tmp_path / "opencode.json.bak").exists()
    sidecar = manifest_path(tmp_path / "opencode.json")
    record = json.loads(sidecar.read_text(encoding="utf-8"))
    rendered = (tmp_path / "opencode.json").read_text(encoding="utf-8")
    assert record["installer_version"] == __version__
    assert record["format"] == "permissions"
    assert record["config_sha256"] == hashlib.sha256(rendered.encode("utf-8")).hexdigest()
    assert record["permissions"][0]["original"] is None
    assert "targets" not in record
    assert stat.S_IMODE(sidecar.stat().st_mode) == 0o600


def test_merge_preserves_user_fields_and_rules(tmp_path):
    original = {
        "$schema": "https://opencode.ai/config.json",
        "model": "anthropic/claude",
        "mcp": {"servers": {"demo": {"type": "local", "command": ["demo"]}}},
        "permission": {
            "edit": "ask",
            "bash": {
                "*": "allow",
                "git status *": "allow",
                "rm *": "deny",
                "ml tree*": "allow",
                "ml * --help*": "allow",
            },
        },
        "permissions": [
            {"action": "read", "resource": "*.md", "effect": "allow"},
            {"action": "shell", "resource": "npm test *", "effect": "allow", "note": "keep"},
            "opaque-entry",
        ],
    }
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps(original, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    install_opencode_permissions(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["model"] == "anthropic/claude"
    assert document["mcp"] == original["mcp"]
    assert document["permission"]["edit"] == "ask"
    assert document["permission"]["bash"] == original["permission"]["bash"]
    assert "shell" not in document["permission"]
    rules = document["permissions"]
    assert rules[0] == "opaque-entry"
    assert rules[1]["resource"] == "*.md" and MARKER not in rules[1]
    assert rules[2] == {"action": "shell", "resource": "*", "effect": "ask"}
    assert rules[3]["resource"] == "npm test *" and MARKER not in rules[3]
    assert MARKER not in document
    resources = [rule["resource"] for rule in rules if isinstance(rule, dict)]
    assert "ml tree*" not in resources
    assert resources.count("ml env list") == 1
    assert "opaque-entry" in rules
    assert permission_effect("shell", "npm test --watch", rules) == "allow"
    assert permission_effect("shell", "echo hello", rules) == "ask"
    assert permission_effect("read", "docs/guide.md", rules) == "allow"
    assert permission_effect("read", r"C:\Users\me\.wiserec\credentials.json", rules) == "deny"
    assert combined_shell_effect(["ml tree"], rules) == "allow"
    assert combined_shell_effect([r"ml tree > C:\out.txt"], rules) == "ask"
    assert combined_shell_effect(
        ["ml jupyter exec --cwd x -- sh -c 'echo pwned' --help"], rules
    ) == "ask"
    kept = next(rule for rule in rules if isinstance(rule, dict) and rule["resource"] == "npm test *")
    assert kept["note"] == "keep"
    bash_rules = [
        {"action": "shell", "resource": resource, "effect": effect}
        for resource, effect in document["permission"]["bash"].items()
    ]
    effective = layered_rules(bash_rules, rules)
    assert combined_shell_effect(["echo hello"], effective) == "ask"
    assert combined_shell_effect(["ml login --show-secrets"], effective) == "deny"
    assert combined_shell_effect(
        ["ml jupyter exec --cwd x -- sh -c 'echo pwned' --help"], effective
    ) == "ask"


def test_reinstall_is_idempotent_and_does_not_refresh_backup(tmp_path):
    original = {"model": "kept", "permissions": [{"action": "shell", "resource": "git diff *", "effect": "allow"}]}
    path = tmp_path / "opencode.json"
    raw = json.dumps(original, indent=2) + "\n"
    path.write_text(raw, encoding="utf-8")
    install_opencode_permissions(tmp_path)
    backup = (tmp_path / "opencode.json.bak").read_bytes()
    assert backup.decode("utf-8") == raw
    merged = path.read_bytes()
    install_opencode_permissions(tmp_path)
    assert path.read_bytes() == merged
    assert (tmp_path / "opencode.json.bak").read_bytes() == backup
    resources = [rule["resource"] for rule in json.loads(merged)["permissions"] if isinstance(rule, dict)]
    assert resources.count("ml *") == 1
    assert resources.count("*") == 1


def test_invalid_json_is_not_replaced(tmp_path):
    path = tmp_path / "opencode.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        install_opencode_permissions(tmp_path)
    assert path.read_text(encoding="utf-8") == "{"
    assert not (tmp_path / "opencode.json.bak").exists()


def test_replace_failure_restores_original_and_removes_temp(tmp_path):
    path = tmp_path / "opencode.json"
    original = '{"model": "keep"}\n'
    path.write_text(original, encoding="utf-8")
    with patch("wiserec_cli.opencode_permissions.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            install_opencode_permissions(tmp_path)
    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "opencode.json.wiserec-tmp").exists()
    assert (tmp_path / "opencode.json.bak").read_text(encoding="utf-8") == original


def test_failed_create_does_not_leave_a_config(tmp_path):
    with patch("wiserec_cli.opencode_permissions.os.replace", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            install_opencode_permissions(tmp_path)
    assert not (tmp_path / "opencode.json").exists()
    assert not (tmp_path / "opencode.json.wiserec-tmp").exists()


def test_jsonc_only_receives_the_merge(tmp_path):
    path = tmp_path / "opencode.jsonc"
    path.write_text('{"model": "keep"}\n', encoding="utf-8")
    install_opencode_permissions(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["model"] == "keep"
    assert document["permissions"][0]["resource"] == "*"
    assert (tmp_path / "opencode.jsonc.bak").read_text(encoding="utf-8") == '{"model": "keep"}\n'
    assert not (tmp_path / "opencode.json").exists()


def test_commented_jsonc_is_left_unchanged(tmp_path):
    path = tmp_path / "opencode.jsonc"
    original = '{\n  // keep\n  "model": "keep"\n}\n'
    path.write_text(original, encoding="utf-8")
    with pytest.raises(ValueError, match="comments"):
        install_opencode_permissions(tmp_path)
    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "opencode.jsonc.bak").exists()


def test_both_config_files_stop_before_any_write(tmp_path):
    json_path = tmp_path / "opencode.json"
    jsonc_path = tmp_path / "opencode.jsonc"
    json_path.write_text('{"model": "json"}\n', encoding="utf-8")
    jsonc_path.write_text('{"model": "jsonc"}\n', encoding="utf-8")
    with pytest.raises(ValueError, match="opencode.jsonc"):
        install_opencode_permissions(tmp_path)
    assert json.loads(json_path.read_text(encoding="utf-8")) == {"model": "json"}
    assert json.loads(jsonc_path.read_text(encoding="utf-8")) == {"model": "jsonc"}


def test_crlf_file_with_the_same_rules_is_not_rewritten(tmp_path):
    install_opencode_permissions(tmp_path)
    path = tmp_path / "opencode.json"
    crlf = path.read_text(encoding="utf-8").replace("\n", "\r\n").encode("utf-8")
    path.write_bytes(crlf)
    install_opencode_permissions(tmp_path)
    assert path.read_bytes() == crlf


def test_symlink_config_and_directory_are_not_followed(tmp_path):
    external = tmp_path / "external.json"
    external.write_text('{"model": "secret"}', encoding="utf-8")
    target = tmp_path / "config"
    target.mkdir()
    (target / "opencode.json").symlink_to(external)
    with pytest.raises(ValueError, match="symlink"):
        install_opencode_permissions(target)
    assert external.read_text(encoding="utf-8") == '{"model": "secret"}'

    linked = tmp_path / "linked"
    real = tmp_path / "real"
    real.mkdir()
    linked.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        install_opencode_permissions(linked)
    assert list(real.iterdir()) == []


def test_merge_does_not_mutate_input():
    config = {"permission": {"bash": {"git status *": "allow"}}}
    merged = merge_opencode_config(config)
    assert config == {"permission": {"bash": {"git status *": "allow"}}}
    assert merged["permissions"]
    assert merged["permission"]["bash"] == {"git status *": "allow"}


def test_readme_minimum_matches_the_version_check():
    from wiserec_cli.opencode_version import MINIMUM_BASH

    assert MINIMUM_BASH == (1, 1, 1)
    for relative in ("README.md", "scripts/windows/INSTALL.md", "skill/wiserec-platform/README.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "1.1.1" in text
        assert "packages/opencode/src/config/config.ts" in text
        assert "388" in text and "405" in text and "947" in text


def test_docs_say_a_tab_skips_the_whole_command():
    for relative in (
        "README.md",
        "scripts/windows/INSTALL.md",
        "skill/wiserec-platform/README.md",
        "skill/wiserec-platform/SKILL.md",
        "docs/WiseRec CLI 使用手册.md",
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "TAB" in text
        assert "整条命令" in text
        assert "只有一条命令" in text


def test_skill_readme_example_matches_installer():
    text = SKILL_README.read_text(encoding="utf-8")
    fenced = text.split("```json\n", 1)[1].split("\n```", 1)[0]
    assert json.loads(fenced) == fresh_opencode_config()
    assert "ml * --help*" not in text.split("```json", 1)[1]
    assert "ReadAllText" in text
    assert "DPAPI" in text


def test_user_ml_star_allow_cannot_override_ask_or_deny(tmp_path, capsys):
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({
        "model": "keep",
        "permissions": [
            {"action": "shell", "resource": "ml*", "effect": "allow"},
            {"action": "shell", "resource": "ml tree*", "effect": "allow"},
            {"action": "shell", "resource": "git status *", "effect": "allow"},
        ],
    }), encoding="utf-8")
    install_opencode_permissions(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    rules = document["permissions"]
    assert document["model"] == "keep"
    assert [rule["resource"] for rule in rules[:4]] == ["*", "ml*", "ml tree*", "git status *"]
    assert rules[0]["effect"] == "ask" and MARKER not in rules[0]
    assert all(MARKER not in rule for rule in rules if isinstance(rule, dict))
    assert rules[-1]["effect"] == "deny" or rules[-1]["action"] == "read"
    user_index = 1
    ask_index = next(i for i, rule in enumerate(rules) if rule["resource"] == "ml jupyter exec*")
    secret_index = next(i for i, rule in enumerate(rules) if rule["resource"] == "ml login --show-secrets*")
    credential_index = next(
        i for i, rule in enumerate(rules)
        if rule["action"] == "shell" and rule["resource"] == "*credentials.json*"
    )
    assert user_index < ask_index < secret_index
    assert user_index < credential_index
    assert combined_shell_effect(
        ["ml jupyter exec --cwd x -- sh -c 'echo pwned' --help"], rules
    ) == "ask"
    assert combined_shell_effect(["ml login --show-secrets"], rules) == "deny"
    assert combined_shell_effect(["cat ./credentials.json"], rules) == "deny"
    assert combined_shell_effect(["Get-Content credentials.json"], rules) == "deny"
    assert combined_shell_effect(["git status"], rules) == "allow"
    assert combined_shell_effect(["ml tree"], rules) == "allow"
    assert combined_shell_effect(["ml jupyter exec --help"], rules) == "allow"
    warning = capsys.readouterr().err
    assert "ml*" in warning
    assert "ml tree*" in warning
    assert "git status *" not in warning
    assert conflicting_allow_rules(rules)[0]["resource"] == "ml*"


def test_marked_rules_reinstall_once_and_uninstall_removes_only_them(tmp_path):
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({
        "model": "keep",
        "permissions": [{"action": "shell", "resource": "ml*", "effect": "allow", "note": "user"}],
    }), encoding="utf-8")
    install_opencode_permissions(tmp_path)
    installed = json.loads(path.read_text(encoding="utf-8"))
    assert MARKER not in installed
    assert all(MARKER not in rule for rule in installed["permissions"] if isinstance(rule, dict))
    managed = [
        rule for rule in installed["permissions"]
        if isinstance(rule, dict) and rule["resource"] in {resource for resource, _effect in SHELL_RULES} | {"*"}
    ]
    assert managed
    assert len(managed) == len({(rule["action"], rule["resource"]) for rule in managed})
    install_opencode_permissions(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["permissions"] == installed["permissions"]
    uninstall_opencode_permissions(tmp_path)
    removed = json.loads(path.read_text(encoding="utf-8"))
    assert removed["model"] == "keep"
    assert removed["permissions"] == [
        {"action": "shell", "resource": "ml*", "effect": "allow", "note": "user"},
    ]
    assert (tmp_path / "opencode.json.bak").read_text(encoding="utf-8")
    uninstall_opencode_permissions(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8")) == removed


def test_uninstall_invalid_json_leaves_the_file(tmp_path):
    path = tmp_path / "opencode.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON"):
        uninstall_opencode_permissions(tmp_path)
    assert path.read_text(encoding="utf-8") == "{"
    assert not (tmp_path / "opencode.json.bak").exists()


def _v2(monkeypatch, kind="permissions"):
    monkeypatch.setattr("wiserec_cli.opencode_install.detect_permission_format", lambda: kind)


def _plant_skill(directory: Path) -> None:
    skill = directory / "skills" / "wiserec-platform"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("old", encoding="utf-8")
    commands = directory / "commands"
    commands.mkdir()
    (commands / "ml.md").write_text("old", encoding="utf-8")
    (commands / "custom.md").write_text("keep", encoding="utf-8")


def _assert_prior_skill(directory: Path) -> None:
    assert (directory / "skills" / "wiserec-platform" / "SKILL.md").read_text(encoding="utf-8") == "old"
    assert (directory / "commands" / "ml.md").read_text(encoding="utf-8") == "old"
    assert (directory / "commands" / "custom.md").read_text(encoding="utf-8") == "keep"


def test_invalid_json_aborts_the_install_step(tmp_path, monkeypatch, capsys):
    path = tmp_path / "opencode.json"
    path.write_text("{", encoding="utf-8")
    _plant_skill(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    _v2(monkeypatch)
    with patch("wiserec_cli.opencode_install.install_resources") as install_resources:
        assert main() == 1
    install_resources.assert_not_called()
    assert path.read_text(encoding="utf-8") == "{"
    assert not (tmp_path / "opencode.json.bak").exists()
    _assert_prior_skill(tmp_path)
    error = capsys.readouterr().err
    assert "left unchanged" in error
    assert "were left unchanged" in error


def test_uninstall_flag_removes_marked_rules(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    _v2(monkeypatch)
    with patch("wiserec_cli.opencode_install.install_resources"):
        assert main([]) == 0
    assert main(["--uninstall"]) == 0
    document = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert "permissions" not in document
    assert "removed" in capsys.readouterr().err


def test_main_writes_permissions_before_the_skill(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    _v2(monkeypatch)
    seen = {}

    def resources(target):
        seen["ready"] = json.loads((target / "opencode.json").read_text(encoding="utf-8"))
        seen["manifest"] = (target / "wiserec-managed.json").is_file()

    with patch("wiserec_cli.opencode_install.install_resources", side_effect=resources):
        assert main() == 0
    assert seen["ready"]["permissions"][0]["resource"] == "*"
    assert seen["manifest"] is True
    output = capsys.readouterr().err
    assert "permission rules installed" in output
    assert "every shell command, not only ml" in output


def test_main_reports_permission_failure_without_claiming_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    _plant_skill(tmp_path)
    _v2(monkeypatch)
    with patch("wiserec_cli.opencode_install.install_resources") as install_resources, patch(
        "wiserec_cli.opencode_install.install_opencode_permissions",
        side_effect=OSError("disk full"),
    ):
        assert main() == 1
    install_resources.assert_not_called()
    _assert_prior_skill(tmp_path)
    error = capsys.readouterr().err
    assert "CLI remains usable" in error
    assert "were left unchanged" in error
    assert "permission rules installed" not in error


def test_version_selects_bash_or_permissions_and_aborts_when_unknown():
    assert permission_format_for_version("1.19.3") == "bash"
    assert permission_format_for_version("opencode 1.1.1") == "bash"
    assert permission_format_for_version("2.0.0") == "permissions"
    assert permission_format_for_version("2.1.0") == "permissions"
    assert permission_format_for_version("2.0.32\n") == "permissions"
    with pytest.raises(OpenCodeVersionError):
        permission_format_for_version("1.1.0")
    with pytest.raises(OpenCodeVersionError):
        permission_format_for_version("not a version")
    with pytest.raises(OpenCodeVersionError):
        detect_permission_format(lambda name: None)
    assert detect_permission_format(lambda name: "1.19.3" if name == "opencode" else None) == "bash"
    with pytest.raises(OpenCodeVersionError):
        detect_permission_format(lambda name: None if name == "opencode" else "2.1.0")


def test_undetectable_version_aborts_before_any_config_write(tmp_path, monkeypatch, capsys):
    path = tmp_path / "opencode.json"
    path.write_text('{"model": "keep"}\n', encoding="utf-8")
    _plant_skill(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    monkeypatch.setattr(
        "wiserec_cli.opencode_install.detect_permission_format",
        lambda: (_ for _ in ()).throw(OpenCodeVersionError("undetectable")),
    )
    with patch("wiserec_cli.opencode_install.install_resources") as install_resources:
        assert main() == 1
    install_resources.assert_not_called()
    assert path.read_text(encoding="utf-8") == '{"model": "keep"}\n'
    assert not (tmp_path / "opencode.json.bak").exists()
    _assert_prior_skill(tmp_path)
    error = capsys.readouterr().err
    assert "[错误]" in error
    assert "were left unchanged" in error


def test_commented_jsonc_fails_the_install_step(tmp_path, monkeypatch, capsys):
    path = tmp_path / "opencode.jsonc"
    path.write_text('{\n  // keep\n  "model": "keep"\n}\n', encoding="utf-8")
    _plant_skill(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    _v2(monkeypatch)
    with patch("wiserec_cli.opencode_install.install_resources") as install_resources:
        assert main() == 1
    install_resources.assert_not_called()
    assert "// keep" in path.read_text(encoding="utf-8")
    assert not (tmp_path / "opencode.jsonc.bak").exists()
    _assert_prior_skill(tmp_path)
    error = capsys.readouterr().err
    assert "[错误]" in error
    assert "were left unchanged" in error


def test_bash_release_appends_without_moving_user_rules(tmp_path, capsys):
    path = tmp_path / "opencode.json"
    original = {
        "model": "keep",
        "permission": {
            "edit": "ask",
            "shell": {"npm test *": "allow"},
            "bash": {"ml*": "allow", "git status *": "allow"},
        },
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    install_opencode_permissions(tmp_path, rule_format="bash")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["model"] == "keep"
    assert document["permission"]["edit"] == "ask"
    assert document["permission"]["shell"] == {"npm test *": "allow"}
    bash = document["permission"]["bash"]
    assert list(bash)[:3] == ["*", "ml*", "git status *"]
    assert bash["*"] == "ask"
    assert bash["ml*"] == "allow"
    assert bash["ml login --show-secrets*"] == "deny"
    assert list(bash).index("ml login --show-secrets*") > list(bash).index("ml*")
    assert list(bash).index("ml jupyter exec*") > list(bash).index("ml*")
    assert list(bash).index("ml jupyter exec --help") > list(bash).index("ml jupyter exec*")
    assert "permissions" not in document
    rules = [{"action": "shell", "resource": resource, "effect": effect} for resource, effect in bash.items()]
    assert combined_shell_effect(["echo hello"], rules) == "ask"
    assert combined_shell_effect(["git status"], rules) == "allow"
    assert combined_shell_effect(["ml tree"], rules) == "allow"
    assert combined_shell_effect(["ml login --show-secrets"], rules) == "deny"
    assert combined_shell_effect(
        ["ml jupyter exec --cwd x -- sh -c 'echo pwned' --help"], rules
    ) == "ask"
    warning = capsys.readouterr().err
    assert "ml*" in warning
    assert "later managed ask or deny" in warning
    assert "Added OpenCode rules" in warning
    install_opencode_permissions(tmp_path, rule_format="bash")
    assert json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"] == bash
    uninstall_opencode_permissions(tmp_path)
    removed = json.loads(path.read_text(encoding="utf-8"))
    assert removed["permission"]["bash"] == {"ml*": "allow", "git status *": "allow"}
    assert removed["permission"]["shell"] == {"npm test *": "allow"}
    assert MARKER not in removed


def test_existing_backup_is_not_overwritten(tmp_path):
    path = tmp_path / "opencode.json"
    path.write_text('{"model": "first"}\n', encoding="utf-8")
    install_opencode_permissions(tmp_path)
    original_backup = (tmp_path / "opencode.json.bak").read_bytes()
    assert stat.S_IMODE((tmp_path / "opencode.json.bak").stat().st_mode) == 0o600
    path.write_text('{"model": "second"}\n', encoding="utf-8")
    install_opencode_permissions(tmp_path)
    assert (tmp_path / "opencode.json.bak").read_bytes() == original_backup
    stamped = list(tmp_path.glob("opencode.json.bak.*"))
    assert len(stamped) == 1
    assert stamped[0].read_text(encoding="utf-8") == '{"model": "second"}\n'


def test_project_and_agent_rules_override_global():
    # OpenCode 2 loads global rules, then project rules, then appends agent rules.
    # The same file still evaluates permission.bash before the permissions array.
    global_rules = fresh_opencode_config()["permissions"]
    project = [{"action": "shell", "resource": "*", "effect": "allow"}]
    agent = [{"action": "shell", "resource": "ml login --show-secrets*", "effect": "deny"}]
    assert combined_shell_effect(["ml login --show-secrets"], global_rules) == "deny"
    assert combined_shell_effect(["echo hello"], global_rules) == "ask"
    assert combined_shell_effect(
        ["ml login --show-secrets"], layered_rules(global_rules, project)
    ) == "allow"
    assert combined_shell_effect(
        ["echo hello"], layered_rules(global_rules, project)
    ) == "allow"
    assert combined_shell_effect(
        ["ml login --show-secrets"], layered_rules(global_rules, project, agent)
    ) == "deny"
    bash = [
        {"action": "shell", "resource": "*", "effect": "allow"},
        {"action": "shell", "resource": "rm *", "effect": "deny"},
    ]
    layered = layered_rules(bash, global_rules)
    assert combined_shell_effect(["echo hello"], layered) == "ask"
    assert combined_shell_effect(["rm -rf /tmp/demo"], layered) == "ask"


def _bash_rules(bash: dict) -> list:
    return [{"action": "shell", "resource": resource, "effect": effect} for resource, effect in bash.items()]


def test_fresh_bash_puts_star_ask_first_and_ask_deny_last():
    document = fresh_bash_config()
    bash = document["permission"]["bash"]
    keys = list(bash)
    assert keys[0] == "*"
    assert bash["*"] == "ask"
    assert keys[1] == "ml *"
    assert keys.index("ml tree") < keys.index("ml jupyter exec*")
    assert keys.index("ml jupyter exec*") < keys.index("ml jupyter exec --help")
    assert keys.index("ml jupyter exec --help") < keys.index("ml login --show-secrets*")
    assert keys[-1] == "*credentials.json*"
    assert "permissions" not in document
    rules = _bash_rules(bash)
    assert combined_shell_effect(["echo hello"], rules) == "ask"
    assert combined_shell_effect(["ml tree"], rules) == "allow"
    assert combined_shell_effect(["ml jupyter exec --help"], rules) == "allow"
    assert combined_shell_effect(
        ["ml jupyter exec --cwd x -- sh -c 'echo pwned' --help"], rules
    ) == "ask"
    assert combined_shell_effect(["ml login --show-secrets"], rules) == "deny"
    assert permission_effect("read", "credentials.json", [
        {"action": "read", "resource": resource, "effect": effect}
        for resource, effect in document["permission"]["read"].items()
    ]) == "deny"
    assert document["permission"]["skill"]["wiserec-platform"] == "allow"


def test_bash_inserts_star_ask_first_without_moving_user_keys(tmp_path):
    path = tmp_path / "opencode.json"
    original = {"permission": {"bash": {"git status *": "allow", "npm test *": "ask"}}}
    path.write_text(json.dumps(original), encoding="utf-8")
    install_opencode_permissions(tmp_path, rule_format="bash")
    bash = json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"]
    assert list(bash)[:3] == ["*", "git status *", "npm test *"]
    assert bash["*"] == "ask"
    assert list(bash)[3] == "ml *"
    assert list(bash)[-1] == "*credentials.json*"
    rules = _bash_rules(bash)
    assert combined_shell_effect(["echo hello"], rules) == "ask"
    assert combined_shell_effect(["git status"], rules) == "allow"
    assert combined_shell_effect(["npm test"], rules) == "ask"
    assert combined_shell_effect(["ml tree"], rules) == "allow"
    install_opencode_permissions(tmp_path, rule_format="bash")
    again = json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"]
    assert list(again) == list(bash)


def test_existing_star_key_is_overwritten_and_moved_first():
    merged = merge_opencode_config(
        {"permission": {"bash": {"git status *": "allow", "*": "deny", "npm test *": "ask"}}},
        rule_format="bash",
    )
    bash = merged["permission"]["bash"]
    assert list(bash)[:3] == ["*", "git status *", "npm test *"]
    assert bash["*"] == "ask"
    assert list(bash)[3] == "ml *"
    assert combined_shell_effect(["echo hello"], _bash_rules(bash)) == "ask"


def test_bash_string_shorthand_overwrites_star_and_keeps_other_read_keys():
    original = {"permission": {"bash": "allow", "read": {"*.md": "allow", "*credentials.json*": "allow"}}}
    merged = merge_opencode_config(original, rule_format="bash")
    assert original["permission"]["bash"] == "allow"
    bash = merged["permission"]["bash"]
    assert list(bash)[0] == "*" and bash["*"] == "ask"
    read = merged["permission"]["read"]
    assert list(read) == ["*.md", "*credentials.json*"]
    assert read["*.md"] == "allow"
    assert read["*credentials.json*"] == "deny"


def test_permissions_mode_does_not_change_permission_bash():
    original = {
        "permission": {
            "edit": "ask",
            "bash": {"*": "allow", "ml*": "allow", "git status *": "allow"},
            "shell": {"npm test *": "allow"},
        },
        MARKER: {"format": "bash", "bash": ["ml*"], "read": [], "skill": []},
    }
    merged = merge_opencode_config(original, rule_format="permissions")
    assert merged["permission"] == original["permission"]
    assert list(merged["permission"]["bash"]) == ["*", "ml*", "git status *"]
    assert MARKER not in merged


def test_bash_mode_drops_marked_array_rules_and_keeps_user_array_rules():
    merged = merge_opencode_config(
        {
            "permissions": [
                {"action": "read", "resource": "*.md", "effect": "allow"},
                {"action": "shell", "resource": "ml *", "effect": "ask", MARKER: MARKER_VALUE},
            ]
        },
        rule_format="bash",
    )
    assert merged["permissions"] == [{"action": "read", "resource": "*.md", "effect": "allow"}]
    assert list(merged["permission"]["bash"])[0] == "*"


def test_debug_config_rejection_restores_the_original(tmp_path, monkeypatch):
    path = tmp_path / "opencode.json"
    original = '{"model": "keep"}\n'
    path.write_text(original, encoding="utf-8")

    def reject(target, expected=None):
        raise ValueError("V2 permissions are not supported by OpenCode V1")

    monkeypatch.setattr(permission_module, "_opencode_debug_config", reject)
    with pytest.raises(ValueError, match="not supported"):
        install_opencode_permissions(tmp_path)
    assert path.read_text(encoding="utf-8") == original
    assert (tmp_path / "opencode.json.bak").read_text(encoding="utf-8") == original
    assert not (tmp_path / "opencode.json.wiserec-tmp").exists()


def test_prior_skill_stays_when_permission_validation_fails(tmp_path, monkeypatch, capsys):
    path = tmp_path / "opencode.json"
    original = '{"model": "keep"}\n'
    path.write_text(original, encoding="utf-8")
    _plant_skill(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    _v2(monkeypatch)

    def reject(target, expected=None):
        raise ValueError("opencode debug config failed (exit 1): missing managed bash rule")

    monkeypatch.setattr(permission_module, "_opencode_debug_config", reject)
    with patch("wiserec_cli.opencode_install.install_resources") as install_resources:
        assert main() == 1
    install_resources.assert_not_called()
    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "wiserec-managed.json").exists()
    _assert_prior_skill(tmp_path)
    error = capsys.readouterr().err
    assert "missing managed bash rule" in error
    assert "super-secret" not in error
    assert "were left unchanged" in error


def test_skill_install_failure_restores_permissions_and_removes_manifest(tmp_path, monkeypatch, capsys):
    path = tmp_path / "opencode.json"
    original = '{"model": "keep"}\n'
    path.write_text(original, encoding="utf-8")
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    _v2(monkeypatch)
    with patch("wiserec_cli.opencode_install.install_resources", side_effect=OSError("disk full")):
        assert main() == 1
    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "wiserec-managed.json").exists()
    error = capsys.readouterr().err
    assert "disk full" in error
    assert "wiserec-managed.json was removed" in error
    assert "restored from the backup" in error
    assert "permission rules installed" not in error


def test_debug_config_rejection_removes_a_new_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        permission_module,
        "_opencode_debug_config",
        lambda target, expected=None: (_ for _ in ()).throw(ValueError("Unrecognized key")),
    )
    with pytest.raises(ValueError, match="Unrecognized key"):
        install_opencode_permissions(tmp_path, rule_format="bash")
    assert not (tmp_path / "opencode.json").exists()
    assert list(tmp_path.glob("opencode.json*")) == []


def test_debug_config_asks_opencode_to_load_the_directory(tmp_path, monkeypatch):
    seen = {}

    class Completed:
        def __init__(self, code, stdout, stderr):
            self.returncode = code
            self.stdout = stdout
            self.stderr = stderr

    def fake_run(argv, **kwargs):
        seen["argv"] = argv
        seen["cwd"] = kwargs["cwd"]
        seen["env"] = kwargs["env"]
        return Completed(0, "{}", "")

    monkeypatch.setattr(permission_module.shutil, "which", lambda name: "/usr/bin/opencode" if name == "opencode" else None)
    monkeypatch.setattr(permission_module.subprocess, "run", fake_run)
    _DEBUG_CONFIG(tmp_path)
    assert seen["argv"] == ["/usr/bin/opencode", "debug", "config"]
    assert seen["cwd"] == str(tmp_path)
    assert seen["env"]["OPENCODE_CONFIG_DIR"] == str(tmp_path)
    assert seen["env"]["OPENCODE_DISABLE_PROJECT_CONFIG"] == "1"

    def reject(argv, **kwargs):
        return Completed(1, "", "V2 permissions are not supported by OpenCode V1")

    monkeypatch.setattr(permission_module.subprocess, "run", reject)
    with pytest.raises(ValueError, match="not supported"):
        _DEBUG_CONFIG(tmp_path)
    monkeypatch.setattr(permission_module.shutil, "which", lambda name: None)
    with pytest.raises(ValueError, match="not found"):
        _DEBUG_CONFIG(tmp_path)

    def empty(argv, **kwargs):
        return Completed(0, "", "")

    monkeypatch.setattr(permission_module.shutil, "which", lambda name: "/usr/bin/opencode")
    monkeypatch.setattr(permission_module.subprocess, "run", empty)
    with pytest.raises(ValueError, match="JSON config object"):
        _DEBUG_CONFIG(tmp_path)

    def usage(argv, **kwargs):
        return Completed(0, "unknown command: debug\n", "")

    monkeypatch.setattr(permission_module.subprocess, "run", usage)
    with pytest.raises(ValueError, match="JSON config object"):
        _DEBUG_CONFIG(tmp_path)


def test_unclear_debug_config_rolls_back_and_reports(tmp_path, monkeypatch):
    path = tmp_path / "opencode.json"
    original = '{"model": "keep"}\n'
    path.write_text(original, encoding="utf-8")

    class Completed:
        def __init__(self, code, stdout, stderr):
            self.returncode = code
            self.stdout = stdout
            self.stderr = stderr

    monkeypatch.setattr(permission_module.shutil, "which", lambda name: "/usr/bin/opencode")
    monkeypatch.setattr(
        permission_module.subprocess,
        "run",
        lambda argv, **kwargs: Completed(0, "", ""),
    )
    monkeypatch.setattr(permission_module, "_opencode_debug_config", _DEBUG_CONFIG)
    with pytest.raises(ValueError, match="JSON config object"):
        install_opencode_permissions(tmp_path, rule_format="bash")
    assert path.read_text(encoding="utf-8") == original
    assert (tmp_path / "opencode.json.bak").read_text(encoding="utf-8") == original
    assert not (tmp_path / "opencode.json.wiserec-tmp").exists()


def test_v1_bash_scenarios_none_ml_star_and_star_allow(tmp_path, capsys):
    # No user rules: built-in "*": allow is replaced by our "*": ask first.
    none_dir = tmp_path / "none"
    install_opencode_permissions(none_dir, rule_format="bash")
    none = json.loads((none_dir / "opencode.json").read_text(encoding="utf-8"))["permission"]["bash"]
    assert list(none)[0] == "*" and none["*"] == "ask"
    none_rules = _bash_rules(none)
    assert combined_shell_effect(["echo x"], none_rules) == "ask"
    assert combined_shell_effect(["ml tree"], none_rules) == "allow"
    assert combined_shell_effect(["ml tree", "echo x"], none_rules) == "ask"
    assert combined_shell_effect(["ml tree", "ml login --show-secrets"], none_rules) == "deny"
    assert combined_shell_effect(["ml tree", "cat ./credentials.json"], none_rules) == "deny"
    none_err = capsys.readouterr().err
    assert "Added OpenCode rules" in none_err
    assert "Project or agent config" not in none_err
    assert "already has" not in none_err

    # User ml* allow stays, and later ask/deny still govern the chain.
    ml_dir = tmp_path / "ml"
    ml_dir.mkdir()
    (ml_dir / "opencode.json").write_text(
        json.dumps({"permission": {"bash": {"ml*": "allow"}}}),
        encoding="utf-8",
    )
    install_opencode_permissions(ml_dir, rule_format="bash")
    ml_bash = json.loads((ml_dir / "opencode.json").read_text(encoding="utf-8"))["permission"]["bash"]
    assert list(ml_bash)[:2] == ["*", "ml*"]
    assert ml_bash["*"] == "ask" and ml_bash["ml*"] == "allow"
    assert list(ml_bash).index("ml login --show-secrets*") > list(ml_bash).index("ml*")
    ml_rules = _bash_rules(ml_bash)
    assert combined_shell_effect(["ml tree"], ml_rules) == "allow"
    assert combined_shell_effect(["ml tree", "echo x"], ml_rules) == "ask"
    assert combined_shell_effect(["ml login --show-secrets"], ml_rules) == "deny"
    assert combined_shell_effect(["ml tree", "cat ./credentials.json"], ml_rules) == "deny"
    ml_err = capsys.readouterr().err
    assert "ml*" in ml_err
    assert "will run" not in ml_err

    # User "*" allow is an exact key we manage. Our ask wins and stays first.
    star_dir = tmp_path / "star"
    star_dir.mkdir()
    (star_dir / "opencode.json").write_text(
        json.dumps({"permission": {"bash": {"git status *": "allow", "*": "allow", "ml*": "allow"}}}),
        encoding="utf-8",
    )
    install_opencode_permissions(star_dir, rule_format="bash")
    star = json.loads((star_dir / "opencode.json").read_text(encoding="utf-8"))["permission"]["bash"]
    assert list(star)[:3] == ["*", "git status *", "ml*"]
    assert star["*"] == "ask" and star["ml*"] == "allow"
    star_rules = _bash_rules(star)
    assert combined_shell_effect(["echo x"], star_rules) == "ask"
    assert combined_shell_effect(["ml tree", "echo x"], star_rules) == "ask"
    assert combined_shell_effect(["git status"], star_rules) == "allow"
    star_err = capsys.readouterr().err
    assert 'permission.bash "*": allow -> ask' in star_err
    assert "will run" not in star_err
    record = json.loads(manifest_path(star_dir / "opencode.json").read_text(encoding="utf-8"))
    assert record["bash"]["bash"]["*"]["original"] == "allow"
    assert record["installer_version"] == __version__


def test_v1_star_ask_is_kept_without_saying_the_chain_will_run(tmp_path, capsys):
    path = tmp_path / "opencode.json"
    path.write_text(
        json.dumps({"permission": {"bash": {"*": "ask", "npm test *": "allow"}}}),
        encoding="utf-8",
    )
    install_opencode_permissions(tmp_path, rule_format="bash")
    bash = json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"]
    assert list(bash)[:2] == ["*", "npm test *"]
    assert bash["*"] == "ask"
    warning = capsys.readouterr().err
    assert 'permission.bash "*": ask -> ask' in warning
    assert "already has" not in warning
    assert "will run" not in warning


def test_recorded_star_is_not_reported_as_a_user_key(tmp_path, capsys):
    install_opencode_permissions(tmp_path, rule_format="bash")
    capsys.readouterr()
    install_opencode_permissions(tmp_path, rule_format="bash")
    warning = capsys.readouterr().err
    assert "already has" not in warning
    assert "Added OpenCode rules" in warning
    assert "Project or agent config" not in warning


def test_exact_bash_collision_overwrites_and_restores_on_uninstall(tmp_path, capsys):
    path = tmp_path / "opencode.json"
    original = {"permission": {"bash": {"git status *": "allow", "ml *": "allow", "*": "allow"}}}
    path.write_text(json.dumps(original), encoding="utf-8")
    install_opencode_permissions(tmp_path, rule_format="bash")
    bash = json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"]
    assert list(bash)[0] == "*" and bash["*"] == "ask"
    assert list(bash)[1] == "git status *"
    assert bash["ml *"] == "ask"
    assert list(bash).index("ml *") > list(bash).index("git status *")
    assert list(bash).index("ml tree") > list(bash).index("ml *")
    backup = json.loads((tmp_path / "opencode.json.bak").read_text(encoding="utf-8"))
    assert backup["permission"]["bash"]["ml *"] == "allow"
    assert backup["permission"]["bash"]["*"] == "allow"
    warning = capsys.readouterr().err
    assert 'permission.bash "ml *": allow -> ask' in warning
    assert 'permission.bash "*": allow -> ask' in warning
    rules = _bash_rules(bash)
    assert combined_shell_effect(["echo x"], rules) == "ask"
    assert combined_shell_effect(["ml tree", "echo x"], rules) == "ask"
    assert combined_shell_effect(["ml tree"], rules) == "allow"
    record = json.loads(manifest_path(path).read_text(encoding="utf-8"))
    assert record["bash"]["bash"]["ml *"]["original"] == "allow"
    assert record["bash"]["bash"]["ml *"]["index"] == 1
    assert "git status *" not in record["bash"]["bash"]
    capsys.readouterr()
    install_opencode_permissions(tmp_path, rule_format="bash")
    assert "->" not in capsys.readouterr().err
    again = json.loads(manifest_path(path).read_text(encoding="utf-8"))
    assert again["bash"]["bash"]["ml *"]["original"] == "allow"
    uninstall_opencode_permissions(tmp_path)
    restored = json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"]
    assert restored == {"git status *": "allow", "ml *": "allow", "*": "allow"}
    assert not manifest_path(path).exists()


def test_stronger_exact_bash_key_is_overwritten(tmp_path, capsys):
    path = tmp_path / "opencode.json"
    path.write_text(
        json.dumps({"permission": {"bash": {"ml *": "deny", "git status *": "allow"}}}),
        encoding="utf-8",
    )
    install_opencode_permissions(tmp_path, rule_format="bash")
    bash = json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"]
    assert list(bash)[:3] == ["*", "git status *", "ml *"]
    assert bash["ml *"] == "ask"
    assert list(bash).count("ml *") == 1
    assert bash["git status *"] == "allow"
    assert 'permission.bash "ml *": deny -> ask' in capsys.readouterr().err
    uninstall_opencode_permissions(tmp_path)
    restored = json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"]
    assert list(restored) == ["ml *", "git status *"]
    assert restored["ml *"] == "deny"


def test_exact_array_collision_overwrites_and_restores_the_original_rule(tmp_path, capsys):
    path = tmp_path / "opencode.json"
    original = {
        "permissions": [
            {"action": "shell", "resource": "ml *", "effect": "allow", "note": "user"},
            {"action": "bash", "resource": "ml login --show-secrets*", "effect": "allow"},
        ]
    }
    path.write_text(json.dumps(original), encoding="utf-8")
    install_opencode_permissions(tmp_path)
    rules = json.loads(path.read_text(encoding="utf-8"))["permissions"]
    assert rules[0]["resource"] == "*" and rules[0]["effect"] == "ask"
    ml_rules = [rule for rule in rules if rule["resource"] == "ml *"]
    assert ml_rules == [{"action": "shell", "resource": "ml *", "effect": "ask"}]
    secret = next(rule for rule in rules if rule["resource"] == "ml login --show-secrets*")
    assert secret["effect"] == "deny"
    assert MARKER not in secret
    backup = json.loads((tmp_path / "opencode.json.bak").read_text(encoding="utf-8"))
    assert backup["permissions"][0]["effect"] == "allow"
    warning = capsys.readouterr().err
    assert 'permissions shell "ml *": allow -> ask' in warning
    assert 'permissions bash "ml login --show-secrets*": allow -> deny' in warning
    record = json.loads(manifest_path(path).read_text(encoding="utf-8"))
    stored = {rule["resource"]: rule for rule in record["permissions"]}
    assert stored["ml *"]["original"]["note"] == "user"
    assert stored["ml *"]["original"]["effect"] == "allow"
    assert record["installer_version"] == __version__
    capsys.readouterr()
    install_opencode_permissions(tmp_path)
    assert "->" not in capsys.readouterr().err
    uninstall_opencode_permissions(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8"))["permissions"] == original["permissions"]
    assert not manifest_path(path).exists()


def test_stronger_array_rule_is_overwritten_with_our_effect():
    merged = merge_opencode_config(
        {"permissions": [{"action": "shell", "resource": "ml *", "effect": "deny"}]},
    )
    matches = [rule for rule in merged["permissions"] if rule["resource"] == "ml *"]
    assert matches == [{"action": "shell", "resource": "ml *", "effect": "ask"}]
    assert merged["permissions"][0]["resource"] == "*"


def test_legacy_marker_is_removed_and_reinstall_uses_the_manifest(tmp_path, capsys):
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({
        "model": "keep",
        MARKER: {"format": "bash", "bash": ["ml *"], "read": [], "skill": []},
        "permissions": [
            {"action": "shell", "resource": "git status *", "effect": "allow"},
            {"action": "shell", "resource": "ml *", "effect": "ask", MARKER: MARKER_VALUE},
        ],
    }), encoding="utf-8")
    install_opencode_permissions(tmp_path)
    document = json.loads(path.read_text(encoding="utf-8"))
    assert MARKER not in document
    assert all(MARKER not in rule for rule in document["permissions"] if isinstance(rule, dict))
    assert document["model"] == "keep"
    resources = [rule["resource"] for rule in document["permissions"] if isinstance(rule, dict)]
    assert resources.count("ml *") == 1
    assert resources.count("*") == 1
    warning = capsys.readouterr().err
    assert "Migrated OpenCode rules" in warning
    assert "Added OpenCode rules" in warning
    install_opencode_permissions(tmp_path)
    assert json.loads(path.read_text(encoding="utf-8")) == document
    uninstall_opencode_permissions(tmp_path)
    removed = json.loads(path.read_text(encoding="utf-8"))
    assert removed["permissions"] == [{"action": "shell", "resource": "git status *", "effect": "allow"}]
    assert not manifest_path(path).exists()


def test_permissions_install_leaves_recorded_bash_until_uninstall(tmp_path):
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({
        "permission": {"bash": {"ml*": "allow", "git status *": "allow"}},
        MARKER: {"format": "bash", "bash": ["ml*"], "read": [], "skill": []},
    }), encoding="utf-8")
    install_opencode_permissions(tmp_path, rule_format="permissions")
    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["permission"]["bash"] == {"ml*": "allow", "git status *": "allow"}
    assert MARKER not in document
    uninstall_opencode_permissions(tmp_path)
    removed = json.loads(path.read_text(encoding="utf-8"))
    assert removed["permission"]["bash"] == {"git status *": "allow"}
    assert "permissions" not in removed


def test_v2_star_allow_warning_says_ask_overrides_it(tmp_path, capsys):
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({
        "permission": {"bash": {"*": "allow", "git status *": "allow"}},
    }), encoding="utf-8")
    install_opencode_permissions(tmp_path, rule_format="permissions")
    warning = capsys.readouterr().err
    assert "ask overrides the allow" in warning
    assert "will run" not in warning
    assert "matches it last" not in warning
    rules = json.loads(path.read_text(encoding="utf-8"))["permissions"]
    bash = [{"action": "shell", "resource": "*", "effect": "allow"}]
    assert combined_shell_effect(["echo hello"], layered_rules(bash, rules)) == "ask"


def test_project_and_agent_files_warn_only_when_they_can_override(tmp_path, capsys, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "opencode.json").write_text(json.dumps({
        "permission": {"bash": {"git status *": "allow"}},
    }), encoding="utf-8")
    monkeypatch.chdir(project)
    install_opencode_permissions(tmp_path / "global", rule_format="bash")
    assert "Project or agent config" not in capsys.readouterr().err

    (project / "opencode.json").write_text(json.dumps({
        "permissions": [{"action": "shell", "resource": "*", "effect": "allow"}],
    }), encoding="utf-8")
    (project / ".opencode").mkdir()
    (project / ".opencode" / "agents").mkdir()
    (project / ".opencode" / "agents" / "review.md").write_text(
        "---\npermission:\n  bash:\n    \"ml*\": allow\n---\n",
        encoding="utf-8",
    )
    install_opencode_permissions(tmp_path / "global2", rule_format="permissions")
    warning = capsys.readouterr().err
    assert "Project or agent config" in warning
    assert "permissions *=allow" in warning
    assert "ml*=allow" in warning

    agents = tmp_path / "with-agent"
    agents.mkdir()
    (agents / "agents").mkdir()
    (agents / "agents" / "local.md").write_text(
        "---\npermission:\n  bash:\n    \"*\": allow\n---\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    install_opencode_permissions(agents, rule_format="bash")
    assert "agent " in capsys.readouterr().err


def test_missing_loaded_rule_rolls_back(tmp_path, monkeypatch):
    path = tmp_path / "opencode.json"
    original = '{"model": "keep"}\n'
    path.write_text(original, encoding="utf-8")

    class Completed:
        def __init__(self):
            self.returncode = 0
            self.stdout = json.dumps({"permission": {"bash": {"git status *": "allow"}}})
            self.stderr = ""

    monkeypatch.setattr(permission_module.shutil, "which", lambda name: "/usr/bin/opencode")
    monkeypatch.setattr(permission_module.subprocess, "run", lambda argv, **kwargs: Completed())
    monkeypatch.setattr(permission_module, "_opencode_debug_config", _DEBUG_CONFIG)
    with pytest.raises(ValueError, match="missing"):
        install_opencode_permissions(tmp_path, rule_format="bash")
    assert path.read_text(encoding="utf-8") == original
    assert (tmp_path / "opencode.json.bak").read_text(encoding="utf-8") == original


def test_debug_failure_redacts_secrets_and_hides_the_dump(monkeypatch):
    dumped = json.dumps({"api_key": "super-secret-value", "token": "another-secret"})
    message = public_debug_failure(2, dumped, "token=super-secret-value\nsecond line should stay hidden")
    assert "exit 2" in message
    assert "token=[redacted]" in message
    assert "super-secret-value" not in message
    assert "second line" not in message
    assert "api_key" not in message

    class Completed:
        def __init__(self):
            self.returncode = 3
            self.stdout = dumped
            self.stderr = "password=hunter2"

    monkeypatch.setattr(permission_module.shutil, "which", lambda name: "/usr/bin/opencode")
    monkeypatch.setattr(permission_module.subprocess, "run", lambda argv, **kwargs: Completed())
    with pytest.raises(ValueError, match="exit 3") as caught:
        _DEBUG_CONFIG(Path("/tmp"))
    text = str(caught.value)
    assert "password=[redacted]" in text
    assert "hunter2" not in text
    assert "super-secret-value" not in text


def test_restrict_backup_uses_icacls_for_the_current_user(tmp_path, monkeypatch):
    path = tmp_path / "opencode.json.bak"
    path.write_text('{"api_key": "secret"}', encoding="utf-8")
    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        if argv == ["whoami"]:
            return type("Completed", (), {"returncode": 0, "stdout": "CONTOSO\\alice\n", "stderr": ""})()
        return type("Completed", (), {"returncode": 0, "stdout": "", "stderr": ""})()

    monkeypatch.setattr("wiserec_cli.opencode_managed.os.name", "nt")
    monkeypatch.delenv("USERNAME", raising=False)
    monkeypatch.setattr("subprocess.run", fake_run)
    restrict_backup(path)
    assert calls == [
        ["whoami"],
        ["icacls", str(path), "/inheritance:r", "/grant:r", "CONTOSO\\alice:(F)"],
    ]


def test_collision_still_installs_the_skill_and_overwrites_the_key(tmp_path, monkeypatch, capsys):
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({"permission": {"bash": {"ml *": "allow"}}}), encoding="utf-8")
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    _v2(monkeypatch, "bash")
    with patch("wiserec_cli.opencode_install.install_resources") as install_resources:
        assert main([]) == 0
    install_resources.assert_called_once()
    warning = capsys.readouterr().err
    assert 'permission.bash "ml *": allow -> ask' in warning
    assert "[错误]" not in warning
    bash = json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"]
    assert bash["ml *"] == "ask"
    assert list(bash)[0] == "*"
    assert main(["--override-conflicts"]) == 2


def _completed(code, stdout="", stderr=""):
    return type("Completed", (), {"returncode": code, "stdout": stdout, "stderr": stderr})()


def _use_real_debug(monkeypatch, completed):
    monkeypatch.setattr(permission_module.shutil, "which", lambda name: "/usr/bin/opencode")
    monkeypatch.setattr(permission_module.subprocess, "run", lambda argv, **kwargs: completed)
    monkeypatch.setattr(permission_module, "_opencode_debug_config", _DEBUG_CONFIG)


def _permission_failure_keeps_skill(tmp_path, monkeypatch, capsys, completed, needle):
    path = tmp_path / "opencode.json"
    original = '{"model": "keep"}\n'
    path.write_text(original, encoding="utf-8")
    _plant_skill(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    _v2(monkeypatch)
    _use_real_debug(monkeypatch, completed)
    with patch("wiserec_cli.opencode_install.install_resources") as install_resources:
        assert main() == 1
    install_resources.assert_not_called()
    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "wiserec-managed.json").exists()
    _assert_prior_skill(tmp_path)
    error = capsys.readouterr().err
    assert needle in error
    assert "were left unchanged" in error
    return error


def test_debug_nonzero_exit_keeps_prior_skill(tmp_path, monkeypatch, capsys):
    error = _permission_failure_keeps_skill(
        tmp_path,
        monkeypatch,
        capsys,
        _completed(1, "", "Authorization: Bearer super-secret-token"),
        "exit 1",
    )
    assert "super-secret-token" not in error
    assert "Authorization: [redacted]" in error


def test_debug_missing_rules_keeps_prior_skill(tmp_path, monkeypatch, capsys):
    loaded = json.dumps({"permissions": [{"action": "shell", "resource": "git status *", "effect": "allow"}]})
    _permission_failure_keeps_skill(
        tmp_path,
        monkeypatch,
        capsys,
        _completed(0, loaded, ""),
        "missing managed rule",
    )


def test_debug_non_json_on_permissions_keeps_prior_skill(tmp_path, monkeypatch, capsys):
    _permission_failure_keeps_skill(
        tmp_path,
        monkeypatch,
        capsys,
        _completed(0, "not-json", ""),
        "not a JSON config object",
    )


def test_skill_copy_failure_restores_the_previous_skill(tmp_path, monkeypatch, capsys):
    import hashlib
    import shutil

    source = tmp_path / "bundle"
    manifest = {}
    for relative in ("skills/wiserec-platform/SKILL.md", "commands/ml.md"):
        bundled = source / relative
        bundled.parent.mkdir(parents=True, exist_ok=True)
        bundled.write_text(relative, encoding="utf-8")
        manifest[relative] = hashlib.sha256(bundled.read_bytes()).hexdigest()
    (source / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr("wiserec_cli.opencode_install.RESOURCE_ROOT", source)

    path = tmp_path / "opencode.json"
    original = '{"model": "keep"}\n'
    path.write_text(original, encoding="utf-8")
    _plant_skill(tmp_path)
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    _v2(monkeypatch)
    real_copyfile = shutil.copyfile
    state = {"failed": False}

    def flaky(src, dst, *args, **kwargs):
        if "wiserec-opencode-backup" in str(dst) or "wiserec-opencode-backup" in str(src):
            return real_copyfile(src, dst, *args, **kwargs)
        if not state["failed"]:
            state["failed"] = True
            raise OSError("disk full")
        return real_copyfile(src, dst, *args, **kwargs)

    with patch("wiserec_cli.opencode_install.shutil.copyfile", side_effect=flaky):
        assert main() == 1
    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "wiserec-managed.json").exists()
    _assert_prior_skill(tmp_path)
    error = capsys.readouterr().err
    assert "disk full" in error
    assert "wiserec-managed.json was removed" in error
    assert "restored from the backup" in error
    assert "permission rules installed" not in error


def test_debug_failure_redacts_bearer_and_basic_headers():
    bearer = public_debug_failure(1, "", "Authorization: Bearer super-secret-token leftover")
    assert "Authorization: [redacted]" in bearer
    assert "super-secret-token" not in bearer
    assert "leftover" not in bearer
    basic = public_debug_failure(1, "", "Authorization: Basic dXNlcjpwYXNz second-part")
    assert "Authorization: [redacted]" in basic
    assert "dXNlcjpwYXNz" not in basic
    assert "second-part" not in basic
    generic = public_debug_failure(1, "", "bearer abc.def.ghi")
    assert "bearer [redacted]" in generic
    assert "abc.def.ghi" not in generic


def test_debug_failure_redacts_proxy_authorization_through_end_of_line():
    basic = public_debug_failure(1, "", "Proxy-Authorization: Basic dXNlcjpwYXNz more-data")
    assert "Proxy-Authorization: [redacted]" in basic
    assert "dXNlcjpwYXNz" not in basic
    assert "more-data" not in basic
    bearer = public_debug_failure(1, "", "proxy-authorization: Bearer aaa.bbb extra")
    assert "proxy-authorization: [redacted]" in bearer
    assert "aaa.bbb" not in bearer
    assert "extra" not in bearer


def test_debug_failure_redacts_cookie_header():
    text = public_debug_failure(1, "", "Cookie: sessionid=cookie-header-secret; theme=light")
    assert "Cookie: [redacted]" in text
    assert "cookie-header-secret" not in text


def test_debug_failure_redacts_set_cookie_header():
    text = public_debug_failure(1, "", "Set-Cookie: sessionid=set-cookie-header-secret; HttpOnly")
    assert "Set-Cookie: [redacted]" in text
    assert "set-cookie-header-secret" not in text


def test_debug_failure_redacts_cookie_key_and_json():
    pair = public_debug_failure(1, "", "cookie=cookie-pair-secret extra")
    assert "cookie=[redacted]" in pair
    assert "cookie-pair-secret" not in pair
    assert "extra" not in pair
    body = public_debug_failure(1, "", '{"cookie": "cookie-json-secret"}')
    assert "cookie-json-secret" not in body
    assert "[redacted]" in body


def test_debug_failure_redacts_set_cookie_key_and_json():
    pair = public_debug_failure(1, "", "set-cookie=set-cookie-pair-secret extra")
    assert "set-cookie=[redacted]" in pair
    assert "set-cookie-pair-secret" not in pair
    assert "extra" not in pair
    body = public_debug_failure(1, "", '{"set-cookie": "set-cookie-json-secret"}')
    assert "set-cookie-json-secret" not in body
    assert "[redacted]" in body


def test_debug_failure_redacts_csrftoken_header_key_and_json():
    header = public_debug_failure(1, "", "csrftoken: csrf-header-secret extra")
    assert "csrftoken: [redacted]" in header
    assert "csrf-header-secret" not in header
    assert "extra" not in header
    pair = public_debug_failure(1, "", "CsrfToken=csrf-pair-secret")
    assert "csrf-pair-secret" not in pair
    assert "[redacted]" in pair
    body = public_debug_failure(1, "", '{"csrftoken": "csrf-json-secret"}')
    assert "csrf-json-secret" not in body
    assert "[redacted]" in body


def test_debug_failure_redacts_sessionid_header_key_and_json():
    header = public_debug_failure(1, "", "sessionid: session-header-secret extra")
    assert "sessionid: [redacted]" in header
    assert "session-header-secret" not in header
    assert "extra" not in header
    pair = public_debug_failure(1, "", "SessionId=session-pair-secret")
    assert "session-pair-secret" not in pair
    assert "[redacted]" in pair
    body = public_debug_failure(1, "", '{"sessionid": "session-json-secret"}')
    assert "session-json-secret" not in body
    assert "[redacted]" in body


def test_debug_failure_does_not_redact_business_id():
    pair = public_debug_failure(1, "", "businessId=biz-pair-value")
    assert "biz-pair-value" in pair
    header = public_debug_failure(1, "", "businessId: biz-header-value")
    assert "biz-header-value" in header
    body = public_debug_failure(1, "", '{"businessId": "biz-json-value"}')
    assert "biz-json-value" in body


def test_global_agent_bash_broad_allow_is_warned(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    narrow = tmp_path / "narrow"
    narrow.mkdir()
    (narrow / "opencode.json").write_text(json.dumps({
        "agent": {"build": {"permission": {"bash": {"git status *": "allow"}}}},
    }), encoding="utf-8")
    install_opencode_permissions(narrow, rule_format="bash")
    assert "Global agent permission.bash broad allow" not in capsys.readouterr().err

    broad = tmp_path / "broad"
    broad.mkdir()
    (broad / "opencode.json").write_text(json.dumps({
        "agent": {"build": {"permission": {"bash": {"*": "allow"}}}},
    }), encoding="utf-8")
    install_opencode_permissions(broad, rule_format="bash")
    warning = capsys.readouterr().err
    assert "Global agent permission.bash broad allow" in warning
    assert "agent.build.permission.bash *=allow" in warning


def test_agent_markdown_bash_shorthand_allow_is_warned(tmp_path, capsys, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    (config / "agents").mkdir()
    (config / "agents" / "build.md").write_text("---\nbash: allow\n---\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    install_opencode_permissions(config, rule_format="bash")
    warning = capsys.readouterr().err
    assert "Project or agent config" in warning
    assert "shell *=allow" in warning


def test_missing_manifest_uninstall_warns_and_reports_unrestored_rules(tmp_path, capsys):
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({
        "permission": {
            "bash": {
                "*": "allow",
                "git status *": "allow",
                "ml *": "ask",
                "ml tree": "allow",
            }
        }
    }), encoding="utf-8")
    uninstall_opencode_permissions(tmp_path)
    bash = json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"]
    assert bash == {"*": "allow", "git status *": "allow"}
    warning = capsys.readouterr().err
    assert "wiserec-managed.json is missing" in warning
    assert 'Could not restore the original value of permission.bash "ml *"' in warning
    assert 'Could not restore the original value of permission.bash "ml tree"' in warning
    assert "git status" not in warning

    array_dir = tmp_path / "array"
    array_dir.mkdir()
    array_path = array_dir / "opencode.json"
    array_path.write_text(json.dumps({
        "permission": {"bash": {"*": "allow"}},
        "permissions": [
            {"action": "shell", "resource": "git status *", "effect": "allow"},
            {"action": "shell", "resource": "ml *", "effect": "ask"},
            {"action": "read", "resource": "*.md", "effect": "allow"},
        ],
    }), encoding="utf-8")
    uninstall_opencode_permissions(array_dir)
    document = json.loads(array_path.read_text(encoding="utf-8"))
    assert document["permission"]["bash"] == {"*": "allow"}
    kept = {(rule["action"], rule["resource"], rule["effect"]) for rule in document["permissions"]}
    assert ("shell", "git status *", "allow") in kept
    assert ("read", "*.md", "allow") in kept
    assert ("shell", "ml *", "ask") not in kept
    warning = capsys.readouterr().err
    assert 'Could not restore the original value of permissions shell "ml *"' in warning


def test_corrupt_manifest_warns_on_install(tmp_path, capsys):
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({
        "permission": {"bash": {"ml *": "ask", "git status *": "allow"}},
    }), encoding="utf-8")
    (tmp_path / "wiserec-managed.json").write_text("{", encoding="utf-8")
    install_opencode_permissions(tmp_path, rule_format="bash")
    warning = capsys.readouterr().err
    assert "wiserec-managed.json is corrupt" in warning
    assert "cannot be restored" in warning
    bash = json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"]
    assert bash["ml *"] == "ask"
    assert bash["git status *"] == "allow"
    json.loads((tmp_path / "wiserec-managed.json").read_text(encoding="utf-8"))


def test_missing_manifest_with_known_rules_warns_on_install(tmp_path, capsys):
    path = tmp_path / "opencode.json"
    path.write_text(json.dumps({"permission": {"bash": {"ml tree": "allow"}}}), encoding="utf-8")
    install_opencode_permissions(tmp_path, rule_format="bash")
    assert "wiserec-managed.json is missing" in capsys.readouterr().err
    assert json.loads(path.read_text(encoding="utf-8"))["permission"]["bash"]["ml tree"] == "allow"


def test_fresh_install_does_not_warn_about_a_missing_manifest(tmp_path, capsys):
    install_opencode_permissions(tmp_path, rule_format="bash")
    assert "wiserec-managed.json is missing" not in capsys.readouterr().err


def test_icacls_failure_is_warned(tmp_path, monkeypatch, capsys):
    path = tmp_path / "opencode.json.bak"
    path.write_text("x", encoding="utf-8")

    def fake_run(argv, **kwargs):
        if argv == ["whoami"]:
            return type("Completed", (), {"returncode": 0, "stdout": "CONTOSO\\alice\n", "stderr": ""})()
        return type("Completed", (), {"returncode": 1, "stdout": "", "stderr": "access denied\n"})()

    monkeypatch.setattr("wiserec_cli.opencode_managed.os.name", "nt")
    monkeypatch.setattr("subprocess.run", fake_run)
    restrict_backup(path)
    warning = capsys.readouterr().err
    assert "icacls failed" in warning
    assert "access denied" in warning

    def no_user(argv, **kwargs):
        return type("Completed", (), {"returncode": 1, "stdout": "", "stderr": "whoami failed\n"})()

    monkeypatch.setattr("subprocess.run", no_user)
    restrict_backup(path)
    warning = capsys.readouterr().err
    assert "whoami did not return" in warning


def test_backup_is_private_before_its_contents_are_written(tmp_path, monkeypatch):
    path = tmp_path / "opencode.json"
    original = '{"api_key": "secret-value"}\n'
    path.write_text(original, encoding="utf-8")
    seen = {}
    real = permission_module.restrict_backup

    def spy(backup):
        seen["mode"] = stat.S_IMODE(backup.stat().st_mode)
        seen["size"] = backup.stat().st_size
        real(backup)

    monkeypatch.setattr(permission_module, "restrict_backup", spy)
    install_opencode_permissions(tmp_path, rule_format="bash")
    assert seen["mode"] == 0o600
    assert seen["size"] == 0
    backup = tmp_path / "opencode.json.bak"
    assert backup.read_text(encoding="utf-8") == original
    assert stat.S_IMODE(backup.stat().st_mode) == 0o600
