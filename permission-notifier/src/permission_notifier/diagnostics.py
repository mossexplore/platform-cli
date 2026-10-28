"""Bounded diagnostics without request credentials or arbitrary response bodies."""
import json
from urllib.parse import urlsplit
import httpx


def target(url):
    parsed = urlsplit(url)
    # Path and query may contain credentials; expose only the destination origin.
    return f'{parsed.scheme}://{parsed.hostname}' + (f':{parsed.port}' if parsed.port else '')


def failure(exc):
    if isinstance(exc, httpx.ProxyError):
        return 'PROXY_ERROR'
    if isinstance(exc, httpx.ConnectTimeout):
        return 'CONNECT_TIMEOUT'
    if isinstance(exc, httpx.ReadTimeout):
        return 'READ_TIMEOUT'
    if isinstance(exc, httpx.ConnectError):
        return 'CONNECTION_FAILED'
    if isinstance(exc, (OSError, ValueError)):
        return 'LOCAL_NETWORK_CONFIG_ERROR'
    return 'TRANSPORT_ERROR'


def response_summary(response, secrets):
    """Keep known diagnostic fields only; never expose HTML or echoed payloads."""
    try:
        body = response.json()
    except ValueError:
        return '非 JSON 响应；正文未展示，请查消息服务日志'
    if not isinstance(body, dict):
        return 'JSON 非对象；请查消息服务日志'
    allowed = {'code', 'message', 'msg', 'error', 'success', 'request_id', 'trace_id', 'message_id'}
    values = {}
    for key in allowed:
        value = body.get(key)
        if value is not None and isinstance(value, (str, bool, int, float)):
            text = str(value)
            for secret in secrets:
                if secret:
                    text = text.replace(secret, '[已隐藏]')
            values[key] = text[:400]
    return json.dumps(values, ensure_ascii=False) if values else '无可展示的诊断字段；请查消息服务日志'
