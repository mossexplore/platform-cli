"""Real permission service access; business simulation cannot grant permissions."""
import json
from urllib.parse import urlsplit
import httpx
from wiserec_cli.access import validate_settings
from wiserec_cli.access_transport import permission_url, tls_verify


def settings(url, username):
    if not username or len(username) > 128 or username != username.strip():
        raise ValueError('必须指定权限系统登记的账号 --username')
    value = validate_settings({'enable': True, 'url': url, 'use_env_proxy': False})
    parsed = urlsplit(url)
    if parsed.hostname.endswith('.mock.invalid'):
        raise ValueError('权限服务必须是真实服务，不能使用模拟域名')
    return value


class PermissionTransport:
    def __init__(self, root):
        metadata = json.loads((root/'workspace.json').read_text())
        url = metadata['permission_url']
        settings(url, metadata['username'])
        check = httpx.URL(permission_url(url))
        self.urls = {check.copy_with(path=check.path.rsplit('/', 1)[0]+'/'+name)
                     for name in ('check', 'summary', 'environments')}
        self.origin = (check.scheme, check.host, check.port)
        self.network = None

    def matches(self, request):
        return (request.url.scheme, request.url.host, request.url.port) == self.origin

    def handle_request(self, request):
        if request.method != 'POST' or request.url not in self.urls:
            raise httpx.ConnectError('演示环境只允许权限服务的检查接口', request=request)
        if self.network is None:
            self.network = httpx.HTTPTransport(verify=tls_verify(), trust_env=False, retries=0)
        return self.network.handle_request(request)

    def close(self):
        if self.network is not None:
            self.network.close()


def authorize(root, profile, business_id, command):
    """Also cover keepalive requests that do not use Runtime.authenticated_call."""
    from types import SimpleNamespace
    from wiserec_cli.access import check_access
    metadata = json.loads((root/'workspace.json').read_text())
    return check_access(settings(metadata['permission_url'], metadata['username']),
                        SimpleNamespace(name=profile, base_url=f'https://{profile}.mock.invalid'),
                        SimpleNamespace(username=metadata['username']),
                        SimpleNamespace(business_id=business_id), command=command)
