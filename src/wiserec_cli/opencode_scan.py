"""Find project and agent rules that can override the global OpenCode config.

OpenCode 1.19.3 ``packages/opencode/src/config/config.ts`` loads the global
file, then project ``opencode.json`` / ``opencode.jsonc``, then each config
directory's agent markdown (``{agent,agents}/**/*.md`` and
``{mode,modes}/*.md``). ``@opencode/cli`` 2.1.0
``packages/core/src/config/discovery.ts`` also walks ``.opencode``,
``.agents``, and ``.claude``. A warning is printed only when one of those
files contains a rule that can match a command our rules govern.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .opencode_managed import SIDECAR_NAME, shell_family
from .opencode_rulematch import (
    BROAD_RESOURCES,
    EFFECTS,
    OTHER_RULES,
    PROTECTED_COMMANDS,
    SHELL_ACTIONS,
    SHELL_RULES,
    wildcard_match,
)

_PROBES = tuple(PROTECTED_COMMANDS) + tuple(
    resource for resource, _effect in SHELL_RULES if "*" not in resource and "?" not in resource
) + ("echo hello",)


def global_agent_broad_allows(config: dict) -> list:
    """Broad shell allows nested under global ``agent.<name>.permission``."""
    found = []
    if not isinstance(config, dict):
        return found
    for key in ("agent", "agents"):
        agents = config.get(key)
        if not isinstance(agents, dict):
            continue
        for name, agent in agents.items():
            if not isinstance(agent, dict):
                continue
            for label, action, resource, effect in _permission_object_rules(agent.get("permission"), f"{key}.{name}"):
                if effect != "allow" or resource.lower() not in BROAD_RESOURCES:
                    continue
                if shell_family(action) != "shell" and action not in SHELL_ACTIONS:
                    continue
                found.append(f"{label}.permission.bash {resource}={effect}")
    return found


def could_override(action: str, resource: str) -> bool:
    if not isinstance(action, str) or not isinstance(resource, str):
        return False
    if action in {"read", "skill"} or shell_family(action) == "read":
        return any(
            wildcard_match(pattern, resource) or wildcard_match(resource, pattern)
            for _action, pattern, _effect in OTHER_RULES
            if _action == action or shell_family(action) == _action
        )
    if shell_family(action) != "shell" and action not in SHELL_ACTIONS:
        return False
    return any(wildcard_match(probe, resource) for probe in _PROBES)


def scan_overriding_configs(install_target: Path, start: Path | None = None) -> list:
    """Return descriptions of later-loaded rules that can override managed ones."""
    start = (start or Path.cwd()).resolve()
    home = Path.home().resolve()
    found = []
    seen = set()
    current = start
    for _ in range(16):
        _scan_directory(current, install_target, seen, found)
        if current == home or current == current.parent:
            break
        current = current.parent
    for name in (".opencode", ".agents", ".claude"):
        _scan_tree(home / name, install_target, seen, found, kind="project")
    _scan_install_agents(install_target, seen, found)
    return found


def _scan_directory(directory: Path, install_target: Path, seen: set, found: list) -> None:
    names = [
        directory / "opencode.json",
        directory / "opencode.jsonc",
        directory / ".opencode" / "opencode.json",
        directory / ".opencode" / "opencode.jsonc",
    ]
    for path in names:
        _consider_config_file(path, install_target, seen, found, kind="project")
    for name in (".opencode", ".agents", ".claude"):
        _scan_tree(directory / name, install_target, seen, found, kind="project")


def _scan_tree(root: Path, install_target: Path, seen: set, found: list, *, kind: str) -> None:
    if not root.is_dir() or root.is_symlink():
        return
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        if path.suffix.lower() not in {".md", ".json", ".jsonc"}:
            continue
        if path.suffix.lower() == ".md":
            _consider_agent_markdown(path, install_target, seen, found)
        else:
            _consider_config_file(path, install_target, seen, found, kind=kind)


def _scan_install_agents(install_target: Path, seen: set, found: list) -> None:
    """Agent files in the global config directory are loaded after opencode.json."""
    if not install_target.is_dir() or install_target.is_symlink():
        return
    for name in ("agent", "agents", "mode", "modes"):
        root = install_target / name
        if not root.is_dir() or root.is_symlink():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.is_symlink() or path.suffix.lower() != ".md":
                continue
            _consider_agent_markdown(path, install_target, seen, found, allow_inside=True)


def _consider_config_file(path: Path, install_target: Path, seen: set, found: list, kind: str) -> None:
    if path.name == SIDECAR_NAME:
        return
    resolved = _safe_resolve(path)
    if resolved is None or resolved in seen or _inside(resolved, install_target):
        return
    seen.add(resolved)
    document = _load_loose(resolved)
    if not isinstance(document, dict):
        return
    for label, action, resource, effect in _rules_in_document(document):
        if could_override(action, resource):
            found.append(f"{kind} {resolved}: {label} {resource}={effect}")


def _consider_agent_markdown(path: Path, install_target: Path, seen: set, found: list, allow_inside: bool = False) -> None:
    resolved = _safe_resolve(path)
    if resolved is None or resolved in seen:
        return
    if not allow_inside and _inside(resolved, install_target):
        return
    seen.add(resolved)
    try:
        text = resolved.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return
    front = _frontmatter(text)
    if not front or not _frontmatter_may_have_rules(front):
        return
    for action, resource, effect in _frontmatter_rules(front):
        if could_override(action, resource):
            found.append(f"agent {resolved}: {action} {resource}={effect}")


def _rules_in_document(document: dict):
    yield from _permission_object_rules(document.get("permission"), "permission")
    yield from _array_rules(document.get("permissions"), "permissions")
    for key in ("agent", "agents", "mode"):
        agents = document.get(key)
        if not isinstance(agents, dict):
            continue
        for name, agent in agents.items():
            if not isinstance(agent, dict):
                continue
            yield from _permission_object_rules(agent.get("permission"), f"{key}.{name}")
            yield from _array_rules(agent.get("permissions"), f"{key}.{name}")


def _permission_object_rules(permission, label: str):
    if isinstance(permission, str) and permission in EFFECTS:
        yield (label, "shell", "*", permission)
        return
    if not isinstance(permission, dict):
        return
    for action in ("bash", "shell", "*", "read", "skill"):
        value = permission.get(action)
        exposed = "shell" if action in SHELL_ACTIONS else action
        if isinstance(value, str) and value in EFFECTS:
            yield (label, exposed, "*", value)
        elif isinstance(value, dict):
            for resource, effect in value.items():
                if isinstance(resource, str) and effect in EFFECTS:
                    yield (label, exposed, resource, effect)


def _array_rules(rules, label: str):
    if not isinstance(rules, list):
        return
    for rule in rules:
        if (
            isinstance(rule, dict)
            and isinstance(rule.get("action"), str)
            and isinstance(rule.get("resource"), str)
            and rule.get("effect") in EFFECTS
        ):
            yield (label, rule["action"], rule["resource"], rule["effect"])


def _frontmatter_may_have_rules(front: str) -> bool:
    if "permission" in front.lower():
        return True
    return bool(re.search(
        r"(?im)^\s*[\"']?(?:bash|shell|read|skill)[\"']?\s*:\s*[\"']?(?:allow|ask|deny)[\"']?\s*$",
        front,
    ))


def _frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    if end == -1:
        return ""
    return text[3:end]


def _frontmatter_rules(front: str):
    action = "shell"
    for line in front.splitlines():
        stripped = line.strip().lower().rstrip(":")
        if stripped in {"bash", "shell", "read", "skill", "permission", "permissions"}:
            action = "shell" if stripped in {"bash", "shell", "permission", "permissions"} else stripped
            continue
        match = re.match(
            r"""^["']?(.+?)["']?\s*:\s*["']?(allow|ask|deny)["']?\s*$""",
            line.strip(),
            re.IGNORECASE,
        )
        if match:
            key = match.group(1)
            effect = match.group(2).lower()
            if key.lower() in {"bash", "shell", "*", "permission", "permissions"}:
                yield ("shell", "*", effect)
            elif key.lower() in {"read", "skill"}:
                yield (key.lower(), "*", effect)
            else:
                yield (action, key, effect)


def _load_loose(path: Path):
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        stripped = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
        stripped = re.sub(r"(?<!:)//.*?$", "", stripped, flags=re.M)
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return None


def _safe_resolve(path: Path):
    try:
        if not path.is_file() or path.is_symlink():
            return None
        return path.resolve()
    except OSError:
        return None


def _inside(path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory.resolve())
        return True
    except ValueError:
        return False
