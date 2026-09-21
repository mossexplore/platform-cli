"""将平台访问 URL 转换为可信的 Jupyter 根地址，不泄露 Token。"""
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, unquote

from ..jupyter.connection import JupyterError


def parse_access_url(server_url, access_url):
    try:
        base = urlsplit(server_url)
        if (base.scheme not in ('http', 'https') or not base.hostname or base.username or base.password
                or base.path not in ('', '/') or base.query or base.fragment):
            raise ValueError()
        origin = (base.scheme, base.hostname.lower(), base.port or (443 if base.scheme == 'https' else 80))
        if not isinstance(access_url, str) or any(ord(c) <= 32 for c in access_url) or '\\' in access_url:
            raise ValueError()
        access = urlsplit(access_url)
        if access_url.startswith('//') or access.username or access.password or access.fragment:
            raise ValueError()
        if access.scheme or access.netloc:
            other = (access.scheme, (access.hostname or '').lower(), access.port or (443 if access.scheme == 'https' else 80))
            if other != origin:
                raise ValueError()
        if not access.path.startswith('/'):
            raise ValueError()
        decoded = unquote(access.path)
        if ('\\' in decoded or '%' in decoded or any(ord(c) < 32 for c in decoded)
                or any(p in ('.', '..') for p in decoded.split('/')) or '//' in decoded):
            raise ValueError()
        # 仅接受已确认的页面入口；保留平台返回的实例路由。
        match = re.fullmatch(r'(/.+)/lab/?', access.path)
        if not match:
            raise ValueError()
        params = parse_qsl(access.query, keep_blank_values=True, encoding='utf-8', errors='strict')
        tokens = [v for k, v in params if k == 'token']
        if len(tokens) != 1 or any(ord(c) < 32 or ord(c) == 127 for c in tokens[0]):
            raise ValueError()
        if any(k != 'token' for k, _ in params):
            raise JupyterError('accessUrl 含未支持的查询参数，需要先确认网关路由含义')
        return urlunsplit((base.scheme, base.netloc, match[1] + '/', '', '')), tokens[0]
    except (ValueError, TypeError, UnicodeError):
        raise JupyterError('Web Studio 访问地址无效：检查网关源站、/lab 路径及唯一的 token 参数') from None
