"""Append managed patterns to OpenCode 1 permission.bash without moving user keys.

v1.19.3 ``packages/opencode/src/permission/index.ts`` lines 28-38 keep the last
match by key insertion order. The built-in bash default is ``"*": "allow"``,
so ``"*": "ask"`` is inserted first when the user has no ``"*"`` key. An
existing ``"*"`` stays where it is. Any denied subcommand denies the whole
command. Managed ask/deny patterns are appended after every existing key.
"""

from __future__ import annotations

from . import messages as msg
from .opencode_managed import describe_conflict, raise_if_conflicts, weaker
from .opencode_rulematch import EFFECTS, MARKER, OTHER_RULES, SHELL_RULES

_BASH_ACTIONS = ("bash", "read", "skill")


def merge_bash_rules(config: dict, *, owned: dict | None = None, override_conflicts: bool = False, report=None) -> None:
    """Append managed patterns. A weaker exact key aborts unless override is set."""
    permission = config.get("permission", None)
    if permission is None:
        permission = {}
        config["permission"] = permission
    elif isinstance(permission, str):
        if permission not in EFFECTS:
            raise ValueError("OpenCode permission has an unknown effect")
        permission = {"*": permission}
        config["permission"] = permission
    elif not isinstance(permission, dict):
        raise ValueError("OpenCode permission must be an object or action")
    owned = owned or {"bash": [], "read": [], "skill": []}
    conflicts = []
    written = {}
    for action, patterns in _patterns().items():
        written[action] = _append_patterns(
            permission,
            action,
            patterns,
            owned.get(action, []),
            override_conflicts,
            conflicts,
            report,
        )
    raise_if_conflicts(conflicts, override_conflicts)
    if report is not None:
        report.written_bash = written


def drop_recorded_bash_patterns(config: dict, owned: dict | None = None) -> None:
    """Remove only patterns previously recorded as ours. Used by uninstall."""
    record = bash_record(config)
    patterns = {"bash": [], "read": [], "skill": []}
    for action in _BASH_ACTIONS:
        for pattern in _pattern_list(record, action):
            if pattern not in patterns[action]:
                patterns[action].append(pattern)
        for pattern in (owned or {}).get(action, []):
            if pattern not in patterns[action]:
                patterns[action].append(pattern)
    if not any(patterns.values()) and not record:
        return
    permission = config.get("permission")
    if isinstance(permission, dict):
        for action in _BASH_ACTIONS:
            bucket = permission.get(action)
            if not isinstance(bucket, dict):
                continue
            for pattern in patterns[action]:
                bucket.pop(pattern, None)
            if not bucket:
                permission.pop(action, None)
        if not permission:
            config.pop("permission", None)
    config.pop(MARKER, None)


def warn_v1_bash(original: dict, owned: dict | None = None) -> None:
    """Warn when an equal or stronger user star key stays in its original position.

    A weaker ``"*"`` (``allow`` against our ``ask``) is a conflict and aborts
    before this warning. Putting our ``"*"`` ask at the end would erase the
    exact allows that follow it, so an overridden star is inserted first.
    """
    effect = user_bash_star(original, owned)
    if effect not in {"ask", "deny"}:
        return
    msg.warning(
        'permission.bash already has a "*" key. Its position was kept and the key was not replaced. '
        "OpenCode 1.19.3 matches permission.bash by key order (permission/index.ts lines 28-38). "
        'The built-in default is "*": "allow".'
    )


def user_bash_star(config: dict, owned: dict | None = None):
    """Return the user's own bash ``*`` effect, ignoring a star this installer recorded."""
    if not isinstance(config, dict):
        return None
    record = bash_record(config)
    recorded = set(_pattern_list(record, "bash"))
    recorded.update((owned or {}).get("bash", []))
    permission = config.get("permission")
    if not isinstance(permission, dict):
        return None
    bash = permission.get("bash")
    if isinstance(bash, str):
        return bash if bash in EFFECTS else None
    if isinstance(bash, dict) and "*" in bash and "*" not in recorded:
        effect = bash["*"]
        if isinstance(effect, str) and effect in EFFECTS:
            return effect
    return None


def bash_record(config: dict) -> dict:
    record = config.get(MARKER)
    if not isinstance(record, dict) or record.get("format") != "bash":
        return {}
    return record


def _pattern_list(record: dict, action: str) -> list:
    value = record.get(action, [])
    if not isinstance(value, list):
        return []
    return [pattern for pattern in value if isinstance(pattern, str)]


def _patterns() -> dict:
    patterns = {"bash": [resource for resource, _effect in SHELL_RULES]}
    for action, resource, _effect in OTHER_RULES:
        patterns.setdefault(action, []).append(resource)
    return patterns


def _effects() -> dict:
    effects = {"bash": {resource: effect for resource, effect in SHELL_RULES}}
    for action, resource, effect in OTHER_RULES:
        effects.setdefault(action, {})[resource] = effect
    return effects


def _append_patterns(permission, action, patterns, previous, override_conflicts, conflicts, report) -> list:
    current = permission.get(action)
    shorthand = None
    if isinstance(current, str):
        if current not in EFFECTS:
            raise ValueError(f"OpenCode permission.{action} has an unknown effect")
        shorthand = current
        current = {}
    elif current is None:
        current = {}
    elif not isinstance(current, dict):
        raise ValueError(f"OpenCode permission.{action} must be an object or action")
    else:
        current = dict(current)
    owned = set(previous)
    for pattern in previous:
        current.pop(pattern, None)
    if shorthand is not None and "*" not in current and "*" not in owned:
        current = {"*": shorthand, **current}
    wanted = _effects()[action]
    if action == "bash":
        patterns = ["*", *patterns]
        wanted = {"*": "ask", **wanted}
    pending = []
    for pattern in patterns:
        effect = wanted[pattern]
        if pattern in owned:
            pending.append((pattern, effect))
            continue
        if pattern not in current:
            pending.append((pattern, effect))
            continue
        user_effect = current[pattern]
        if not isinstance(user_effect, str) or user_effect not in EFFECTS:
            raise ValueError(f"OpenCode permission.{action} {pattern} has an unknown effect")
        if not weaker(user_effect, effect):
            continue
        item = describe_conflict(f"permission.{action}", pattern, user_effect, effect)
        conflicts.append(item)
        if override_conflicts:
            current.pop(pattern, None)
            pending.append((pattern, effect))
            if report is not None:
                report.overrides.append(item)
                msg.warning(
                    f"Replacing permission.{action} {pattern!r} from {user_effect!r} to {effect!r} "
                    "and moving it into the managed rules."
                )
    rebuilt = {}
    written = []
    star = [(pattern, effect) for pattern, effect in pending if pattern == "*"]
    rest = [(pattern, effect) for pattern, effect in pending if pattern != "*"]
    if star and "*" not in current:
        rebuilt["*"] = star[0][1]
        written.append("*")
    for pattern, effect in current.items():
        rebuilt[pattern] = effect
    for pattern, effect in rest:
        rebuilt[pattern] = effect
        written.append(pattern)
    permission[action] = rebuilt
    if report is not None:
        report.added.extend(f"{action} {pattern}={rebuilt[pattern]}" for pattern in written)
    return written
