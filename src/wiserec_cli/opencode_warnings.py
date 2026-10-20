"""Warnings for user allows that are not an exact-key collision."""

from __future__ import annotations

from . import messages as msg
from .opencode_rulematch import (
    BROAD_RESOURCES,
    MARKER,
    MARKER_VALUE,
    PROTECTED_COMMANDS,
    SHELL_ACTIONS,
    is_rule,
    wildcard_match,
)


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
        if folded in BROAD_RESOURCES:
            continue
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
    """Catch-all shell allows such as ``*`` that a later ask can override."""
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


def warn_user_allows(_original: dict, merged: dict, *, rule_format: str) -> None:
    rules = []
    if isinstance(merged.get("permissions"), list):
        rules.extend(rule for rule in merged["permissions"] if not _is_ours(rule))
    rules.extend(_legacy_allow_rules(merged.get("permission")))
    broad = broad_allow_rules(rules)
    if broad:
        listed = ", ".join(
            f"{rule['action']} {rule['resource']}={rule['effect']}" for rule in broad
        )
        if rule_format == "permissions":
            msg.warning(
                "OpenCode 2 keeps this broad shell allow in the file. "
                "The managed shell * ask is written after permission.bash and after earlier array rules, "
                "so that ask overrides the allow for commands that do not match a later rule: "
                + listed
            )
        else:
            msg.warning(
                "OpenCode kept this broad shell allow. Later managed ask and deny rules still override "
                "it when they match: "
                + listed
            )
    conflicts = conflicting_allow_rules(rules)
    if conflicts:
        listed = ", ".join(
            f"{rule['action']} {rule['resource']}={rule['effect']}" for rule in conflicts
        )
        msg.warning(
            "OpenCode wildcard allows were kept. A later managed ask or deny overrides them "
            "when that rule matches last: "
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


__all__ = ["broad_allow_rules", "conflicting_allow_rules", "warn_user_allows"]
