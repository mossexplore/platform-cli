"""Append managed patterns to OpenCode 1 permission.bash without moving user keys.

v1.19.3 ``packages/opencode/src/permission/index.ts`` lines 28-38 keep the last
match by key insertion order. The built-in bash default is ``"*": "allow"``,
so ``"*": "ask"`` is inserted first when the user has no ``"*"`` key. An
existing ``"*"`` stays where it is. Any denied subcommand denies the whole
command. Managed ask/deny patterns are appended after every existing key.
"""

from __future__ import annotations

from . import messages as msg
from .opencode_rulematch import EFFECTS, MARKER, OTHER_RULES, SHELL_RULES

_BASH_ACTIONS = ("bash", "read", "skill")


def merge_bash_rules(config: dict) -> None:
    """Append managed patterns. Existing user keys stay in their current order."""
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
    record = bash_record(config)
    written = {}
    for action, patterns in _patterns().items():
        written[action] = _append_patterns(permission, action, patterns, _pattern_list(record, action))
    config[MARKER] = {"format": "bash", **written}


def drop_recorded_bash_patterns(config: dict) -> None:
    """Remove only patterns previously recorded as ours. Used by uninstall."""
    record = bash_record(config)
    if not record:
        return
    permission = config.get("permission")
    if isinstance(permission, dict):
        for action in _BASH_ACTIONS:
            bucket = permission.get(action)
            if not isinstance(bucket, dict):
                continue
            for pattern in _pattern_list(record, action):
                bucket.pop(pattern, None)
            if not bucket:
                permission.pop(action, None)
        if not permission:
            config.pop("permission", None)
    config.pop(MARKER, None)


def warn_v1_bash(original: dict) -> None:
    """Warn about limits that stay in force after a v1 bash merge."""
    msg.warning(
        "Project-level OpenCode config is merged after these permission.bash rules and can override them."
    )
    effect = user_bash_star(original)
    if effect is None:
        return
    message = (
        'permission.bash already has a "*" key. Its position was kept and the key was not replaced. '
        "OpenCode 1.19.3 matches permission.bash by key order (permission/index.ts lines 28-38). "
        'The built-in default is "*": "allow".'
    )
    if effect == "allow":
        message += (
            ' This "*": "allow" stays in effect for commands that match it last. '
            "Unlisted commands chained with ml will run, for example `ml tree && echo x`, "
            "because a command is denied only when one of its subcommands is denied."
        )
    msg.warning(message)


def user_bash_star(config: dict):
    """Return the user's own bash ``*`` effect, ignoring a star this installer recorded."""
    if not isinstance(config, dict):
        return None
    record = bash_record(config)
    recorded = set(_pattern_list(record, "bash"))
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


def _append_patterns(permission: dict, action: str, patterns: list, previous: list) -> list:
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
    for pattern in previous:
        current.pop(pattern, None)
    rebuilt = {}
    written = []
    if action == "bash" and "*" not in current:
        # A string shorthand such as "allow" is the user's own "*" effect.
        if shorthand is None:
            rebuilt["*"] = "ask"
            written.append("*")
        else:
            rebuilt["*"] = shorthand
    for pattern, effect in current.items():
        rebuilt[pattern] = effect
    wanted = _effects()[action]
    for pattern in patterns:
        if pattern in rebuilt:
            continue
        rebuilt[pattern] = wanted[pattern]
        written.append(pattern)
    permission[action] = rebuilt
    return written
