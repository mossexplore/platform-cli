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
from .opencode_bash_rules import drop_legacy_bash_patterns, merge_bash_rules, remove_known_rules, warn_manifest_for_install
from .opencode_configfile import (
    SCHEMA,
    backup_path as _backup_path,
    write_private as _write_private,
    config_path as _config_path,
    decode as _decode,
    dump as _dump,
    normalize_newlines as _normalize_newlines,
    read_config_file as _read_config_file,
    read_existing as _read_existing,
    restore as _restore,
)
from .opencode_debug import run_debug_config
from .opencode_managed import (
    MergeReport,
    manifest_problem,
    clear_record,
    content_hash,
    owned_bash_patterns,
    owned_permission_keys,
    prior_bash_entries,
    prior_permission_entries,
    record_for,
    remembered_permission_entries,
    restore_originals,
    restored_bash_keys,
    restrict_backup,
    save_record,
    shell_family,
    take_legacy_marker,
)
from .opencode_scan import global_agent_broad_allows, scan_overriding_configs
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
    announce: bool = True,
    report: MergeReport | None = None,
) -> dict:
    """Return a new document. Schema-only keys are written."""
    document, _report = plan_opencode_config(
        config,
        rule_format=rule_format,
        managed=managed,
        announce=announce,
        report=report,
    )
    return document


def plan_opencode_config(
    config: dict,
    *,
    rule_format: str = "permissions",
    managed: dict | None = None,
    announce: bool = True,
    report: MergeReport | None = None,
) -> tuple:
    """Merge in memory. Exact keys we manage take our value."""
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
            prior=prior_permission_entries(managed),
            announce=announce,
            report=report,
        )
        report.bash_entries = prior_bash_entries(managed)
        for action, patterns in legacy.get("bash", {}).items():
            bucket = report.bash_entries.setdefault(action, {})
            if not isinstance(patterns, list):
                continue
            for pattern in patterns:
                if isinstance(pattern, str):
                    bucket.setdefault(pattern, {"original": None, "index": None})
        return result, report
    merge_bash_rules(
        result,
        owned=owned_bash_patterns(managed, legacy),
        prior=prior_bash_entries(managed),
        announce=announce,
        report=report,
    )
    report.permission_entries = remembered_permission_entries(managed)
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
) -> None:
    """Plan the merge before any file is written. Collisions do not abort."""
    if target.is_symlink():
        raise ValueError(f"OpenCode directory must not be a symlink: {target}")
    if not target.exists():
        plan_opencode_config({"$schema": SCHEMA}, rule_format=rule_format, announce=False)
        return
    path = _config_path(target)
    if not path.exists() and not path.is_symlink():
        plan_opencode_config({"$schema": SCHEMA}, rule_format=rule_format, announce=False)
        return
    _original, config = _read_existing(path)
    plan_opencode_config(
        config,
        rule_format=rule_format,
        managed=record_for(path),
        announce=False,
    )


_rollback_snapshot = None


def rollback_opencode_permissions(target: Path) -> None:
    """Undo this run's permission write and remove the sidecar manifest."""
    global _rollback_snapshot
    if _rollback_snapshot is None:
        raise RuntimeError("OpenCode permission changes cannot be rolled back because this run has no backup")
    path, original = _rollback_snapshot
    if path.parent.resolve() != target.resolve():
        raise RuntimeError(f"OpenCode permission rollback does not match {target}")
    _restore(path, original)
    clear_record(path)
    _rollback_snapshot = None


def _remember_rollback(path: Path, original: bytes | None) -> None:
    global _rollback_snapshot
    _rollback_snapshot = (path, original)


def install_opencode_permissions(
    target: Path,
    *,
    rule_format: str = "permissions",
) -> None:
    """Merge managed rules, backing up the original without overwriting ``.bak``."""
    if target.is_symlink():
        raise ValueError(f"OpenCode directory must not be a symlink: {target}")
    path = _config_path(target)
    original, config = _read_existing(path) if path.exists() or path.is_symlink() else (None, {"$schema": SCHEMA})
    if path.is_symlink():
        raise ValueError(f"OpenCode config must not be a symlink: {path}")
    managed = record_for(path)
    warn_manifest_for_install(path, config)
    _warn_global_agents(config)
    report = MergeReport()
    merged, report = plan_opencode_config(
        config,
        rule_format=rule_format,
        managed=managed,
        report=report,
    )
    _warn_user_allows(config, merged, rule_format=rule_format)
    _warn_project_and_agent(target)
    _announce(report)
    rendered = _dump(merged)
    if original is not None and _normalize_newlines(_decode(original)) == rendered:
        _store_manifest(path, rendered, rule_format, report)
        _remember_rollback(path, original)
        return
    target.mkdir(parents=True, exist_ok=True)
    _replace_with_rollback(path, rendered, original, _expected_rules(rule_format, report))
    _store_manifest(path, rendered, rule_format, report)
    _remember_rollback(path, original)


