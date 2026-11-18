"""权限服务的代理与 CA 来源独立配置，始终校验证书。"""
import os
from pathlib import Path
import socket
import ssl

import certifi
import httpx

from .errors import ConfigError, MlError


def validate_ca_settings(settings):
    source = settings.get('ca_source', 'env')
    if not isinstance(source, str) or source not in {'certifi', 'env', 'custom'}:
        raise ConfigError('access_control.ca_source 必须为 certifi、env 或 custom')
    cafile = settings.get('ca_file')
    if source == 'custom':
        if not isinstance(cafile, str) or not cafile.strip() or not Path(cafile).is_absolute():
            raise ConfigError('access_control.ca_source 为 custom 时，ca_file 必须是 CA 文件的绝对路径')
    elif 'ca_file' in settings:
        raise ConfigError('access_control.ca_file 仅可与 ca_source=custom 一起使用')
    return source


def ca_description(settings):
    source = settings.get('ca_source', 'env')
    if source == 'certifi':
        return 'certifi 公共 CA，忽略 SSL_CERT_FILE 和 SSL_CERT_DIR'
    if source == 'custom':
        return 'custom 指定 CA 文件'
    if os.environ.get('SSL_CERT_FILE'):
        return 'env 环境变量 SSL_CERT_FILE'
    if os.environ.get('SSL_CERT_DIR'):
        return 'env 环境变量 SSL_CERT_DIR'
    return 'env 未设置 CA 环境变量，使用默认公共 CA'


def tls_verify(settings=None):
    settings = settings or {}
    source = validate_ca_settings(settings)
    try:
        if source == 'certifi':
            return ssl.create_default_context(cafile=certifi.where())
        if source == 'custom':
            return ssl.create_default_context(cafile=settings['ca_file'])
        # Preserve the legacy environment CA precedence, independently of proxies.
        cafile = os.environ.get('SSL_CERT_FILE')
        capath = os.environ.get('SSL_CERT_DIR')
        if cafile:
            return ssl.create_default_context(cafile=cafile)
        if capath:
            return ssl.create_default_context(capath=capath)
        return True
    except (OSError, ValueError):
        raise ConfigError(f'权限服务 CA 配置无法加载，来源：{ca_description(settings)}；请检查对应 CA 文件或目录') from None


def connection_error(exc, settings, fallback):
    """Classify typed causes without exposing raw exceptions, URLs or credentials."""
    pending, seen = [exc], set()
    causes = []
    while pending:
        cause = pending.pop()
        if id(cause) in seen:
            continue
        seen.add(id(cause))
        causes.append(cause)
        pending.extend(item for item in (cause.__cause__, cause.__context__) if item is not None)
    if any(isinstance(cause, ssl.SSLCertVerificationError) for cause in causes):
        return MlError(f'权限服务证书校验失败，业务请求已停止；CA 来源：{ca_description(settings)}；'
                       '请核对服务端证书链和 access_control.ca_source，不要关闭证书校验')
    if any(isinstance(cause, socket.gaierror) for cause in causes):
        return MlError('权限服务连接目标域名解析失败，请检查权限服务地址、代理地址及 DNS')
    if isinstance(exc, httpx.ConnectTimeout):
        return MlError('连接权限服务超时，请检查地址、端口和网络')
    if isinstance(exc, httpx.ReadTimeout):
        return MlError('等待权限服务响应超时，请检查服务日志及 timeout_seconds 配置')
    if isinstance(exc, httpx.TimeoutException):
        return MlError('权限服务请求超时，请检查网络及 timeout_seconds 配置')
    return MlError(fallback)


def permission_url(base):
    base = base.rstrip('/')
    if not base.endswith('/cli-permission'):
        base += '/cli-permission'
    return base + '/api/v1/access/check'
