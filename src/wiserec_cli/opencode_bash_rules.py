"""Write managed patterns into OpenCode 1 permission.bash.

v1.19.3 ``packages/opencode/src/permission/index.ts`` lines 28-38 keep the last
match by key insertion order. The built-in bash default is ``"*": "allow"``.
``"*": "ask"`` is always the first key. Any other managed key is removed from
the user section and appended after the remaining user keys, so the managed
effect is the one that matches last. A denied subcommand denies the whole
command. Keys this installer does not manage are left in place.
"""

from __future__ import annotations

from . import messages as msg
from .opencode_rulematch import EFFECTS, MARKER, OTHER_RULES, SHELL_RULES

_BASH_ACTIONS = ("bash", "read", "skill")


def merge_bash_rules(
    config: dict,
    *,
    owned: dict | None = None,
    prior: dict | None = None,
    announce: bool = True,
    report=None,
) -> None:
    """Overwrite exact keys we manage. Other user keys stay in their order."""
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
    prior = prior or {"bash": {}, "read": {}, "skill": {}}
    written = {}
    for action, patterns in _patterns().items():
        written[action] = _append_patterns(
            permission,
            action,
            patterns,
            owned.get(action, []),
            prior.get(action, {}),
            announce,
            report,
        )
    if report is not None:
        report.written_bash = written


def drop_legacy_bash_patterns(config: dict, legacy: dict, restored: set) -> None:
    """Drop in-file marker patterns that the sidecar did not just restore."""
    recorded = legacy.get("bash") if isinstance(legacy, dict) else None
    if not isinstance(recorded, dict):
        return
    permission = config.get("permission")
    if not isinstance(permission, dict):
        return
    for action in _BASH_ACTIONS:
        patterns = recorded.get(action, [])
        bucket = permission.get(action)
        if not isinstance(bucket, dict) or not isinstance(patterns, list):
            continue
        for pattern in patterns:
            if isinstance(pattern, str) and (action, pattern) not in restored:
                bucket.pop(pattern, None)
        if not bucket:
            permission.pop(action, None)
    if not permission:
        config.pop("permission", None)
    config.pop(MARKER, None)


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


def _append_patterns(permission, action, patterns, previous, prior, announce, report) -> list:
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
    if shorthand is not None and "*" not in current:
        current = {"*": shorthand, **current}
    owned = set(previous)
    indexes = {pattern: index for index, pattern in enumerate(current)}
    snapshot = dict(current)
    for pattern in owned:
        current.pop(pattern, None)
    wanted = _effects()[action]
    if action == "bash":
        patterns = ["*", *patterns]
        wanted = {"*": "ask", **wanted}
    entries = {}
    pending = []
    for pattern in patterns:
        effect = wanted[pattern]
        if pattern in prior:
            memory = prior[pattern]
            entries[pattern] = {
                "effect": effect,
                "original": memory.get("original"),
                "index": memory.get("index"),
            }
            pending.append((pattern, effect))
            continue
        if pattern in owned or pattern not in snapshot:
            entries[pattern] = {"effect": effect, "original": None, "index": None}
            pending.append((pattern, effect))
            continue
        user_effect = snapshot[pattern]
        if not isinstance(user_effect, str) or user_effect not in EFFECTS:
            raise ValueError(f"OpenCode permission.{action} {pattern} has an unknown effect")
        current.pop(pattern, None)
        entries[pattern] = {"effect": effect, "original": user_effect, "index": indexes.get(pattern)}
        pending.append((pattern, effect))
        if announce:
            _announce_takeover(action, pattern, user_effect, effect, report)
    rebuilt = {}
    written = []
    star = [(pattern, effect) for pattern, effect in pending if pattern == "*"]
    rest = [(pattern, effect) for pattern, effect in pending if pattern != "*"]
    if star:
        rebuilt["*"] = star[0][1]
        written.append("*")
    for pattern, effect in current.items():
        rebuilt[pattern] = effect
    for pattern, effect in rest:
        rebuilt[pattern] = effect
        written.append(pattern)
    permission[action] = rebuilt
    if report is not None:
        report.bash_entries[action] = entries
        report.added.extend(f"{action} {pattern}={rebuilt[pattern]}" for pattern in written)
    return written


def _announce_takeover(action: str, pattern: str, user_effect: str, effect: str, report) -> None:
    text = f'permission.{action} "{pattern}": {user_effect} -> {effect}'
    msg.warning(text)
    if report is not None:
        report.overrides.append(text)