def uninstall_opencode_permissions(target: Path) -> None:
    """Remove keys we added and restore values we overwrote."""
    if not target.exists() and not target.is_symlink():
        return
    if target.is_symlink():
        raise ValueError(f"OpenCode directory must not be a symlink: {target}")
    path = _config_path(target)
    if not path.exists() and not path.is_symlink():
        return
    original, config = _read_existing(path)
    problem = manifest_problem(path)
    legacy = take_legacy_marker(config)
    if problem:
        remove_known_rules(config, reason=problem)
    else:
        managed = record_for(path)
        restore_originals(config, managed)
        drop_legacy_bash_patterns(config, legacy, restored_bash_keys(managed))
    rendered = _dump(config)
    if original is not None and _normalize_newlines(_decode(original)) == rendered:
        clear_record(path)
        return
    _replace_with_rollback(path, rendered, original, None)
    clear_record(path)


def _merge_rules(items: list, *, owned: set, prior: dict, announce: bool, report: MergeReport) -> list:
    """User non-shell rules, shell ``*`` ask, user shell rules, then ours.

    OpenCode keeps the last match. This order is the one the array must keep.
    An exact action/resource we manage is removed from the user section and
    rewritten with our effect in that managed suffix.
    """
    opaque = []
    user_other = []
    user_shell = []
    collisions = {}
    wanted = [("shell", "*", "ask"), *[("shell", resource, effect) for resource, effect in SHELL_RULES]]
    wanted.extend(OTHER_RULES)
    by_key = {(shell_family(action), resource): (action, resource, effect) for action, resource, effect in wanted}
    for index, item in enumerate(items):
        if not is_rule(item):
            opaque.append(item)
            continue
        if _is_ours(item):
            continue
        key = (shell_family(item["action"]), item["resource"])
        if key in owned or key in prior:
            continue
        copied = {field: item[field] for field in ("action", "resource", "effect")}
        for extra, value in item.items():
            if extra not in copied and extra != MARKER:
                copied[extra] = value
        managed = by_key.get(key)
        if managed is None:
            _bucket(copied, user_shell, user_other)
            continue
        if key in collisions:
            continue
        _action, _resource, effect = managed
        collisions[key] = {"original": copied, "index": index}
        if announce:
            text = f'permissions {item["action"]} "{item["resource"]}": {item["effect"]} -> {effect}'
            msg.warning(text)
            report.overrides.append(text)
    entries = []
    managed_rules = []
    for action, resource, effect in wanted:
        key = (shell_family(action), resource)
        if key in prior:
            original = prior[key]["original"]
            index = prior[key]["index"]
        elif key in collisions:
            original = collisions[key]["original"]
            index = collisions[key]["index"]
        else:
            original = None
            index = None
        entries.append({
            "action": action,
            "resource": resource,
            "effect": effect,
            "original": original,
            "index": index,
        })
        managed_rules.append(_rule(action, resource, effect))
    report.permission_entries = entries
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


def _announce(report: MergeReport) -> None:
    if report.added:
        msg.detail("Added OpenCode rules: " + ", ".join(report.added))
    if report.migrated:
        msg.detail("Migrated OpenCode rules: " + ", ".join(report.migrated))


def _warn_global_agents(config: dict) -> None:
    notes = global_agent_broad_allows(config)
    if not notes:
        return
    msg.warning(
        "Global agent permission.bash broad allow can override the managed rules: " + "; ".join(notes)
    )


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
    from wiserec_cli import __version__

    save_record(path, {
        "installer_version": __version__,
        "format": rule_format,
        "config_sha256": content_hash(rendered),
        "bash": report.bash_entries,
        "permissions": report.permission_entries,
    })


def _opencode_debug_config(target: Path, expected: dict | None = None) -> None:
    """Load the written directory with ``opencode debug config`` and verify rules."""
    run_debug_config(target, expected, resolver=shutil.which, run=subprocess.run)


def _replace_with_rollback(path: Path, rendered: str, original: bytes | None, expected: dict | None) -> None:
    backup = _backup_path(path) if original is not None else None
    temporary = path.with_name(path.name + ".wiserec-tmp")
    if original is not None and backup is not None:
        _write_private(backup, original, before_write=restrict_backup)
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
