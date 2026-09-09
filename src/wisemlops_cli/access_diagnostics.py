"""权限请求的有限诊断：不记录完整请求头、响应正文或网络异常文本。"""
import re
from time import monotonic
from urllib.parse import urlsplit


def endpoint(value):
    try:
        parsed = urlsplit(str(value))
        host = parsed.hostname or ''
        if ':' in host:
            host = '[' + host + ']'
        return f'{parsed.scheme}://{host}' + (f':{parsed.port}' if parsed.port else '') + parsed.path
    except ValueError:
        return '地址格式无效'


class AccessDiagnostics:
    def __init__(self, emit):
        self.emit = emit
        self.started = None
        self.secrets = []

    def line(self, label, value):
        text = str(value)
        for secret in self.secrets:
            if secret:
                text = text.replace(secret, '[已隐藏]')
        text = re.sub(r'(?i)(https?://)[^\s/@]+@', r'\1[已隐藏]@', text)
        text = ''.join(char for char in text if char.isprintable())[:1000]
        self.emit(f'{label}: {text}')

    def begin(self, url, profile, credentials, selection, command, timeout):
        self.secrets = [credentials.cookie, credentials.csrftoken]
        self.started = monotonic()
        self.line('请求', 'POST ' + endpoint(url))
        self.line('账号', credentials.username)
        self.line('环境', profile.name)
        self.line('平台源地址', endpoint(profile.base_url))
        self.line('businessid', selection.business_id)
        self.line('命令', command)
        self.line('超时设置（秒）', timeout)
        self.line('网络设置', '沿用 HTTPX 环境配置；不更改代理、证书或重定向策略')

    def trace(self, event, info):
        # 只消费连接元数据，绝不输出 info 中的请求对象或异常。
        if event == 'connection.connect_tcp.started':
            host = info.get('host', '')
            if isinstance(host, bytes):
                host = host.decode('ascii', errors='replace')
            self.line('TCP 连接目标（可能是代理）', f"{host}:{info.get('port', '')}")
        elif event == 'connection.connect_tcp.complete':
            self.peer(info.get('return_value'))

    def peer(self, stream):
        if stream is None:
            return
        try:
            address = stream.get_extra_info('server_addr')
            if isinstance(address, tuple) and len(address) >= 2:
                self.line('TCP 对端', f'{address[0]}:{address[1]}')
        except Exception:
            # 诊断能力不可用不能阻断正常权限检查。
            pass

    def response(self, response):
        self.line('HTTP 状态', response.status_code)
        self.peer(response.extensions.get('network_stream'))
        for name in ('server', 'via', 'content-type', 'x-request-id', 'x-correlation-id'):
            self.line('响应头 ' + name, response.headers.get(name, '未提供'))

    def finish(self):
        if self.started is not None:
            self.line('请求耗时（秒）', f'{monotonic() - self.started:.3f}')
