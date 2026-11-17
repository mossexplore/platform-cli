import json
import sys
from uuid import uuid4

import pytest

from wiserec_cli import windows_edge_policy as edge
from wiserec_cli.config import ConfigManager
from wiserec_cli.edge_policy import AUTO_SELECT, PROMPT_ON_MULTIPLE, certificate_rule
from wiserec_cli.errors import ConfigError
from wiserec_cli.install_config import install_config


FIRST = "https://sso.example.com:443"
SECOND = "https://auth.example.com:8443"
PROMPT = PROMPT_ON_MULTIPLE.casefold()


def rule(origin):
    return certificate_rule(origin), edge.REG_SZ


class MemoryRegistry:
    def __init__(self):
        self.user = {}
        self.machine = {}
        self.writes = []

    def values(self, path, *, machine=False):
        return dict((self.machine if machine else self.user).get(path, {}))

    def has_key(self, path, *, machine=False):
        return path in (self.machine if machine else self.user)

    def set_user_value(self, path, name, value):
        self.user.setdefault(path, {})[name.casefold()] = value
        self.writes.append((path, name, value))

    def delete_user_value(self, path, name):
        self.user.get(path, {}).pop(name.casefold(), None)

    def delete_empty_user_key(self, path):
        if not self.user.get(path):
            self.user.pop(path, None)


def test_reinstall_updates_and_removes_only_owned_entries():
    registry = MemoryRegistry()
    existing = rule("https://other.example.com:443")
    registry.user[edge.RULES_KEY] = {"1": existing}

    assert edge._reconcile(registry, (FIRST,)) == ""
    assert registry.values(edge.RULES_KEY) == {"1": existing, "2": rule(FIRST)}
    assert registry.values(edge.EDGE_KEY)[PROMPT] == edge.PROMPT_ENABLED
    assert registry.writes.index(
        (edge.EDGE_KEY, PROMPT_ON_MULTIPLE, edge.PROMPT_ENABLED)
    ) < registry.writes.index((edge.RULES_KEY, "2", rule(FIRST)))

    registry.writes.clear()
    edge._reconcile(registry, (FIRST,))
    assert registry.writes == []

    edge._reconcile(registry, (SECOND,))
    assert registry.values(edge.RULES_KEY) == {"1": existing, "2": rule(SECOND)}
    edge._reconcile(registry, ())
    assert registry.values(edge.RULES_KEY) == {"1": existing}
    assert registry.values(edge.EDGE_KEY) == {}
    assert registry.values(edge.STATE_KEY) == {}


def test_keeps_overlapping_external_filters_and_other_policy_values():
    registry = MemoryRegistry()
    external = (json.dumps({
        "pattern": "https://[*.]example.com:443",
        "filter": {"ISSUER": {"CN": "Corporate CA"}},
    }), edge.REG_SZ)
    registry.user[edge.RULES_KEY] = {"1": external}
    registry.user[edge.EDGE_KEY] = {PROMPT: edge.PROMPT_ENABLED}

    edge._reconcile(registry, (FIRST, SECOND))
    assert registry.values(edge.RULES_KEY) == {"1": external, "2": rule(SECOND)}
    edge._reconcile(registry, ())
    assert registry.values(edge.EDGE_KEY) == {PROMPT: edge.PROMPT_ENABLED}
    assert registry.values(edge.RULES_KEY) == {"1": external}


def test_does_not_delete_a_rule_changed_since_the_installer_created_it():
    registry = MemoryRegistry()
    edge._reconcile(registry, (FIRST,))
    registry.user[edge.RULES_KEY]["1"] = rule(SECOND)

    edge._reconcile(registry, ())
    assert registry.values(edge.RULES_KEY) == {"1": rule(SECOND)}
    assert registry.values(edge.STATE_KEY) == {}


def test_removing_configuration_does_not_leave_an_empty_edge_list():
    registry = MemoryRegistry()
    edge._reconcile(registry, (FIRST,))
    edge._reconcile(registry, ())
    assert not registry.has_key(edge.RULES_KEY)

    registry.user[edge.RULES_KEY] = {}
    edge._reconcile(registry, (FIRST,))
    edge._reconcile(registry, ())
    assert registry.has_key(edge.RULES_KEY)


