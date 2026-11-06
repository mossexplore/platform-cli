"""环境禁止命令：手动输入完整路径，不绑定 CLI 命令目录。"""
import re
from fastapi import HTTPException
from .models import EnvironmentCommandDeny

CONTROL_GROUPS = {"login", "logout", "auth", "env", "tree", "history", "context", "access", "business"}
COMMAND_PATTERN = re.compile(r'ml(?: [a-z][a-z0-9_-]*)+')


def is_denied(command, rules):
    return any(command == rule or command.startswith(rule + ' ') for rule in rules)


def known_command(command):
    """仅校验路径格式，不依赖某个 CLI 版本的命令目录。"""
    parts = command.split()
    return bool(COMMAND_PATTERN.fullmatch(command)) or (
        len(parts) >= 2 and parts[0] == "ml" and parts[1] in CONTROL_GROUPS)


def parse_commands(value):
    selected = []
    for line in value.splitlines():
        command = ' '.join(line.split())
        if command and command not in selected:
            selected.append(command)
    return selected


def denied_commands(environment):
    return sorted(rule.command for rule in environment.forbidden_commands)


def policy_snapshot(environment):
    return {'environment': environment.name, 'platform_origin': environment.platform_origin,
            'revision': environment.command_policy_revision or 0, 'deny': denied_commands(environment)}


def save_policy(environment, selected, actor):
    if len(selected) != len(set(selected)) or len(selected) > 500:
        raise HTTPException(400, '禁止命令不得重复或超过 500 项')
    previous = set(denied_commands(environment))
    for command in selected:
        if (len(command) > 128 or not COMMAND_PATTERN.fullmatch(command)
                or command.split()[1] in CONTROL_GROUPS):
            raise HTTPException(400, '每行需填写一条业务命令或分组，如 ml jupyter；不支持参数、通配符或基础管理入口')
    if set(selected) != previous:
        environment.forbidden_commands = [rule for rule in environment.forbidden_commands if rule.command in selected]
        environment.forbidden_commands.extend(EnvironmentCommandDeny(command=command, created_by=actor)
                                               for command in sorted(set(selected) - previous))
        environment.command_policy_revision = (environment.command_policy_revision or 0) + 1
