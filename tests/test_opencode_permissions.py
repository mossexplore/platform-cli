"""OpenCode permission merge, rollback, and the 2026-10-20 bypass regression."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from wiserec_cli.opencode_install import main
from wiserec_cli.opencode_permissions import (
    MARKER,
    MARKER_VALUE,
    SHELL_RULES,
    combined_shell_effect,
    conflicting_allow_rules,
    fresh_opencode_config,
    install_opencode_permissions,
    merge_opencode_config,
    permission_effect,
    uninstall_opencode_permissions,
    wildcard_match,
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
    assert document["permissions"][0] == {
        "action": "shell", "resource": "*", "effect": "ask", MARKER: MARKER_VALUE,
    }
    assert not (tmp_path / "opencode.json.bak").exists()


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
    assert document["permission"] == {"edit": "ask"}
    resources = [rule["resource"] for rule in document["permissions"] if isinstance(rule, dict)]
    assert "ml tree*" in resources
    assert "ml * --help*" in resources
    assert resources.count("*") == 2  # user allow, plus our ask fallback
    assert resources[0] == "*"
    rules = document["permissions"]
    assert rules[0][MARKER] == MARKER_VALUE
    lifted = next(rule for rule in rules if rule["resource"] == "ml tree*")
    assert MARKER not in lifted
    assert resources.count("ml env list") == 1
    assert "opaque-entry" in rules
    assert permission_effect("shell", "git status", rules) == "allow"
    assert permission_effect("shell", "git status --short", rules) == "allow"
    assert permission_effect("shell", "npm test --watch", rules) == "allow"
    assert permission_effect("shell", "rm -rf /tmp/demo", rules) == "deny"
    assert permission_effect("shell", "echo hello", rules) == "allow"
    assert permission_effect("read", "docs/guide.md", rules) == "allow"
    assert permission_effect("read", r"C:\Users\me\.wiserec\credentials.json", rules) == "deny"
    assert combined_shell_effect(["ml tree"], rules) == "allow"
    assert combined_shell_effect([r"ml tree > C:\out.txt"], rules) == "ask"
    assert combined_shell_effect(
        ["ml jupyter exec --cwd x -- sh -c 'echo pwned' --help"], rules
    ) == "ask"
    kept = next(rule for rule in rules if isinstance(rule, dict) and rule["resource"] == "npm test *")
    assert kept["note"] == "keep"


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
    with pytest.raises(ValueError, match="JSON"):
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
    assert "permission" not in merged


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
    user_rules = [rule for rule in rules if rule.get(MARKER) != MARKER_VALUE]
    assert [rule["resource"] for rule in user_rules] == ["ml*", "ml tree*", "git status *"]
    managed = [rule for rule in rules if rule.get(MARKER) == MARKER_VALUE]
    assert rules[0]["resource"] == "*" and rules[0][MARKER] == MARKER_VALUE
    assert rules[1:4] == user_rules
    assert managed[-1]["effect"] == "deny" or managed[-1]["action"] == "read"
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
    marked = [rule for rule in installed["permissions"] if rule.get(MARKER) == MARKER_VALUE]
    assert marked
    assert all(rule[MARKER] == MARKER_VALUE for rule in marked)
    assert len(marked) == len({(rule["action"], rule["resource"]) for rule in marked})
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


def test_invalid_json_aborts_the_install_step(tmp_path, monkeypatch, capsys):
    path = tmp_path / "opencode.json"
    path.write_text("{", encoding="utf-8")
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    with patch("wiserec_cli.opencode_install.install_resources") as install_resources:
        assert main() == 1
    install_resources.assert_not_called()
    assert path.read_text(encoding="utf-8") == "{"
    assert not (tmp_path / "opencode.json.bak").exists()
    assert not (tmp_path / "skills").exists()
    assert "left unchanged" in capsys.readouterr().err


def test_uninstall_flag_removes_marked_rules(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    with patch("wiserec_cli.opencode_install.install_resources"):
        assert main([]) == 0
    assert main(["--uninstall"]) == 0
    document = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert "permissions" not in document
    assert "removed" in capsys.readouterr().err


def test_main_merges_permissions_after_resources(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    with patch("wiserec_cli.opencode_install.install_resources") as install_resources:
        assert main() == 0
    install_resources.assert_called_once_with(tmp_path)
    document = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert document["permissions"][0]["resource"] == "*"
    assert "permission rules installed" in capsys.readouterr().err


def test_main_reports_permission_failure_without_claiming_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OPENCODE_CONFIG_DIR", str(tmp_path))
    with patch("wiserec_cli.opencode_install.install_resources"), patch(
        "wiserec_cli.opencode_install.install_opencode_permissions",
        side_effect=OSError("disk full"),
    ):
        assert main() == 1
    error = capsys.readouterr().err
    assert "CLI remains usable" in error
    assert "permission rules installed" not in error
