"""Merge Windows OpenCode permission rules into the user config.

OpenCode 1.1.1 through 1.x stores shell rules on ``permission.bash``. The
current GitHub release, v1.19.3, rejects a top-level ``permissions`` array.
OpenCode 2.0.0 and newer accept that array of ``{action, resource, effect}``.
The installer detects ``opencode --version`` and writes only the shape that
release understands. User ``permission.bash`` and ``permission.shell`` entries
stay in place.

Within the v2 array the order is fixed: user non-shell rules, the shell
``*`` ask fallback, user shell rules, then managed rules. The fallback asks
for every shell command, not only ``ml``.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import messages as msg
from .opencode_bash_rules import drop_recorded_bash_patterns, merge_bash_rules
from .opencode_rulematch import (
    BROAD_RESOURCES,
    MARKER,
    MARKER_VALUE,
    OTHER_RULES,
    PROTECTED_COMMANDS,
    SHELL_ACTIONS,
    SHELL_RULES,
    combined_shell_effect,
    is_rule,
    layered_rules,
    permission_effect,
    wildcard_match,
)

SCHEMA = "https://opencode.ai/config.json"
# v1.1.1 release notes introduced granular permission.bash patterns.
MINIMUM_BASH = (1, 1, 1)
# Tag v2.0.0 is the first tree whose schema declares the permissions array.
MINIMUM_PERMISSIONS = (2, 0, 0)
_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_COMMENT = re.compile(r"(?<!:)//|/\*")
class OpenCodeVersionError(ValueError):
    """The installed OpenCode cannot be identified or is too old to update."""


def fresh_opencode_config() -> dict:
    """Config written for OpenCode 2 when the user has no opencode.json yet."""
    return merge_opencode_config({"$schema": SCHEMA}, rule_format="permissions")


def fresh_bash_config() -> dict:
    """Config written for OpenCode 1.1.1+ when the user has no opencode.json yet."""
    return merge_opencode_config({"$schema": SCHEMA}, rule_format="bash")


def merge_opencode_config(config: dict, *, rule_format: str = "permissions") -> dict:
    """Return a new document. User permission.bash and permission.shell stay."""
    if not isinstance(config, dict):
        raise ValueError("OpenCode config must be a JSON object")
    if rule_format not in {"permissions", "bash"}:
        raise ValueError(f"Unknown OpenCode rule format: {rule_format}")
    result = json.loads(json.dumps(config))
    if rule_format == "permissions":
        drop_recorded_bash_patterns(result)
        existing = result.get("permissions", [])
        if existing is None:
            existing = []
        if not isinstance(existing, list):
            raise ValueError("OpenCode permissions must be an array")
        result["permissions"] = _merge_rules(existing)
        return result
    _drop_marked_array_rules(result)
    merge_bash_rules(result)
    return result


def permission_format_for_version(version: str) -> str:
    """Return ``permissions`` for OpenCode 2+, ``bash`` for 1.1.1 through 1.x."""
    parsed = _parse_version(version)
    if parsed is None:
        raise OpenCodeVersionError(
            "OpenCode version could not be read. Install OpenCode 1.1.1 or newer and rerun. "
            "opencode.json was left unchanged."
        )
    if parsed >= MINIMUM_PERMISSIONS:
        return "permissions"
    if parsed >= MINIMUM_BASH:
        return "bash"
    found = ".".join(str(part) for part in parsed)
    raise OpenCodeVersionError(
        f"OpenCode {found} is older than 1.1.1. Permission rules were not written. "
        "opencode.json was left unchanged."
    )


def detect_permission_format(run_version=None) -> str:
    """Read ``opencode --version``, or ``opencode2 --version`` when opencode is absent."""
    run_version = run_version or _command_version
    text = run_version("opencode")
    if text is None:
        text = run_version("opencode2")
    if text is None:
        raise OpenCodeVersionError(
            "OpenCode version could not be detected. Install OpenCode 1.1.1 or newer and rerun. "
            "opencode.json was left unchanged."
        )
    return permission_format_for_version(text)


def validate_opencode_config(target: Path) -> None:
    """Parse an existing config or raise. Does not create or modify files."""
    if not target.exists() and not target.is_symlink():
        return
    if target.is_symlink():
        raise ValueError(f"OpenCode directory must not be a symlink: {target}")
    path = _config_path(target)
    if not path.exists() and not path.is_symlink():
        return
    _read_config_file(path)


def install_opencode_permissions(target: Path, *, rule_format: str = "permissions") -> None:
    """Merge managed rules, backing up the original without overwriting ``.bak``."""
    if target.is_symlink():
        raise ValueError(f"OpenCode directory must not be a symlink: {target}")
    target.mkdir(parents=True, exist_ok=True)
    path = _config_path(target)
    original, config = _read_existing(path)
    merged = merge_opencode_config(config, rule_format=rule_format)
    _warn_user_allows(config, merged)
    rendered = _dump(merged)
    if original is not None and _normalize_newlines(_decode(original)) == rendered:
        return
    _replace_with_rollback(path, rendered, original)


def uninstall_opencode_permissions(target: Path) -> None:
    """Remove rules tagged as WiseRec managed. User rules stay."""
    if not target.exists() and not target.is_symlink():
        return
    if target.is_symlink():
        raise ValueError(f"OpenCode directory must not be a symlink: {target}")
    path = _config_path(target)
    if not path.exists() and not path.is_symlink():
        return
    original, config = _read_existing(path)
    if not _remove_managed(config):
        return
    _replace_with_rollback(path, _dump(config), original)


def conflicting_allow_rules(rules) -> list:
    """User wildcard allows that match a command our ask/deny rules govern."""
    found = []
    seen = set()
    for rule in rules:
        if not is_rule(rule) or _is_ours(rule) or rule["effect"] != "allow":
            continue
        if rule["action"] not in SHELL_ACTIONS:
            continue
        resource = rule["resource"]
        if "*" not in resource and "?" not in resource:
            continue
        folded = resource.lower()
        if not (folded.startswith("ml") or folded.startswith("*")):
            continue
        if not any(wildcard_match(command, resource) for command in PROTECTED_COMMANDS):
            continue
        key = (rule["action"], resource, rule["effect"])
        if key in seen:
            continue
        seen.add(key)
        found.append(rule)
    return found


def broad_allow_rules(rules) -> list:
    """Catch-all shell allows such as ``*`` that override the ask fallback."""
    found = []
    seen = set()
    for rule in rules:
        if not is_rule(rule) or _is_ours(rule) or rule["effect"] != "allow":
            continue
        if rule["action"] not in SHELL_ACTIONS:
            continue
        if rule["resource"].lower() not in BROAD_RESOURCES:
            continue
        key = (rule["action"], rule["resource"], rule["effect"])
        if key in seen:
            continue
        seen.add(key)
        found.append(rule)
    return found


def _merge_rules(items: list) -> list:
    """User non-shell rules, shell ``*`` ask, user shell rules, then ours.

    OpenCode keeps the last match. This order is the one the array must keep.
    """
    opaque = []
    user_other = []
    user_shell = []
    for item in items:
        if not is_rule(item):
            opaque.append(item)
            continue
        if _is_ours(item):
            continue
        copied = dict(item)
        if item["action"] in SHELL_ACTIONS:
            user_shell.append(copied)
        else:
            user_other.append(copied)
    managed_shell = [_rule("shell", resource, effect) for resource, effect in SHELL_RULES]
    managed_other = [_rule(action, resource, effect) for action, resource, effect in OTHER_RULES]
    return [
        *opaque,
        *user_other,
        _rule("shell", "*", "ask"),
        *user_shell,
        *managed_shell,
        *managed_other,
    ]


def _drop_marked_array_rules(config: dict) -> None:
    rules = config.get("permissions")
    if not isinstance(rules, list):
        return
    kept = [rule for rule in rules if not _is_ours(rule)]
    if kept:
        config["permissions"] = kept
    else:
        config.pop("permissions", None)


def _remove_managed(config: dict) -> bool:
    before = json.dumps(config, sort_keys=True)
    _drop_marked_array_rules(config)
    drop_recorded_bash_patterns(config)
    rules = config.get("permissions")
    if isinstance(rules, list):
        kept = [rule for rule in rules if not _is_ours(rule)]
        if kept:
            config["permissions"] = kept
        elif not kept:
            config.pop("permissions", None)
    return json.dumps(config, sort_keys=True) != before


def _warn_user_allows(original: dict, merged: dict) -> None:
    rules = []
    if isinstance(merged.get("permissions"), list):
        rules.extend(rule for rule in merged["permissions"] if not _is_ours(rule))
    rules.extend(_legacy_allow_rules(original.get("permission")))
    rules.extend(_legacy_allow_rules(merged.get("permission")))
    broad = broad_allow_rules(rules)
    if broad:
        listed = ", ".join(
            f"{rule['action']} {rule['resource']}={rule['effect']}" for rule in broad
        )
        msg.warning(
            "OpenCode has a broad shell allow. The * ask fallback applies to every shell "
            "command, but this allow stays in place and wins for commands it matches last: "
            + listed
        )
    conflicts = conflicting_allow_rules(rules)
    if conflicts:
        listed = ", ".join(
            f"{rule['action']} {rule['resource']}={rule['effect']}" for rule in conflicts
        )
        msg.warning(
            "OpenCode allow rules conflict with WiseRec ask/deny rules and were kept: "
            + listed
        )


def _legacy_allow_rules(permission) -> list:
    if permission is None:
        return []
    if isinstance(permission, str):
        return [_plain("shell", "*", permission)] if permission == "allow" else []
    if not isinstance(permission, dict):
        return []
    rules = []
    for action in ("bash", "shell", "*"):
        value = permission.get(action)
        if isinstance(value, str) and value == "allow":
            rules.append(_plain(action if action != "*" else "shell", "*", "allow"))
        elif isinstance(value, dict):
            for resource, effect in value.items():
                if isinstance(resource, str) and effect == "allow":
                    rules.append(_plain("shell" if action == "bash" else action, resource, effect))
    return rules


def _plain(action: str, resource: str, effect: str) -> dict:
    return {"action": action, "resource": resource, "effect": effect}


def _is_ours(rule) -> bool:
    return isinstance(rule, dict) and rule.get(MARKER) == MARKER_VALUE


def _rule(action: str, resource: str, effect: str) -> dict:
    return {"action": action, "resource": resource, "effect": effect, MARKER: MARKER_VALUE}


def _parse_version(text: str):
    if not text:
        return None
    match = _VERSION.search(text)
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _command_version(name: str):
    resolved = shutil.which(name)
    if not resolved:
        return None
    try:
        completed = subprocess.run(
            [resolved, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return (completed.stdout or completed.stderr or "").strip()


def _read_existing(path: Path):
    if path.is_symlink():
        raise ValueError(f"OpenCode config must not be a symlink: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"OpenCode config must be a file: {path}")
    if not path.is_file():
        return None, {"$schema": SCHEMA}
    original = path.read_bytes()
    return original, _load_config(original, path.name)


def _read_config_file(path: Path) -> dict:
    if path.is_symlink():
        raise ValueError(f"OpenCode config must not be a symlink: {path}")
    if not path.is_file():
        raise ValueError(f"OpenCode config must be a file: {path}")
    return _load_config(path.read_bytes(), path.name)


def _config_path(target: Path) -> Path:
    json_path = target / "opencode.json"
    jsonc_path = target / "opencode.jsonc"
    json_present = json_path.exists() or json_path.is_symlink()
    jsonc_present = jsonc_path.exists() or jsonc_path.is_symlink()
    if json_present and jsonc_present:
        raise ValueError(
            "Both opencode.json and opencode.jsonc exist. OpenCode loads jsonc after json. "
            "Combine them into opencode.json and remove opencode.jsonc, then rerun the installer."
        )
    if jsonc_present:
        return jsonc_path
    return json_path


def _load_config(original: bytes, name: str = "opencode.json") -> dict:
    try:
        text = _decode(original)
    except UnicodeError as error:
        raise ValueError("OpenCode config must be UTF-8") from error
    if not text.strip():
        return {}
    try:
        config = json.loads(text)
    except json.JSONDecodeError as error:
        if _COMMENT.search(text):
            raise ValueError(
                f"{name} contains comments. This installer does not continue with JSONC comments. "
                "Remove the comments and rerun. The file was left unchanged."
            ) from error
        raise ValueError(
            f"{name} is not strict JSON ({error}). The installer stopped. The file was left unchanged."
        ) from error
    if not isinstance(config, dict):
        raise ValueError("OpenCode config must be a JSON object")
    return config


def _decode(original: bytes) -> str:
    return original.decode("utf-8-sig")


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _dump(config: dict) -> str:
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"


def _backup_path(path: Path) -> Path:
    primary = path.with_name(path.name + ".bak")
    if not primary.exists() and not primary.is_symlink():
        return primary
    stamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    candidate = path.with_name(f"{path.name}.bak.{stamp}")
    suffix = 2
    while candidate.exists() or candidate.is_symlink():
        candidate = path.with_name(f"{path.name}.bak.{stamp}-{suffix}")
        suffix += 1
    return candidate


def _replace_with_rollback(path: Path, rendered: str, original: bytes | None) -> None:
    backup = _backup_path(path) if original is not None else None
    temporary = path.with_name(path.name + ".wiserec-tmp")
    if original is not None and backup is not None:
        backup.write_bytes(original)
    try:
        temporary.write_bytes(rendered.encode("utf-8"))
        loaded = json.loads(temporary.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("OpenCode config must be a JSON object")
        os.replace(temporary, path)
        confirmed = json.loads(path.read_text(encoding="utf-8"))
        if confirmed != loaded:
            raise ValueError("OpenCode config verification failed")
    except Exception as error:
        temporary.unlink(missing_ok=True)
        try:
            _restore(path, original)
        except Exception as restore_error:
            raise RuntimeError(
                f"OpenCode config restore failed; backup is {backup}"
            ) from restore_error
        raise


def _restore(path: Path, original: bytes | None) -> None:
    if original is None:
        if path.is_file() and not path.is_symlink():
            path.unlink()
        return
    path.write_bytes(original)


__all__ = [
    "MARKER",
    "MARKER_VALUE",
    "MINIMUM_BASH",
    "MINIMUM_PERMISSIONS",
    "SHELL_RULES",
    "OpenCodeVersionError",
    "broad_allow_rules",
    "combined_shell_effect",
    "conflicting_allow_rules",
    "detect_permission_format",
    "fresh_bash_config",
    "fresh_opencode_config",
    "install_opencode_permissions",
    "layered_rules",
    "merge_opencode_config",
    "permission_effect",
    "permission_format_for_version",
    "uninstall_opencode_permissions",
    "validate_opencode_config",
    "wildcard_match",
]
