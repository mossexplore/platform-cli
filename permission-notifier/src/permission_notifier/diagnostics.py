"""Bounded diagnostics without request credentials or arbitrary response bodies."""
import json
import re
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
    """Render nested responses as bounded plain text with credential redaction."""
    def redact(text):
        for secret in sorted(filter(None, secrets), key=len, reverse=True):
            text = text.replace(secret, '[已隐藏]')
        text = re.sub(r'(?i)(bearer\s+)[^\s"<>]+', r'\1[已隐藏]', text)
        return re.sub(
            r'(?i)((?:auth|token|password|secret|api[_-]?key|cookie)["\']?\s*[:=]\s*["\']?)[^\s"\'<>&,}]+',
            r'\1[已隐藏]', text)

    def clean(value, depth=0):
        if depth > 12:
            return '[嵌套过深，已省略]'
        if isinstance(value, dict):
            return {redact(str(key)): '[已隐藏]' if any(
                word in re.sub(r'[^a-z]', '', str(key).lower())
                for word in ('auth', 'token', 'password', 'secret', 'apikey', 'cookie'))
                else clean(item, depth+1) for key, item in list(value.items())[:100]}
        if isinstance(value, list):
            return [clean(item, depth+1) for item in value[:100]]
        return redact(value) if isinstance(value, str) else value

    try:
        text = json.dumps(clean(response.json()), ensure_ascii=False, indent=2)
    except (ValueError, RecursionError):
        text = redact(response.text)
    if not text:
        return '（空响应体）'
    return text[:8000] + ('\n[响应体超过 8000 字符，已截断]' if len(text) > 8000 else '')
