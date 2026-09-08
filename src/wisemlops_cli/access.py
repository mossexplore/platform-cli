"""在线授权检查：仅信任权限服务验证过的平台身份。"""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlsplit
import httpx
from .errors import AuthenticationError, ConfigError, MlError


def validate_settings(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError('access_control 必须是对象')
    if not isinstance(value.get('enabled', True), bool):
        raise ConfigError('access_control.enabled 必须是布尔值')
    if value.get('enabled', True):
        url = value.get('url', '')
        try:
            if not isinstance(url, str):
                raise ValueError()
            parsed = urlsplit(url)
            valid = (parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username
                     and not parsed.password and not parsed.query and not parsed.fragment
                     and parsed.path in ('', '/'))
            _ = parsed.port
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise ConfigError('access_control.url 必须是 HTTP 或 HTTPS 源地址，不含路径或凭据')
    timeout = value.get('timeout_seconds', 15)
    if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 1 <= timeout <= 120:
        raise ConfigError('access_control.timeout_seconds 必须在 1–120 秒之间')
    return dict(value)


def command_name(context):
    """仅取已解析的命令名，不包含用户参数、密码或自定义配置。"""
    parts = []
    while context is not None and context.parent is not None:
        if context.command.name:
            parts.append(context.command.name)
        context = context.parent
    return ('ml ' + ' '.join(reversed(parts)))[:128] if parts else 'unknown'


def check_access(settings, profile, credentials, selection, *, command="unknown"):
    if not settings or not settings.get('enabled', True):
        return None
    try:
        with httpx.Client(timeout=settings.get('timeout_seconds', 15),
                          verify=True, follow_redirects=False) as client:
            response = client.post(settings['url'].rstrip('/') + '/api/v1/access/check',
                                   headers={'X-Platform-Cookie': credentials.cookie,
                                            'X-Platform-Csrf': credentials.csrftoken,
                                            'businessid': selection.business_id},
                                   json={'environment': profile.name,
                                         'platform_origin': profile.base_url,
                                         'command': command})
        if response.status_code == 401:
            raise AuthenticationError('权限服务核验平台身份失败，请重新登录')
        if response.status_code != 200:
            raise MlError(f'权限检查失败，HTTP {response.status_code}，业务请求已停止，请联系管理员')
        result = response.json()
    except (httpx.HTTPError, ValueError):
        # 不拼接可能包含平台 Cookie、认证信息的网络异常。
        raise MlError('权限服务连接失败或响应无效，业务请求已停止，请检查网络、证书或联系管理员') from None
    if not isinstance(result, dict) or type(result.get('allowed')) is not bool:
        raise MlError('权限服务响应格式错误，业务请求已停止')
    if not result['allowed']:
        messages = {
            'ENVIRONMENT_DISABLED': '当前环境未启用权限访问',
            'ENVIRONMENT_MISMATCH': '当前环境与平台地址不匹配',
            'USER_DISABLED': '当前账号未获授权或已停用',
            'NOT_GRANTED': '当前账号未获当前环境授权',
            'GRANT_EXPIRED': '当前环境的使用授权已过期',
        }
        reason = result.get('reason')
        message = messages.get(reason, '当前账号没有访问权限') if isinstance(reason, str) else '当前账号没有访问权限'
        raise MlError(message + '，请联系管理员')
    if result.get('username') != credentials.username or result.get('environment') != profile.name:
        raise MlError('权限服务返回的账号或环境与当前登录不一致，请重新登录')
    return result
