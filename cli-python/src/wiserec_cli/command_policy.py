"""环境禁止策略：业务命令及其所有子命令。"""
import re
from .errors import ConfigError, MlError
from .adapters.registry import require_supported

CONTROL_GROUPS = {"login", "logout", "auth", "env", "tree", "history", "context", "access", "business"}
COMMAND_PATTERN = re.compile(r'[a-z][a-z0-9_-]*(?: [a-z][a-z0-9_-]*)*')


def is_denied(command, rules):
    command = ' '.join(command.split()).removeprefix('ml ')
    return any(command == rule or command.startswith(rule + ' ') for rule in rules)


def parse_policy(value):
    if not isinstance(value, dict) or set(value) - {'deny'}:
        raise ConfigError('command_policy 必须是仅包含 deny 的对象')
    deny = value.get('deny', [])
    message = 'command_policy.deny 需填写业务命令或分组，如 ml jupyter；不支持参数、通配符或基础管理入口'
    if not isinstance(deny, list) or any(not isinstance(item, str) for item in deny):
        raise ConfigError(message)
    # Match the permission system's full paths while retaining legacy local entries.
    deny = [' '.join(item.split()).removeprefix('ml ') for item in deny]
    if len(deny) > 500 or any(item == 'ml' or len(item) > 125 or not COMMAND_PATTERN.fullmatch(item)
            or item.split()[0] in CONTROL_GROUPS for item in deny):
        raise ConfigError(message)
    if len(deny) != len(set(deny)):
        raise ConfigError('command_policy.deny 不得重复')
    return tuple(deny)


def require_command(profile, command):
    require_supported(getattr(profile, 'platform_type', 'wiserec'), command)
    if is_denied(command, getattr(profile, 'denied_commands', ())):
        raise MlError(f'当前环境 {profile.name} 禁止执行 ml {command}')