@pytest.mark.parametrize("machine_policy", [
    {edge.RULES_KEY: {"1": rule(SECOND)}},
    {edge.EDGE_KEY: {AUTO_SELECT.casefold(): ("[]", edge.REG_SZ)}},
    {edge.EDGE_KEY: {PROMPT: (0, edge.REG_DWORD)}},
])
def test_machine_policy_takes_precedence_and_retires_owned_rules(machine_policy):
    registry = MemoryRegistry()
    edge._reconcile(registry, (FIRST,))
    registry.machine = machine_policy

    assert "Ask IT" in edge._reconcile(registry, (FIRST,))
    assert registry.values(edge.RULES_KEY) == {}
    assert registry.values(edge.EDGE_KEY) == {}
    assert registry.machine == machine_policy


def test_leaves_an_explicitly_disabled_user_prompt_alone():
    registry = MemoryRegistry()
    registry.user[edge.EDGE_KEY] = {PROMPT: (0, edge.REG_DWORD)}
    assert "Ask IT" in edge._reconcile(registry, (FIRST,))
    assert registry.values(edge.RULES_KEY) == {}
    assert registry.values(edge.EDGE_KEY) == {PROMPT: (0, edge.REG_DWORD)}


def packaged_settings(origins):
    return {
        "current": "test",
        "profiles": [
            {"name": "test", "api_endpoint": "https://console.example.com"},
            {"name": "dev", "api_endpoint": "https://dev.example.com",
             "client_certificate_origins": origins},
        ],
    }


def test_windows_install_reads_all_packaged_profiles_and_synchronizes(tmp_path, monkeypatch):
    template = packaged_settings(["https://SSO.example.com", FIRST, SECOND])
    destination = tmp_path / "config.json"
    calls = []
    monkeypatch.setattr("wiserec_cli.install_config.packaged_config_text", lambda: json.dumps(template))

    def synchronize(origins, config_dir):
        calls.append((origins, config_dir))
        assert ConfigManager(destination).current_name == "test"
        return ""

    monkeypatch.setattr(edge, "synchronize", synchronize)
    install_config(destination, sync_edge_policy=True)
    assert calls == [((FIRST, SECOND), tmp_path)]
    assert json.loads(destination.read_text(encoding="utf-8")) == template

    install_config(destination)
    assert len(calls) == 1


@pytest.mark.parametrize("origins", [None, FIRST, [2], ["https://[*.]example.com"]])
def test_rejects_invalid_config_before_install(tmp_path, monkeypatch, origins):
    monkeypatch.setattr(
        "wiserec_cli.install_config.packaged_config_text",
        lambda: json.dumps(packaged_settings(origins)),
    )
    destination = tmp_path / "config.json"
    with pytest.raises(ConfigError, match="client_certificate_origins"):
        install_config(destination, sync_edge_policy=True)
    assert not destination.exists()


@pytest.mark.skipif(sys.platform != "win32", reason="requires the Windows registry")
def test_windows_registry_sync_in_isolated_key(tmp_path, monkeypatch):
    import winreg

    root = f"Software\\WiseRecCLITest-{uuid4()}"
    for attr, path in {
        "EDGE_KEY": root, "RULES_KEY": root + "\\Rules", "STATE_KEY": root + "\\State"
    }.items():
        monkeypatch.setattr(edge, attr, path)
    try:
        assert edge.synchronize((FIRST,), tmp_path) == ""
        registry = edge.WindowsRegistry()
        assert registry.values(edge.RULES_KEY) == {"1": rule(FIRST)}
        assert registry.values(edge.EDGE_KEY)[PROMPT] == edge.PROMPT_ENABLED
        assert edge.synchronize((), tmp_path) == ""
        assert not registry.has_key(edge.RULES_KEY)
        assert registry.values(edge.EDGE_KEY) == {}
    finally:
        for path in (edge.RULES_KEY, edge.STATE_KEY, root):
            try:
                winreg.DeleteKeyEx(winreg.HKEY_CURRENT_USER, path, winreg.KEY_WOW64_64KEY)
            except FileNotFoundError:
                pass
