"""Merge Windows OpenCode permission rules into the user config.

Rules target OpenCode's shell tool on Windows (PowerShell). Matching follows
OpenCode's wildcard rules: ``*`` is ``.*``, a pattern ending in `` *`` also
matches without that suffix, backslashes are treated as slashes, and Windows
matching is case-insensitive. The last matching rule wins. An empty command
scan is not a permission decision: OpenCode skips the check.

Allow rules are exact command strings. New or parameterized ``ml`` commands
stay on the ``ml *`` ask rule. ``.NET`` static calls and ``${path}`` provider
variables are not shell commands, so these rules cannot see them.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


SCHEMA = "https://opencode.ai/config.json"
BACKUP_SUFFIX = ".wiserec-backup"
_EFFECTS = {"allow", "ask", "deny"}
_SHELL_ACTIONS = {"shell", "bash"}
_SPECIAL = re.compile(r"[.+^${}()|[\]\\]")

# Exact read-only commands that take no required positional arguments.
_EXACT_ALLOW = (
    "ml --version",
    "ml tree",
    "ml env list",
    "ml env show",
    "ml auth status",
    "ml auth ping status",
    "ml access status",
    "ml business list",
    "ml business show",
    "ml user info",
    "ml mep config get",
    "ml history list",
    "ml mtp swanboard project list",
    "ml offline experiment list",
    "ml train list",
    "ml algorithm list",
    "ml model list",
    "ml resource template list",
    "ml deployment template list",
    "ml service list",
    "ml dataset list",
    "ml featureset wide list",
    "ml featureset model list",
    "ml webstudio list",
    "ml webstudio show",
    "ml jupyter doctor",
    "ml jupyter files list",
    "ml jupyter terminal list",
)

# These override the exact allows because the last match wins.
_ASK_OVERRIDES = (
    "ml jupyter exec*",
    "ml * --yes*",
    "ml * -y*",
    "ml env use product*",
    "ml model deploy*",
    "ml train start*",
    "* > *",
    "* >> *",
)

# Specific --help forms sit after the ask overrides so a prefix wildcard
# cannot swallow the exact help command.
_HELP_ALLOW = (
    "ml tree --help",
    "ml env list --help",
    "ml service logs --help",
    "ml train list --help",
    "ml model list --help",
    "ml jupyter exec --help",
)

_DENY = (
    "ml jupyter terminal open*",
    "ml jupyter terminal attach*",
    "ml login --show-secrets*",
    "ml * --show-secrets*",
    "cat *credentials*",
    "type *credentials*",
    "gc *credentials*",
    "get-content *credentials*",
    "more *credentials*",
    "less *credentials*",
    "head *credentials*",
    "tail *credentials*",
    "select-string *credentials*",
    "sls *credentials*",
    "findstr *credentials*",
    "copy *credentials*",
    "cp *credentials*",
    "copy-item *credentials*",
    "import-csv *credentials*",
    "get-item *credentials*",
    "gi *credentials*",
    "notepad *credentials*",
    "base64 *credentials*",
    "certutil *credentials*",
    "xxd *credentials*",
    "od *credentials*",
    "strings *credentials*",
    "sed *credentials*",
    "awk *credentials*",
    "grep *credentials*",
    "rg *credentials*",
    "*credentials.json*",
)

_OTHER_RULES = (
    ("skill", "wiserec-platform", "allow"),
    ("read", "*credentials.json*", "deny"),
)

# Previous README example allowed these prefixes. They are removed on merge so
# an upgraded config cannot keep the trailing-wildcard bypasses.
RETIRED_SHELL_ALLOWS = frozenset({
    "ml --version*",
    "ml * --help*",
    "ml tree*",
    "ml env list*",
    "ml env show*",
    "ml auth status*",
    "ml auth ping status*",
    "ml access status*",
    "ml business list*",
    "ml business show*",
    "ml user info*",
    "ml mep config get*",
    "ml history list*",
    "ml mtp swanboard project list*",
    "ml mtp swanboard project namespace list*",
    "ml mtp swanboard project experiment list*",
    "ml mtp swanboard experiment feature list*",
    "ml mtp swanboard experiment environment get*",
    "ml mtp swanboard experiment metrics*",
    "ml mtp swanboard experiment config list*",
    "ml mtp swanboard experiment inspect*",
    "ml offline experiment list*",
    "ml offline experiment trial list*",
    "ml offline experiment clone * --dry-run*",
    "ml train list*",
    "ml train instance list*",
    "ml train history list*",
    "ml algorithm list*",
    "ml model list*",
    "ml model detail*",
    "ml model source*",
    "ml model deploy * --dry-run*",
    "ml resource template list*",
    "ml resource template detail*",
    "ml deployment template list*",
    "ml deployment template detail*",
    "ml service list*",
    "ml service logs*",
    "ml service host list*",
    "ml service deployment list*",
    "ml dataset list*",
    "ml dataset detail*",
    "ml dataset files list*",
    "ml featureset wide list*",
    "ml featureset wide config*",
    "ml featureset model list*",
    "ml featureset model config*",
    "ml webstudio list*",
    "ml webstudio show*",
    "ml jupyter doctor*",
    "ml jupyter files list*",
    "ml jupyter files stat*",
    "ml jupyter files read*",
    "ml jupyter terminal list*",
})


def _shell_rules():
    rules = [("ml *", "ask")]
    rules.extend((resource, "allow") for resource in _EXACT_ALLOW)
    rules.extend((resource, "ask") for resource in _ASK_OVERRIDES)
    rules.extend((resource, "allow") for resource in _HELP_ALLOW)
    rules.extend((resource, "deny") for resource in _DENY)
    resources = [resource for resource, _effect in rules]
    duplicates = sorted({resource for resource in resources if resources.count(resource) > 1})
    if duplicates:
        raise RuntimeError(f"duplicate OpenCode shell rules: {duplicates}")
    for resource, effect in rules:
        if effect == "allow" and ("*" in resource or "?" in resource):
            raise RuntimeError(f"allow rule must be exact: {resource}")
    return tuple(rules)


SHELL_RULES = _shell_rules()
MANAGED_RULES = {("shell", resource) for resource, _effect in SHELL_RULES}
MANAGED_RULES.update((action, resource) for action, resource, _effect in _OTHER_RULES)


def wildcard_match(value: str, pattern: str, *, windows: bool = True) -> bool:
    """Return whether ``value`` matches an OpenCode permission pattern."""
    normalized = value.replace("\\", "/")
    escaped = pattern.replace("\\", "/")
    escaped = _SPECIAL.sub(lambda match: "\\" + match.group(0), escaped)
    escaped = escaped.replace("*", ".*").replace("?", ".")
    if escaped.endswith(" .*"):
        escaped = escaped[:-3] + "( .*)?"
    flags = re.DOTALL | (re.IGNORECASE if windows else 0)
    return re.fullmatch(escaped, normalized, flags) is not None


def permission_effect(action: str, resource: str, rules, *, windows: bool = True) -> str:
    """Last matching rule wins. No match asks, matching OpenCode's default."""
    effect = "ask"
    for rule in rules:
        if not _is_rule(rule):
            continue
        if (wildcard_match(action, rule["action"], windows=windows)
                and wildcard_match(resource, rule["resource"], windows=windows)):
            effect = rule["effect"]
    return effect


