"""Merge Windows OpenCode permission rules into the user config.

``opencode --version`` selects the shape. Major 2 and newer write the
``permissions`` array. OpenCode 1.1.1 through 1.x write ``permission.bash``.
Every 1.x release rejects the array: v1.18.35 and v1.19.3 raise
"V2 permissions are not supported by OpenCode V1" from
``packages/opencode/src/config/v2-compat.ts`` lines 94-113, and older 1.x
releases report an unrecognized key. ``@opencode/cli`` 2.1.0 is the release
known to load the array. User ``permission.bash`` and ``permission.shell``
entries stay in place in both modes.

Within the v2 array the order is fixed: user non-shell rules, the shell
``*`` ask fallback, user shell rules, then managed rules. The fallback asks
for every shell command, not only ``ml``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import messages as msg
from .opencode_bash_rules import drop_recorded_bash_patterns, merge_bash_rules, warn_v1_bash
from .opencode_configfile import (
    SCHEMA,
    backup_path as _backup_path,
    config_path as _config_path,
    decode as _decode,
    dump as _dump,
    normalize_newlines as _normalize_newlines,
    read_config_file as _read_config_file,
    read_existing as _read_existing,
    restore as _restore,
)
from .opencode_managed import (
    MergeReport,
    OpenCodeConflictError,
    assert_loaded_rules,
    clear_record,
    content_hash,
    describe_conflict,
    owned_bash_patterns,
    owned_permission_keys,
    public_debug_failure,
    raise_if_conflicts,
    record_for,
    restrict_backup,
    save_record,
    shell_family,
    take_legacy_marker,
    weaker,
)
from .opencode_scan import scan_overriding_configs
from .opencode_warnings import broad_allow_rules, conflicting_allow_rules, warn_user_allows as _warn_user_allows
from .opencode_rulematch import (
    MARKER,
    MARKER_VALUE,
    OTHER_RULES,
    SHELL_ACTIONS,
    SHELL_RULES,
    combined_shell_effect,
    is_rule,
    layered_rules,
    permission_effect,
    wildcard_match,
)
from .opencode_version import (
    MINIMUM_BASH,
    MINIMUM_PERMISSIONS,
    OpenCodeVersionError,
    detect_permission_format,
    permission_format_for_version,
)

def fresh_opencode_config() -> dict:
    """Config written for OpenCode 2 when the user has no opencode.json yet."""
    return merge_opencode_config({"$schema": SCHEMA}, rule_format="permissions")


def fresh_bash_config() -> dict:
    """Config written for OpenCode 1.1.1+ when the user has no opencode.json yet."""
    return merge_opencode_config({"$schema": SCHEMA}, rule_format="bash")


def merge_opencode_config(
    config: dict,
    *,
    rule_format: str = "permissions",
    managed: dict | None = None,
    override_conflicts: bool = False,
    report: MergeReport | None = None,
) -> dict:
    """Return a new document. Schema-only keys are written."""
    document, _report = plan_opencode_config(
        config,
        rule_format=rule_format,
        managed=managed,
        override_conflicts=override_conflicts,
        report=report,
    )
    return document


def plan_opencode_config(
    config: dict,
    *,
    rule_format: str = "permissions",
    managed: dict | None = None,
    override_conflicts: bool = False,
    report: MergeReport | None = None,
) -> tuple:
    """Merge in memory. Weaker exact collisions raise before any file is written."""
    if not isinstance(config, dict):
        raise ValueError("OpenCode config must be a JSON object")
    if rule_format not in {"permissions", "bash"}:
        raise ValueError(f"Unknown OpenCode rule format: {rule_format}")
    result = json.loads(json.dumps(config))
    legacy = take_legacy_marker(result)
    report = report or MergeReport()
    report.migrated.extend(legacy["migrated"])
    managed = managed or {}
    if rule_format == "permissions":
        existing = result.get("permissions", [])
        if existing is None:
            existing = []
        if not isinstance(existing, list):
            raise ValueError("OpenCode permissions must be an array")
        result["permissions"] = _merge_rules(
            existing,
            owned=owned_permission_keys(managed, legacy),
            override_conflicts=override_conflicts,
            report=report,
        )
        remembered = owned_bash_patterns(managed, legacy)
        for action, patterns in remembered.items():
            if patterns:
                report.written_bash[action] = list(patterns)
        return result, report
    merge_bash_rules(
        result,
        owned=owned_bash_patterns(managed, legacy),
        override_conflicts=override_conflicts,
        report=report,
    )
    return result, report


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


def preflight_opencode_permissions(
    target: Path,
    *,
    rule_format: str = "permissions",
    override_conflicts: bool = False,
) -> None:
    """Plan the merge and abort on a weaker exact key before any file is written."""
    if target.is_symlink():
        raise ValueError(f"OpenCode directory must not be a symlink: {target}")
    if not target.exists():
        plan_opencode_config({"$schema": SCHEMA}, rule_format=rule_format)
        return
    path = _config_path(target)
    if not path.exists() and not path.is_symlink():
        plan_opencode_config({"$schema": SCHEMA}, rule_format=rule_format)
        return
    _original, config = _read_existing(path)
    try:
        plan_opencode_config(
            config,
            rule_format=rule_format,
            managed=record_for(path),
            override_conflicts=False,
        )
    except OpenCodeConflictError:
        if not override_conflicts:
            raise


def install_opencode_permissions(
    target: Path,
    *,
    rule_format: str = "permissions",
    override_conflicts: bool = False,
) -> None:
    """Merge managed rules, backing up the original without overwriting ``.bak``."""
    if target.is_symlink():
        raise ValueError(f"OpenCode directory must not be a symlink: {target}")
    path = _config_path(target)
    original, config = _read_existing(path) if path.exists() or path.is_symlink() else (None, {"$schema": SCHEMA})
    if path.is_symlink():
        raise ValueError(f"OpenCode config must not be a symlink: {path}")
    managed = record_for(path)
    report = MergeReport()
    merged, report = plan_opencode_config(
        config,
        rule_format=rule_format,
        managed=managed,
        override_conflicts=override_conflicts,
        report=report,
    )
    _warn_user_allows(config, merged, rule_format=rule_format)
    owned = owned_bash_patterns(managed, {"bash": {"bash": [], "read": [], "skill": []}})
    if rule_format == "bash":
        warn_v1_bash(config, owned)
    _warn_project_and_agent(target)
    _announce(report)
    rendered = _dump(merged)
    if original is not None and _normalize_newlines(_decode(original)) == rendered:
        _store_manifest(path, rendered, rule_format, report)
        return
    target.mkdir(parents=True, exist_ok=True)
    _replace_with_rollback(path, rendered, original, _expected_rules(rule_format, report))
    _store_manifest(path, rendered, rule_format, report)


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
    managed = record_for(path)
    legacy = take_legacy_marker(config)
    owned = owned_bash_patterns(managed, legacy)
    drop_recorded_bash_patterns(config, owned)
    _drop_owned_array_rules(config, owned_permission_keys(managed, legacy))
    rendered = _dump(config)
    if original is not None and _normalize_newlines(_decode(original)) == rendered:
        clear_record(path)
        return
    _replace_with_rollback(path, rendered, original, None)
    clear_record(path)


def _merge_rules(items: list, *, owned: set, override_conflicts: bool, report: MergeReport) -> list:
    """User non-shell rules, shell ``*`` ask, user shell rules, then ours.

    OpenCode keeps the last match. This order is the one the array must keep.
    A weaker exact action/resource collision aborts unless override is set.
    """
    opaque = []
    user_other = []
    user_shell = []
    conflicts = []
    skipped = set()
    wanted = [("shell", "*", "ask"), *[( "shell", resource, effect) for resource, effect in SHELL_RULES]]
    wanted.extend(OTHER_RULES)
    by_key = {(shell_family(action), resource): (action, resource, effect) for action, resource, effect in wanted}
    for item in items:
        if not is_rule(item):
            opaque.append(item)
            continue
        if _is_ours(item):
            continue
        key = (shell_family(item["action"]), item["resource"])
        if key in owned:
            continue
        managed = by_key.get(key)
        copied = {field: item[field] for field in ("action", "resource", "effect")}
        for extra, value in item.items():
            if extra not in copied and extra != MARKER:
                copied[extra] = value
        if managed is None:
            _bucket(copied, user_shell, user_other)
            continue
        _action, _resource, effect = managed
        if not weaker(item["effect"], effect):
            skipped.add(key)
            _bucket(copied, user_shell, user_other)
            continue
        conflict = describe_conflict(
            f"permissions {item['action']}",
            item["resource"],
            item["effect"],
            effect,
        )
        conflicts.append(conflict)
        if override_conflicts:
            report.overrides.append(conflict)
            msg.warning(
                f"Replacing permissions {item['action']} {item['resource']!r} from {item['effect']!r} "
                f"to {effect!r} and moving it into the managed rules."
            )
            continue
        _bucket(copied, user_shell, user_other)
    raise_if_conflicts(conflicts, override_conflicts)
    managed_rules = [
        _rule(action, resource, effect)
        for action, resource, effect in wanted
        if (shell_family(action), resource) not in skipped
    ]
    report.written_permissions = list(managed_rules)
    report.added.extend(
        f"{rule['action']} {rule['resource']}={rule['effect']}" for rule in managed_rules
    )
    star = [rule for rule in managed_rules if rule["resource"] == "*" and rule["action"] == "shell"]
    rest = [rule for rule in managed_rules if rule not in star]
    return [*opaque, *user_other, *star, *user_shell, *rest]


def _is_ours(rule) -> bool:
    return isinstance(rule, dict) and rule.get(MARKER) == MARKER_VALUE


def _rule(action: str, resource: str, effect: str) -> dict:
    return {"action": action, "resource": resource, "effect": effect}


def _bucket(rule: dict, user_shell: list, user_other: list) -> None:
    if rule["action"] in SHELL_ACTIONS:
        user_shell.append(rule)
    else:
        user_other.append(rule)


def _drop_owned_array_rules(config: dict, owned: set) -> None:
    rules = config.get("permissions")
    if not isinstance(rules, list):
        return
    kept = []
    for rule in rules:
        if is_rule(rule) and (shell_family(rule["action"]), rule["resource"]) in owned:
            continue
        if _is_ours(rule):
            continue
        kept.append(rule)
    if kept:
        config["permissions"] = kept
    else:
        config.pop("permissions", None)


def _announce(report: MergeReport) -> None:
    if report.added:
        msg.detail("Added OpenCode rules: " + ", ".join(report.added))
    if report.migrated:
        msg.detail("Migrated OpenCode rules: " + ", ".join(report.migrated))


def _warn_project_and_agent(target: Path) -> None:
    found = scan_overriding_configs(target)
    if not found:
        return
    msg.warning(
        "Project or agent config is loaded after the global rules and can override them: "
        + "; ".join(found)
    )


def _expected_rules(rule_format: str, report: MergeReport) -> dict:
    if rule_format != "bash":
        return {"format": "permissions", "permissions": report.written_permissions}
    from .opencode_bash_rules import _effects

    known = _effects()
    known["bash"] = {"*": "ask", **known["bash"]}
    expected = {"format": "bash"}
    for action in ("bash", "read", "skill"):
        order = list(report.written_bash.get(action) or [])
        expected[f"{action}_order"] = order
        expected[f"{action}_effects"] = {pattern: known[action][pattern] for pattern in order}
    return expected


def _store_manifest(path: Path, rendered: str, rule_format: str, report: MergeReport) -> None:
    save_record(path, {
        "format": rule_format,
        "config_sha256": content_hash(rendered),
        "bash": report.written_bash,
        "permissions": report.written_permissions,
    })


def _opencode_debug_config(target: Path, expected: dict | None = None) -> None:
    """Ask the installed opencode binary to load this config directory.

    ``OPENCODE_CONFIG_DIR`` points at the directory just written.
    ``OPENCODE_DISABLE_PROJECT_CONFIG`` keeps a project file from being appended
    during the check. v1.19.3 ``packages/opencode/src/cli/cmd/debug/config.ts``
    and v2.1.0 ``packages/cli/src/commands/handlers/debug/config.ts`` both expose
    ``opencode debug config``. A non-zero exit, a missing command, or output
    that is not a JSON config object rejects the write.
    """
    resolved = shutil.which("opencode")
    if not resolved:
        raise ValueError(public_debug_failure(127, "", "opencode was not found"))
    env = os.environ.copy()
    env["OPENCODE_CONFIG_DIR"] = str(target)
    env["OPENCODE_DISABLE_PROJECT_CONFIG"] = "1"
    try:
        completed = subprocess.run(
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


def _replace_with_rollback(path: Path, rendered: str, original: bytes | None, expected: dict | None) -> None:
    backup = _backup_path(path) if original is not None else None
    temporary = path.with_name(path.name + ".wiserec-tmp")
    if original is not None and backup is not None:
        backup.write_bytes(original)
        restrict_backup(backup)
    try:
        temporary.write_bytes(rendered.encode("utf-8"))
        loaded = json.loads(temporary.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise ValueError("OpenCode config must be a JSON object")
        os.replace(temporary, path)
        confirmed = json.loads(path.read_text(encoding="utf-8"))
        if confirmed != loaded:
            raise ValueError("OpenCode config verification failed")
        _opencode_debug_config(path.parent, expected)
    except Exception as error:
        temporary.unlink(missing_ok=True)
        try:
            _restore(path, original)
        except Exception as restore_error:
            raise RuntimeError(
                f"OpenCode config restore failed; backup is {backup}"
            ) from restore_error
        raise


__all__ = [
    "MARKER",
    "MARKER_VALUE",
    "MINIMUM_BASH",
    "MINIMUM_PERMISSIONS",
    "SHELL_RULES",
    "OpenCodeConflictError",
    "OpenCodeVersionError",
    "broad_allow_rules",
    "combined_shell_effect",
    "conflicting_allow_rules",
    "detect_permission_format",
    "fresh_bash_config",
    "fresh_opencode_config",
    "install_opencode_permissions",
    "preflight_opencode_permissions",
    "layered_rules",
    "merge_opencode_config",
    "permission_effect",
    "permission_format_for_version",
    "uninstall_opencode_permissions",
    "validate_opencode_config",
    "wildcard_match",
]
