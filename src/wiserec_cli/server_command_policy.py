"""服务端策略快照仅用于命令树展示，实际执行始终使用实时鉴权。"""
import hashlib
import json
import os
from datetime import datetime, timezone
from .config import user_config_dir


def cache_path(settings, profile):
    identity = [settings.get('url', '').rstrip('/'), profile.name, profile.base_url]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return user_config_dir() / 'command-policies' / (key + '.json')


def validated(policy, profile):
    return (isinstance(policy, dict) and policy.get('environment') == profile.name
            and policy.get('platform_origin') == profile.base_url
            and type(policy.get('revision')) is int and policy['revision'] >= 0
            and isinstance(policy.get('deny'), list)
            and all(isinstance(command, str) and command.startswith('ml ') and len(command) <= 128
                    for command in policy['deny']))


def remember(settings, profile, result):
    policy = result.get('command_policy')
    if not validated(policy, profile):
        return
    path = cache_path(settings, profile)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = dict(policy, synced_at=datetime.now(timezone.utc).isoformat())
        temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
        temporary.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        temporary.replace(path)
    except OSError:
        # 展示缓存故障不能掩盖实时鉴权结果，也不能把拒绝变成允许。
        pass


def load(settings, profile):
    try:
        policy = json.loads(cache_path(settings, profile).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return policy if validated(policy, profile) else None