def combined_shell_effect(segments, rules, *, windows: bool = True) -> str:
    """Combine one shell invocation's scanned command strings.

    ``unchecked`` means the scanner produced no command, which is the case
    OpenCode does not submit for a permission decision.
    """
    if not segments:
        return "unchecked"
    effects = [
        permission_effect("shell", segment, rules, windows=windows) for segment in segments
    ]
    if "deny" in effects:
        return "deny"
    if "ask" in effects:
        return "ask"
    return "allow"


def merge_opencode_config(config: dict) -> dict:
    """Return a new document with managed rules updated and user config kept."""
    if not isinstance(config, dict):
        raise ValueError("OpenCode config must be a JSON object")
    result = json.loads(json.dumps(config))
    lifted = _lift_legacy_shell_rules(result)
    existing = result.get("permissions", [])
    if existing is None:
        existing = []
    if not isinstance(existing, list):
        raise ValueError("OpenCode permissions must be an array")
    result["permissions"] = _merge_rules([*lifted, *existing])
    return result


def fresh_opencode_config() -> dict:
    """Config written when the user does not yet have opencode.json."""
    return merge_opencode_config({"$schema": SCHEMA})


def install_opencode_permissions(target: Path) -> None:
    """Merge managed rules into the global OpenCode config, with backup and rollback.

    OpenCode loads ``opencode.json`` and then ``opencode.jsonc`` from the same
    directory. Rules are written to ``opencode.jsonc`` when that is the only
    file, and to ``opencode.json`` otherwise. Both files present is an error:
    a later jsonc document would override rules written only to json.
    """
    if target.is_symlink():
        raise ValueError(f"OpenCode directory must not be a symlink: {target}")
    target.mkdir(parents=True, exist_ok=True)
    path = _config_path(target)
    if path.is_symlink():
        raise ValueError(f"OpenCode config must not be a symlink: {path}")
    if path.exists() and not path.is_file():
        raise ValueError(f"OpenCode config must be a file: {path}")

    original = path.read_bytes() if path.is_file() else None
    if original is None:
        config = {"$schema": SCHEMA}
    else:
        config = _load_config(original)
    rendered = _dump(merge_opencode_config(config))
    if original is not None and _normalize_newlines(_decode(original)) == rendered:
        return
    _replace_with_rollback(path, rendered, original)


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


