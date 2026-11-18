"""将平台访问 URL 转换为可信的 Jupyter 根地址，不泄露 Token。"""
import re
from urllib.parse import urlsplit, urlunsplit, parse_qsl, unquote

from ..jupyter.connection import JupyterError


def _gateway_origin(server_url):
    if not isinstance(server_url, str) or any(ord(c) <= 32 for c in server_url):
        raise ValueError()
    base = urlsplit(server_url)
    if (base.scheme not in ('http', 'https') or not base.hostname or base.username or base.password
            or base.path not in ('', '/') or base.query or base.fragment):
        raise ValueError()
    _ = base.port  # 触发非法或越界端口校验。
    return base


def validate_server_urls(settings):
    mapping = settings.get('server_urls_by_region')
    if mapping is None:
        candidates = [('server_url', settings.get('server_url'))]
    else:
        if not isinstance(mapping, dict) or not mapping:
            raise JupyterError('jupyter.server_urls_by_region 必须是非空对象')
        candidates = []
        for region, server_url in mapping.items():
            if not isinstance(region, str) or not region or any(c.isspace() for c in region):
                raise JupyterError('jupyter.server_urls_by_region 的 region 必须是非空且不含空白字符的字符串')
            candidates.append((f'server_urls_by_region.{region}', server_url))
    for name, server_url in candidates:
        try:
            _gateway_origin(server_url)
        except (ValueError, TypeError):
            raise JupyterError(
                f'jupyter.{name} 必须是不含路径、凭据、查询参数或片段的 HTTP(S) 地址'
            ) from None


def server_url_for_instance(settings, item):
    mapping = settings.get('server_urls_by_region')
    if mapping is None:
        return settings.get('server_url')
    region = item.get('region')
    if not isinstance(region, str) or not region:
        raise JupyterError('Web Studio 响应缺少 region，无法确定 Jupyter 访问前缀')
    if region not in mapping:
        supported = '、'.join(sorted(mapping))
        raise JupyterError(
            f'Web Studio region {region} 未配置 Jupyter 访问前缀；'
            f'请配置 jupyter.server_urls_by_region（当前已配置：{supported}）'
        )
    return mapping[region]


def parse_access_url(server_url, access_url):
    try:
        base = _gateway_origin(server_url)
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
