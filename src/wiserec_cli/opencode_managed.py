"""Track managed OpenCode rules outside opencode.json.

OpenCode 1.1.1 ``packages/opencode/src/config/config.ts`` defines ``permission.bash``
as a pattern object and marks the top-level config ``.strict()``. From v1.16.0
through v1.18.15, ``packages/opencode/src/config/parse.ts`` rejects unknown
top-level keys (``Unrecognized key``). v1.18.16 switches that parser to
``onExcessProperty: "ignore"``. The installer therefore writes only schema
fields and records what it owns in ``wiserec-managed.json`` beside that file.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .opencode_rulematch import EFFECTS, MARKER, MARKER_VALUE, SHELL_ACTIONS

SIDECAR_NAME = "wiserec-managed.json"
_SECRET = re.compile(
    r"(?i)([\"']?(?:api[_-]?key|access[_-]?key|key|token|secret|password|authorization)[\"']?"
    r"\s*[:=]\s*[\"']?)([^\"'\s,}&]+)"
)
_BASH_ACTIONS = ("bash", "read", "skill")


class MergeReport:
    def __init__(self):
        self.added = []
        self.migrated = []
        self.overrides = []
        self.written_bash = {"bash": [], "read": [], "skill": []}
        self.written_permissions = []
        self.bash_entries = {"bash": {}, "read": {}, "skill": {}}
        self.permission_entries = []


def manifest_path(config_file: Path) -> Path:
    """Sidecar beside ``opencode.json``, not a key inside it."""
    return config_file.parent / SIDECAR_NAME


def load_manifest(config_file: Path) -> dict:
    path = manifest_path(config_file)
    if not path.is_file() or path.is_symlink():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def record_for(config_file: Path) -> dict:
    return load_manifest(config_file)


def save_record(config_file: Path, record: dict) -> None:
    path = manifest_path(config_file)
    if path.is_symlink():
        raise ValueError(f"OpenCode managed manifest must not be a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    _chmod_user_only(path)


def clear_record(config_file: Path) -> None:
    path = manifest_path(config_file)
    if path.is_symlink():
        raise ValueError(f"OpenCode managed manifest must not be a symlink: {path}")
    if path.is_file():
        path.unlink()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def shell_family(action: str) -> str:
    return "shell" if action in SHELL_ACTIONS else action


def take_legacy_marker(config: dict) -> dict:
    """Remove installer-only keys. Return the patterns they recorded."""
    legacy = {"bash": {"bash": [], "read": [], "skill": []}, "permissions": [], "migrated": []}
    record = config.pop(MARKER, None)
    if isinstance(record, dict) and record.get("format") == "bash":
        for action in ("bash", "read", "skill"):
            values = record.get(action, [])
            if isinstance(values, list):
                legacy["bash"][action] = [item for item in values if isinstance(item, str)]
                for item in legacy["bash"][action]:
                    legacy["migrated"].append(f"{action} {item}")
    elif record is not None:
        legacy["migrated"].append("wiserec")
    rules = config.get("permissions")
    if isinstance(rules, list):
        kept = []
        for rule in rules:
            if isinstance(rule, dict) and rule.get(MARKER) == MARKER_VALUE:
                action = rule.get("action")
                resource = rule.get("resource")
                effect = rule.get("effect")
                if isinstance(action, str) and isinstance(resource, str) and effect in EFFECTS:
                    legacy["permissions"].append(
                        {"action": action, "resource": resource, "effect": effect}
                    )
                    legacy["migrated"].append(f"{action} {resource}={effect}")
                continue
            kept.append(rule)
        if kept:
            config["permissions"] = kept
        else:
            config.pop("permissions", None)
    return legacy


def _pattern_names(value) -> list:
    if isinstance(value, dict):
        return [key for key in value if isinstance(key, str)]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, str)]
    return []


def owned_bash_patterns(manifest_entry: dict, legacy: dict) -> dict:
    owned = {"bash": [], "read": [], "skill": []}
    sources = []
    recorded = manifest_entry.get("bash")
    if isinstance(recorded, dict):
        sources.append(recorded)
    sources.append(legacy.get("bash", {}))
    for source in sources:
        if not isinstance(source, dict):
            continue
        for action in owned:
            for pattern in _pattern_names(source.get(action)):
                if pattern not in owned[action]:
                    owned[action].append(pattern)
    return owned


def prior_bash_entries(record: dict) -> dict:
    """Original effects recorded for keys this installer already owns."""
    result = {"bash": {}, "read": {}, "skill": {}}
    source = record.get("bash")
    if not isinstance(source, dict):
        return result
    for action in result:
        value = source.get(action)
        if isinstance(value, dict):
            for pattern, info in value.items():
                if isinstance(pattern, str):
                    result[action][pattern] = _bash_memory(info)
        elif isinstance(value, list):
            for pattern in value:
                if isinstance(pattern, str):
                    result[action][pattern] = {"original": None, "index": None}
    return result


def restored_bash_keys(record: dict) -> set:
    """Bash keys whose user value was put back and must not be dropped again."""
    found = set()
    source = record.get("bash") if isinstance(record, dict) else None
    if not isinstance(source, dict):
        return found
    for action, entries in source.items():
        if not isinstance(entries, dict):
            continue
        for pattern, info in entries.items():
            original = _entry_memory(info)["original"]
            if isinstance(pattern, str) and isinstance(original, str):
                found.add((action, pattern))
    return found


def remembered_permission_entries(record: dict) -> list:
    rules = record.get("permissions")
    if not isinstance(rules, list):
        return []
    return [rule for rule in rules if isinstance(rule, dict)]


def prior_permission_entries(record: dict) -> dict:
    found = {}
    rules = record.get("permissions")
    if not isinstance(rules, list):
        return found
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        action = rule.get("action")
        resource = rule.get("resource")
        if isinstance(action, str) and isinstance(resource, str):
            found[(shell_family(action), resource)] = _entry_memory(rule)
    return found


def _bash_memory(info) -> dict:
    memory = _entry_memory(info)
    if isinstance(info, dict) and info.get("effect") in EFFECTS:
        memory["effect"] = info["effect"]
    return memory


def _entry_memory(info) -> dict:
    if not isinstance(info, dict):
        return {"original": None, "index": None}
    original = info.get("original")
    if original is not None and not isinstance(original, dict) and original not in EFFECTS:
        original = None
    index = info.get("index")
    return {"original": original, "index": index if isinstance(index, int) else None}


def owned_permission_keys(manifest_entry: dict, legacy: dict) -> set:
    owned = set()
    for source in (manifest_entry.get("permissions"), legacy.get("permissions")):
        if not isinstance(source, list):
            continue
        for rule in source:
            if isinstance(rule, dict) and isinstance(rule.get("action"), str) and isinstance(rule.get("resource"), str):
                owned.add((shell_family(rule["action"]), rule["resource"]))
    return owned


def restore_originals(config: dict, record: dict) -> None:
    """Remove keys we added and put back the values we overwrote."""
    _restore_bash(config, record.get("bash"))
    _restore_permissions(config, record.get("permissions"))


def _restore_bash(config: dict, recorded) -> None:
    if not isinstance(recorded, dict):
        return
    permission = config.get("permission")
    if permission is None:
        permission = {}
    elif not isinstance(permission, dict):
        return
    touched = False
    for action in _BASH_ACTIONS:
        entries = recorded.get(action)
        if isinstance(entries, list):
            entries = {pattern: {"original": None, "index": None} for pattern in entries if isinstance(pattern, str)}
        if not isinstance(entries, dict) or not entries:
            continue
        touched = True
        bucket = permission.get(action)
        if not isinstance(bucket, dict):
            bucket = {}
        restores = []
        for pattern, info in entries.items():
            if not isinstance(pattern, str):
                continue
            bucket.pop(pattern, None)
            memory = _entry_memory(info)
            original = memory["original"]
            if isinstance(original, str) and original in EFFECTS:
                restores.append((memory["index"], pattern, original))
        items = _reinsert(list(bucket.items()), restores)
        if items:
            permission[action] = dict(items)
        else:
            permission.pop(action, None)
    if not touched:
        return
    if permission:
        config["permission"] = permission
    else:
        config.pop("permission", None)


def _restore_permissions(config: dict, recorded) -> None:
    if not isinstance(recorded, list) or not recorded:
        return
    rules = config.get("permissions")
    if not isinstance(rules, list):
        rules = []
    owned = set()
    restores = []
    for rule in recorded:
        if not isinstance(rule, dict) or not isinstance(rule.get("action"), str):
            continue
        if not isinstance(rule.get("resource"), str):
            continue
        owned.add((shell_family(rule["action"]), rule["resource"]))
        memory = _entry_memory(rule)
        if isinstance(memory["original"], dict):
            restores.append((memory["index"], memory["original"]))
    kept = []
    for rule in rules:
        if (
            isinstance(rule, dict)
            and isinstance(rule.get("action"), str)
            and isinstance(rule.get("resource"), str)
            and (shell_family(rule["action"]), rule["resource"]) in owned
        ):
            continue
        if isinstance(rule, dict) and rule.get(MARKER) == MARKER_VALUE:
            continue
        kept.append(rule)
    items = _reinsert([(None, rule) for rule in kept], [(index, None, original) for index, original in restores])
    restored = [value for _key, value in items]
    if restored:
        config["permissions"] = restored
    elif "permissions" in config:
        config.pop("permissions", None)


def _reinsert(items: list, restores: list) -> list:
    numbered = []
    tail = []
    for index, key, value in restores:
        if isinstance(index, int):
            numbered.append((index, key, value))
        else:
            tail.append((key, value))
    numbered.sort(key=lambda item: item[0])
    for index, key, value in numbered:
        index = max(0, min(index, len(items)))
        items.insert(index, (key, value))
    items.extend(tail)
    return items


def public_debug_failure(returncode, stdout: str, stderr: str) -> str:
    """Exit code and one redacted line. Never the raw config dump."""
    source = stderr if (stderr or "").strip() else (stdout or "")
    line = next((part.strip() for part in source.splitlines() if part.strip()), "")
    line = _SECRET.sub(r"\1[redacted]", line)
    if len(line) > 180:
        line = line[:180] + "..."
    shown = line or "no error line"
    code = returncode if returncode is not None else "unknown"
    return f"opencode debug config failed (exit {code}): {shown}"


def assert_loaded_rules(loaded: dict, expected: dict) -> None:
    """Require every managed rule, with v1 key order, in the loaded config."""
    if not isinstance(loaded, dict):
        raise ValueError("opencode debug config did not return a JSON config object")
    if expected.get("format") == "bash":
        _assert_bash(loaded, expected)
        return
    _assert_permissions(loaded, expected)


def _assert_bash(loaded: dict, expected: dict) -> None:
    permission = _find_permission(loaded)
    if not isinstance(permission, dict):
        raise ValueError("opencode debug config is missing permission.bash")
    _assert_pattern_object(permission, "bash", expected.get("bash_effects", {}), expected.get("bash_order", []), star_first=True)
    _assert_pattern_object(permission, "read", expected.get("read_effects", {}), expected.get("read_order", []), star_first=False)
    _assert_pattern_object(permission, "skill", expected.get("skill_effects", {}), expected.get("skill_order", []), star_first=False)


def _assert_pattern_object(permission: dict, action: str, effects: dict, order: list, *, star_first: bool) -> None:
    if not effects and not order:
        return
    bucket = permission.get(action)
    if not isinstance(bucket, dict):
        raise ValueError(f"opencode debug config is missing permission.{action}")
    keys = list(bucket)
    if star_first and effects.get("*") == "ask" and (not keys or keys[0] != "*" or bucket.get("*") != "ask"):
        raise ValueError('opencode debug config is missing the leading permission.bash "*": "ask"')
    missing = [pattern for pattern, effect in effects.items() if bucket.get(pattern) != effect]
    if missing:
        raise ValueError(f"opencode debug config is missing managed {action} rules: " + ", ".join(missing))
    positions = {key: index for index, key in enumerate(keys)}
    managed_at = [positions[pattern] for pattern in order if pattern in effects]
    if managed_at != sorted(managed_at):
        raise ValueError(f"opencode debug config does not keep managed {action} rules in order")
    user_at = [index for key, index in positions.items() if key not in effects]
    tail = [index for index in managed_at if not (star_first and keys[index] == "*")]
    if user_at and tail and min(tail) < max(user_at):
        raise ValueError(f"opencode debug config places a managed {action} rule before a user key")


def _assert_permissions(loaded: dict, expected: dict) -> None:
    document = _find_permissions(loaded)
    rules = document.get("permissions") if isinstance(document, dict) else None
    if not isinstance(rules, list):
        raise ValueError("opencode debug config is missing the permissions array")
    wanted = expected.get("permissions", [])
    cursor = 0
    for wanted_rule in wanted:
        found = False
        while cursor < len(rules):
            rule = rules[cursor]
            cursor += 1
            if (
                isinstance(rule, dict)
                and rule.get("action") == wanted_rule["action"]
                and rule.get("resource") == wanted_rule["resource"]
                and rule.get("effect") == wanted_rule["effect"]
                and MARKER not in rule
            ):
                found = True
                break
        if not found:
            raise ValueError(
                "opencode debug config is missing managed rule "
                f"{wanted_rule['action']} {wanted_rule['resource']}={wanted_rule['effect']}"
            )


def _find_permission(document):
    if isinstance(document, dict):
        permission = document.get("permission")
        if isinstance(permission, dict) and isinstance(permission.get("bash"), dict):
            return permission
        for value in document.values():
            found = _find_permission(value)
            if found:
                return found
    return {}


def _find_permissions(document):
    if isinstance(document, dict):
        rules = document.get("permissions")
        if isinstance(rules, list):
            return document
        for value in document.values():
            found = _find_permissions(value)
            if isinstance(found, dict) and found:
                return found
    return {}


def _chmod_user_only(path: Path) -> None:
    if os.name == "nt":
        _icacls_current_user(path)
        return
    os.chmod(path, 0o600)


def restrict_backup(path: Path) -> None:
    """Backups can contain API keys. Limit the file to the current user."""
    _chmod_user_only(path)


def _icacls_current_user(path: Path) -> None:
    import subprocess

    user = os.environ.get("USERNAME") or os.environ.get("USER")
    if not user:
        return
    subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", f"{user}:(F)"],
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