def _load_config(original: bytes) -> dict:
    try:
        text = _decode(original)
    except UnicodeError as error:
        raise ValueError("OpenCode config must be UTF-8") from error
    if not text.strip():
        return {}
    try:
        config = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"OpenCode config is not valid JSON: {error}") from error
    if not isinstance(config, dict):
        raise ValueError("OpenCode config must be a JSON object")
    return config


def _decode(original: bytes) -> str:
    return original.decode("utf-8-sig")


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _dump(config: dict) -> str:
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"


def _replace_with_rollback(path: Path, rendered: str, original: bytes | None) -> None:
    backup = path.with_name(path.name + BACKUP_SUFFIX)
    temporary = path.with_name(path.name + ".wiserec-tmp")
    if original is not None:
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


def _lift_legacy_shell_rules(config: dict) -> list:
    """Move v1 ``permission.bash`` / ``permission.shell`` rules into v2 order.

    OpenCode evaluates legacy permission rules before the ``permissions`` array.
    A later shell ``*`` ask would override them, so user shell rules are lifted
    and reinserted after the fallback.
    """
    legacy = config.get("permission", None)
    if legacy is None:
        return []
    if isinstance(legacy, str):
        return []
    if not isinstance(legacy, dict):
        raise ValueError("OpenCode permission must be an object or action")
    lifted = []
    for key in ("bash", "shell"):
        if key not in legacy:
            continue
        lifted.extend(_legacy_shell_rules(legacy.pop(key), key))
    if legacy:
        config["permission"] = legacy
    else:
        config.pop("permission", None)
    return lifted


def _legacy_shell_rules(value, key: str) -> list:
    if isinstance(value, str):
        if value not in _EFFECTS:
            raise ValueError(f"OpenCode permission.{key} has an unknown effect")
        return [_rule("shell", "*", value)]
    if not isinstance(value, dict):
        raise ValueError(f"OpenCode permission.{key} must be an object or action")
    rules = []
    for resource, effect in value.items():
        if not isinstance(resource, str) or effect not in _EFFECTS:
            raise ValueError(f"OpenCode permission.{key} has an invalid rule")
        rules.append(_rule("shell", resource, effect))
    return rules


def _merge_rules(items: list) -> list:
    opaque = []
    user_other = []
    user_shell = []
    for item in items:
        if not _is_rule(item):
            opaque.append(item)
            continue
        if _is_managed(item):
            continue
        if item["action"] in _SHELL_ACTIONS:
            user_shell.append(dict(item))
        else:
            user_other.append(dict(item))
    managed_shell = [_rule("shell", resource, effect) for resource, effect in SHELL_RULES]
    managed_other = [_rule(action, resource, effect) for action, resource, effect in _OTHER_RULES]
    return [
        *opaque,
        *user_other,
        _rule("shell", "*", "ask"),
        *user_shell,
        *managed_shell,
        *managed_other,
    ]


def _is_managed(rule: dict) -> bool:
    action = "shell" if rule["action"] == "bash" else rule["action"]
    resource = rule["resource"]
    if action == "shell" and resource == "*" and rule["effect"] == "ask":
        return True
    if action == "shell" and rule["effect"] == "allow" and resource in RETIRED_SHELL_ALLOWS:
        return True
    return (action, resource) in MANAGED_RULES


def _is_rule(item) -> bool:
    return (
        isinstance(item, dict)
        and isinstance(item.get("action"), str)
        and isinstance(item.get("resource"), str)
        and item.get("effect") in _EFFECTS
    )


def _rule(action: str, resource: str, effect: str) -> dict:
    return {"action": action, "resource": resource, "effect": effect}
