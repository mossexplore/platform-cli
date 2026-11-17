"""Synchronize the certificate policy entries owned by the Windows installer."""

from contextlib import contextmanager
from pathlib import Path

from .edge_policy import AUTO_SELECT, PROMPT_ON_MULTIPLE, certificate_rule, rule_covers_origin


EDGE_KEY = r"SOFTWARE\Policies\Microsoft\Edge"
RULES_KEY = f"{EDGE_KEY}\\{AUTO_SELECT}"
STATE_KEY = r"Software\WiseRec\CLI\EdgeClientCertificatePolicy"
# Windows registry value types. Keep the reconciliation logic testable off Windows.
REG_SZ = 1
REG_DWORD = 4
PROMPT_ENABLED = (1, REG_DWORD)
RULES_KEY_OWNER = "owns_rule_list"


class WindowsRegistry:
    def __init__(self):
        import winreg

        self.winreg = winreg

    def has_key(self, path, *, machine=False):
        reg = self.winreg
        hive = reg.HKEY_LOCAL_MACHINE if machine else reg.HKEY_CURRENT_USER
        try:
            with reg.OpenKey(hive, path, 0, reg.KEY_READ | reg.KEY_WOW64_64KEY):
                return True
        except FileNotFoundError:
            return False

    def values(self, path, *, machine=False):
        reg = self.winreg
        hive = reg.HKEY_LOCAL_MACHINE if machine else reg.HKEY_CURRENT_USER
        try:
            with reg.OpenKey(hive, path, 0, reg.KEY_READ | reg.KEY_WOW64_64KEY) as key:
                return {
                    name.casefold(): (value, kind)
                    for name, value, kind in (
                        reg.EnumValue(key, i) for i in range(reg.QueryInfoKey(key)[1])
                    )
                }
        except FileNotFoundError:
            return {}

    def set_user_value(self, path, name, value):
        reg = self.winreg
        data, kind = value
        with reg.CreateKeyEx(
            reg.HKEY_CURRENT_USER, path, 0, reg.KEY_SET_VALUE | reg.KEY_WOW64_64KEY
        ) as key:
            reg.SetValueEx(key, name, 0, kind, data)

    def delete_user_value(self, path, name):
        reg = self.winreg
        try:
            with reg.OpenKey(
                reg.HKEY_CURRENT_USER, path, 0, reg.KEY_SET_VALUE | reg.KEY_WOW64_64KEY
            ) as key:
                reg.DeleteValue(key, name)
        except FileNotFoundError:
            pass

    def delete_empty_user_key(self, path):
        reg = self.winreg
        try:
            with reg.OpenKey(
                reg.HKEY_CURRENT_USER, path, 0, reg.KEY_READ | reg.KEY_WOW64_64KEY
            ) as key:
                subkeys, values, _ = reg.QueryInfoKey(key)
            if subkeys == values == 0:
                reg.DeleteKeyEx(reg.HKEY_CURRENT_USER, path, reg.KEY_WOW64_64KEY)
        except FileNotFoundError:
            pass


@contextmanager
def _installer_lock(path: Path):
    import msvcrt

    # Serialize concurrent installer invocations for this Windows user.
    with path.open("a+b") as lock:
        if lock.tell() == 0:
            lock.write(b"\0")
            lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
        try:
            yield
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)


def synchronize(origins: tuple[str, ...], config_dir: Path) -> str:
    registry = WindowsRegistry()
    if not origins and not registry.values(STATE_KEY):
        return ""
    with _installer_lock(config_dir / ".edge-client-certificate-policy.lock"):
        return _reconcile(registry, origins)


def _reconcile(registry, origins: tuple[str, ...]) -> str:
    state = registry.values(STATE_KEY)
    user_rules = registry.values(RULES_KEY)
    prompt_key = PROMPT_ON_MULTIPLE.casefold()
    user_policy = registry.values(EDGE_KEY)
    machine_policy = registry.values(EDGE_KEY, machine=True)
    user_prompt = user_policy.get(prompt_key)
    machine_prompt = machine_policy.get(prompt_key)
    effective_prompt = user_prompt if machine_prompt is None else machine_prompt

    warning = ""
    if origins:
        if AUTO_SELECT.casefold() in machine_policy or registry.has_key(RULES_KEY, machine=True):
            warning = (
                "Computer-level Edge certificate policy takes precedence. Ask IT to merge "
                "the configured origins and enable multiple-certificate prompts."
            )
        elif AUTO_SELECT.casefold() in user_policy:
            warning = "Existing Edge certificate policy uses a single registry value. Ask IT to merge the configured origins."
        elif effective_prompt not in (None, PROMPT_ENABLED):
            warning = (
                "Existing Edge policy does not enable multiple-certificate prompts. "
                "Ask IT to enable PromptOnMultipleMatchingCertificates."
            )
    if warning:
        origins = ()

    owned = {
        name: value for name, value in state.items()
        if name.isdecimal() and value == user_rules.get(name)
    }
    external = [
        value for name, (value, kind) in user_rules.items()
        if name not in owned and name.isdecimal() and kind == REG_SZ
    ]
    wanted = {
        (certificate_rule(origin), REG_SZ)
        for origin in origins
        if not any(rule_covers_origin(rule, origin) for rule in external)
    }
    for name in state:
        if not name.isdecimal():
            continue
        if name in owned and owned[name] in wanted:
            wanted.remove(owned[name])
            continue
        if name in owned:
            registry.delete_user_value(RULES_KEY, name)
            del user_rules[name]
        registry.delete_user_value(STATE_KEY, name)

    if not origins:
        if state.get(RULES_KEY_OWNER) == PROMPT_ENABLED:
            if not user_rules:
                registry.delete_empty_user_key(RULES_KEY)
            registry.delete_user_value(STATE_KEY, RULES_KEY_OWNER)
        if state.get(prompt_key) == PROMPT_ENABLED:
            if user_prompt == PROMPT_ENABLED:
                registry.delete_user_value(EDGE_KEY, PROMPT_ON_MULTIPLE)
            registry.delete_user_value(STATE_KEY, PROMPT_ON_MULTIPLE)
        return warning

    if effective_prompt is None:
        registry.set_user_value(STATE_KEY, PROMPT_ON_MULTIPLE, PROMPT_ENABLED)
        registry.set_user_value(EDGE_KEY, PROMPT_ON_MULTIPLE, PROMPT_ENABLED)
    elif user_prompt != PROMPT_ENABLED and prompt_key in state:
        registry.delete_user_value(STATE_KEY, PROMPT_ON_MULTIPLE)

    if wanted and not user_rules and not registry.has_key(RULES_KEY):
        registry.set_user_value(STATE_KEY, RULES_KEY_OWNER, PROMPT_ENABLED)
    slot = 1
    for rule in sorted(wanted):
        while str(slot) in user_rules:
            slot += 1
        name = str(slot)
        # Record ownership first so a retry can recover from an interrupted write.
        registry.set_user_value(STATE_KEY, name, rule)
        registry.set_user_value(RULES_KEY, name, rule)
        slot += 1
    return warning
