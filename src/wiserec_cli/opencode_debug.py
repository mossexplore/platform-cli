"""Post-write ``opencode debug config`` check and redacted failure text."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .opencode_rulematch import MARKER

_HEADER = re.compile(r"(?i)((?:authorization\s*[:=]\s*)?(?:bearer|basic)\s+)\S+")
_SECRET = re.compile(
    r"(?i)([\"']?(?:api[_-]?key|access[_-]?key|key|token|secret|password|authorization)[\"']?"
    r"\s*[:=]\s*[\"']?)([^\"'\s,}&]+)"
)


def _redact_secret(match: re.Match) -> str:
    value = match.group(2)
    if value.lower() in {"bearer", "basic"}:
        return match.group(0)
    return f"{match.group(1)}[redacted]"


def public_debug_failure(returncode, stdout: str, stderr: str) -> str:
    """Exit code and one redacted line. Never the raw config dump."""
    source = stderr if (stderr or "").strip() else (stdout or "")
    line = next((part.strip() for part in source.splitlines() if part.strip()), "")
    line = _HEADER.sub(r"\1[redacted]", line)
    line = _SECRET.sub(_redact_secret, line)
    if len(line) > 180:
        line = line[:180] + "..."
    shown = line or "no error line"
    code = returncode if returncode is not None else "unknown"
    return f"opencode debug config failed (exit {code}): {shown}"


def run_debug_config(target: Path, expected: dict | None, *, resolver, run) -> None:
    """Ask the installed opencode binary to load this config directory.

    ``OPENCODE_CONFIG_DIR`` points at the directory just written.
    ``OPENCODE_DISABLE_PROJECT_CONFIG`` keeps a project file from being appended
    during the check. A non-zero exit, a missing command, or output that is not
    a JSON config object rejects the write.
    """
    import os
    import subprocess

    resolved = resolver("opencode")
    if not resolved:
        raise ValueError(public_debug_failure(127, "", "opencode was not found"))
    env = os.environ.copy()
    env["OPENCODE_CONFIG_DIR"] = str(target)
    env["OPENCODE_DISABLE_PROJECT_CONFIG"] = "1"
    try:
        completed = run(
            [resolved, "debug", "config"],
            cwd=str(target),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ValueError(public_debug_failure(None, "", str(error))) from error
    if completed.returncode != 0:
        raise ValueError(public_debug_failure(completed.returncode, completed.stdout or "", completed.stderr or ""))
    text = (completed.stdout or "").strip()
    try:
        loaded = json.loads(text) if text else None
    except json.JSONDecodeError:
        loaded = None
    if not isinstance(loaded, dict):
        raise ValueError(public_debug_failure(completed.returncode, "", "output was not a JSON config object"))
    if expected:
        try:
            assert_loaded_rules(loaded, expected)
        except ValueError as error:
            raise ValueError(public_debug_failure(completed.returncode, "", str(error))) from error


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
