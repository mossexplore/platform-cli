"""Track managed OpenCode rules outside opencode.json.

OpenCode 1.1.1 ``packages/opencode/src/config/config.ts`` defines ``permission.bash``
as a pattern object and marks the top-level config ``.strict()``. From v1.16.0
through v1.18.15, ``packages/opencode/src/config/parse.ts`` rejects unknown
top-level keys (``Unrecognized key``). v1.18.16 switches that parser to
``onExcessProperty: "ignore"``. The installer therefore writes only schema
fields and records what it owns in ``~/.wiserec/opencode-managed.json``.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from .opencode_rulematch import EFFECTS, MARKER, MARKER_VALUE, SHELL_ACTIONS

_STRENGTH = {"allow": 0, "ask": 1, "deny": 2}
_SECRET = re.compile(
    r"(?i)([\"']?(?:api[_-]?key|access[_-]?key|key|token|secret|password|authorization)[\"']?"
    r"\s*[:=]\s*[\"']?)([^\"'\s,}&]+)"
)


class OpenCodeConflictError(ValueError):
    """A user rule is more permissive than the managed rule for the same key."""

    def __init__(self, conflicts: list):
        self.conflicts = conflicts
        listed = "; ".join(
            f"{item['where']} {item['key']} is {item['user']}, managed rule is {item['ours']}"
            for item in conflicts
        )
        super().__init__(
            "OpenCode config has weaker rules that would bypass the managed ask/deny rules: "
            f"{listed}. opencode.json was left unchanged. "
            "Rerun with --override-conflicts to set the managed effect and move those keys "
            "into the managed block. The original file is preserved in the backup when that flag is used."
        )


class MergeReport:
    def __init__(self):
        self.added = []
        self.migrated = []
        self.overrides = []
        self.written_bash = {"bash": [], "read": [], "skill": []}
        self.written_permissions = []


def manifest_path() -> Path:
    root = Path(os.environ.get("WISEREC_HOME") or Path.home() / ".wiserec")
    return root / "opencode-managed.json"


def load_manifest() -> dict:
    path = manifest_path()
    if not path.is_file() or path.is_symlink():
        return {"targets": {}}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"targets": {}}
    if not isinstance(loaded, dict) or not isinstance(loaded.get("targets"), dict):
        return {"targets": {}}
    return loaded


def record_for(config_file: Path) -> dict:
    entry = load_manifest()["targets"].get(str(config_file.resolve()), {})
    return entry if isinstance(entry, dict) else {}


def save_record(config_file: Path, record: dict) -> None:
    path = manifest_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    document = load_manifest()
    document["targets"][str(config_file.resolve())] = record
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)
    _chmod_user_only(path)


def clear_record(config_file: Path) -> None:
    document = load_manifest()
    document["targets"].pop(str(config_file.resolve()), None)
    path = manifest_path()
    if not document["targets"]:
        if path.is_file() and not path.is_symlink():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    _chmod_user_only(path)


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def weaker(user_effect: str, managed_effect: str) -> bool:
    return _STRENGTH.get(user_effect, -1) < _STRENGTH.get(managed_effect, -1)


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


def owned_bash_patterns(manifest_entry: dict, legacy: dict) -> dict:
    owned = {"bash": [], "read": [], "skill": []}
    sources = []
    recorded = manifest_entry.get("bash")
    if isinstance(recorded, dict):
        sources.append(recorded)
    sources.append(legacy.get("bash", {}))
    for source in sources:
        for action in owned:
            for pattern in source.get(action, []) if isinstance(source, dict) else []:
                if isinstance(pattern, str) and pattern not in owned[action]:
                    owned[action].append(pattern)
    return owned


def owned_permission_keys(manifest_entry: dict, legacy: dict) -> set:
    owned = set()
    for source in (manifest_entry.get("permissions"), legacy.get("permissions")):
        if not isinstance(source, list):
            continue
        for rule in source:
            if isinstance(rule, dict) and isinstance(rule.get("action"), str) and isinstance(rule.get("resource"), str):
                owned.add((shell_family(rule["action"]), rule["resource"]))
    return owned


def describe_conflict(where: str, key: str, user_effect: str, managed_effect: str) -> dict:
    return {"where": where, "key": key, "user": user_effect, "ours": managed_effect}


def raise_if_conflicts(conflicts: list, override_conflicts: bool) -> None:
    if conflicts and not override_conflicts:
        raise OpenCodeConflictError(conflicts)


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
