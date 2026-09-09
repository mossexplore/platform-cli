"""权限服务默认直连；保留企业 CA 环境配置，不改变业务客户端。"""
import os
import ssl
from .errors import ConfigError


def tls_verify():
    # Match HTTPX's precedence while disabling only environment proxy routing.
    cafile = os.environ.get('SSL_CERT_FILE')
    capath = os.environ.get('SSL_CERT_DIR')
    try:
        if cafile:
            return ssl.create_default_context(cafile=cafile)
        if capath:
            return ssl.create_default_context(capath=capath)
        return True
    except (OSError, ValueError):
        raise ConfigError('权限服务 CA 配置无法加载，请检查 SSL_CERT_FILE 或 SSL_CERT_DIR') from None


def permission_url(base):
    base = base.rstrip('/')
    if not base.endswith('/cli-permission'):
        base += '/cli-permission'
    return base + '/api/v1/access/check'
