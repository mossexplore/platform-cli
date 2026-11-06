"""具体环境的命令禁止策略，仅限制两个 Jupyter 文件入口。"""
from .errors import ConfigError, MlError
from .adapters.registry import require_supported

RESTRICTABLE = frozenset({'jupyter files upload', 'jupyter files download'})


def parse_policy(value):
    if not isinstance(value, dict) or set(value) - {'deny'}:
        raise ConfigError('command_policy 必须是仅包含 deny 的对象')
    deny = value.get('deny', [])
    message = 'command_policy.deny 只接受 ml jupyter files upload 和 ml jupyter files download 的列表'
    if not isinstance(deny, list) or any(not isinstance(item, str) for item in deny):
        raise ConfigError(message)
    # Match the permission system's full paths while retaining legacy local entries.
    deny = [' '.join(item.split()).removeprefix('ml ') for item in deny]
    if any(item not in RESTRICTABLE for item in deny):
        raise ConfigError(message)
    if len(deny) != len(set(deny)):
        raise ConfigError('command_policy.deny 不得重复')
    return tuple(deny)


def require_command(profile, command):
    require_supported(getattr(profile, 'platform_type', 'wiserec'), command)
    if command in getattr(profile, 'denied_commands', ()):
        raise MlError(f'当前环境 {profile.name} 禁止执行 ml {command}；请查看 command_policy 配置')
