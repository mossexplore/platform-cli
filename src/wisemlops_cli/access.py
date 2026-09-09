"""在线授权检查：以当前登录账号检查环境授权。"""
from __future__ import annotations

from typing import Any, Dict
from urllib.parse import urlsplit
import httpx
from .errors import ConfigError, MlError
from .access_transport import permission_url, tls_verify


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
                     and parsed.path in ('', '/', '/cli-permission', '/cli-permission/'))
            _ = parsed.port
        except (TypeError, ValueError):
            valid = False
        if not valid:
            raise ConfigError('access_control.url 必须是 HTTP 或 HTTPS 地址，路径仅允许 /cli-permission，不含凭据、查询参数或片段')
    if not isinstance(value.get('use_env_proxy', False), bool):
        raise ConfigError('access_control.use_env_proxy 必须是布尔值')
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


def check_access(settings, profile, credentials, selection, *, command="unknown", full_command="", diagnostics=None):
    if not settings or not settings.get('enabled', True):
        return None
    url = permission_url(settings['url'])
    if diagnostics:
        diagnostics.begin(url, profile, credentials, selection, command, settings.get('timeout_seconds', 15))
        diagnostics.line('网络设置', '沿用环境代理配置' if settings.get('use_env_proxy', False) else '权限服务直连，已忽略环境代理')
    try:
        with httpx.Client(timeout=settings.get('timeout_seconds', 15),
                          verify=tls_verify(), follow_redirects=False,
                          trust_env=settings.get('use_env_proxy', False)) as client:
            response = client.post(url,
                                   headers={'businessid': selection.business_id},
                                   json={'username': credentials.username,
                                         'environment': profile.name,
                                         'platform_origin': profile.base_url,
                                         'command': command, 'full_command': full_command},
                                   **({'extensions': {'trace': diagnostics.trace}} if diagnostics else {}))
            if diagnostics:
                diagnostics.response(response)
        if response.status_code == 401:
            raise MlError('权限服务拒绝请求，请检查客户端与服务端版本及接入配置')
        if response.status_code != 200:
            raise MlError(f'权限检查失败，HTTP {response.status_code}，业务请求已停止，请联系管理员')
        result = response.json()
    except httpx.ConnectTimeout:
        raise MlError('连接权限服务超时，业务请求已停止，请检查地址、端口和网络') from None
    except httpx.ReadTimeout:
        raise MlError('等待权限服务响应超时，业务请求已停止，请检查服务日志、数据库及 timeout_seconds 配置') from None
    except httpx.TimeoutException:
        raise MlError('权限服务请求超时，业务请求已停止，请检查网络及 timeout_seconds 配置') from None
    except httpx.ConnectError:
        raise MlError('无法连接权限服务，业务请求已停止，请检查地址、端口、HTTP/HTTPS 协议及证书') from None
    except httpx.RemoteProtocolError:
        raise MlError('权限服务连接被关闭或 HTTP 响应不完整，业务请求已停止，请检查服务或网关日志及 HTTP/HTTPS 协议') from None
    except httpx.HTTPError:
        raise MlError('权限服务 HTTP 通信异常，业务请求已停止，请检查服务或网关日志') from None
    except ValueError:
        # 不回显异常或响应正文，避免泄露认证信息和内部页面内容。
        raise MlError('权限服务返回 HTTP 200，但响应不是有效 JSON，业务请求已停止，请检查权限接口路由及网关响应') from None
    finally:
        if diagnostics:
            diagnostics.finish()
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
