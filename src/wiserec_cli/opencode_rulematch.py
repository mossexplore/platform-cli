"""OpenCode permission wildcard match, ported for Windows shell rules.

Matching follows OpenCode: ``*`` is ``.*``, a pattern ending in `` *`` also
matches without that suffix, backslashes are slashes, and Windows matching is
case-insensitive. The last matching rule wins. An empty command scan is not a
permission decision.
"""

from __future__ import annotations

import re


MARKER = "wiserec"
MARKER_VALUE = "managed"
EFFECTS = {"allow", "ask", "deny"}
SHELL_ACTIONS = {"shell", "bash", "*"}
_SPECIAL = re.compile(r"[.+^${}()|[\]\\]")
# Commands our ask/deny rules must still govern when a user allow is present.
PROTECTED_COMMANDS = (
    "ml jupyter exec --cwd x -- sh -c 'echo pwned' --help",
    "ml jupyter exec --cwd x -- powershell -c 'gc c' --help",
    "ml login --show-secrets",
    "ml train list --yes",
    "ml env use product",
    "ml model deploy m1 --template t1 --dry-run",
    "ml train start task1",
    "ml tree > C:/out.txt",
    "ml tree >> ~/.bashrc",
    "ml jupyter terminal open",
    "cat ./credentials.json",
    "type credentials.json",
    "gc credentials.json",
    "Get-Content credentials.json",
    r"Get-Content $HOME\.x\credentials.json",
    "Copy-Item .\\credentials.json .\\x",
    "sls token credentials.json",
    "findstr /s secret credentials.json",
)

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

# Specific --help forms sit after the ask overrides.
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

OTHER_RULES = (
    ("skill", "wiserec-platform", "allow"),
    ("read", "*credentials.json*", "deny"),
)
BROAD_RESOURCES = {"*", "* *", "**"}


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


def is_rule(item) -> bool:
    return (
        isinstance(item, dict)
        and isinstance(item.get("action"), str)
        and isinstance(item.get("resource"), str)
        and item.get("effect") in EFFECTS
    )


def permission_effect(action: str, resource: str, rules, *, windows: bool = True) -> str:
    """Last matching rule wins. No match asks, matching OpenCode's default."""
    effect = "ask"
    for rule in rules:
        if not is_rule(rule):
            continue
        if (wildcard_match(action, rule["action"], windows=windows)
                and wildcard_match(resource, rule["resource"], windows=windows)):
            effect = rule["effect"]
    return effect


def combined_shell_effect(segments, rules, *, windows: bool = True) -> str:
    """Combine one shell invocation's scanned command strings."""
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


def layered_rules(*layers) -> list:
    """Concatenate config layers. Later layers are checked last and win."""
    combined = []
    for layer in layers:
        if layer:
            combined.extend(layer)
    return combined
