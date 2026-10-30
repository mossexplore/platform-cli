"""Web Studio connection discovery and guarded Jupyter HTTP/WebSocket operations."""
import json
import tempfile
import time
from pathlib import Path
from urllib.parse import quote
import websocket
from wiserec_cli.services.webstudio import WebStudioService
from wiserec_cli.webstudio.resolve import online_instance
from wiserec_cli.webstudio.urls import parse_access_url, server_url_for_instance
from wiserec_cli.jupyter.connection import Connection, JupyterClient
from wiserec_cli.jupyter import files
from wiserec_cli.jupyter.execution import execute
from wiserec_cli.jupyter.notebook import run_notebook
from .artifacts import MAX_BYTES
from .errors import AppError


class GuardedSocket:
    def __init__(self, socket, platform):
        self.socket, self.platform = socket, platform

    def send(self, data, *args, **kwargs):
        self.platform.agent_guard()
        return self.socket.send(data, *args, **kwargs)

    def recv(self):
        self.platform.agent_check()
        result = self.socket.recv()
        if len(result) > MAX_BYTES: raise ValueError('WebSocket 输出过大')
        return result

    def settimeout(self, timeout): self.socket.settimeout(timeout)
    def close(self): self.socket.close()


def connection(platform, studio_id):
    service = WebStudioService(platform)
    item = online_instance(service, studio_id)
    settings = platform.agent_environment.jupyter_gateways
    if not settings:
        raise AppError('JUPYTER_UNCONFIGURED', '请配置当前环境 jupyter_gateways 的区域和网关地址')
    server = server_url_for_instance({'server_urls_by_region': settings}, item)
    url, token = parse_access_url(server, service.access(studio_id))
    return Connection(url, token, platform.business_id, verify=platform.agent_environment.verify_ssl,
                      timeout=30, studio_id=studio_id)


def dispatch(platform, name, a):
    conn = connection(platform, a.pop('studio_id'))

    class GuardedJupyter(JupyterClient):
        def request(self, *args, **kwargs):
            platform.agent_guard()
            result = super().request(*args, **kwargs)
            platform.agent_check()
            return result

        def _bootstrap_webstudio_session(self):
            platform.agent_guard()
            return super()._bootstrap_webstudio_session()

        def socket(self, path):
            platform.agent_guard()
            return GuardedSocket(super().socket(path), platform)

    with GuardedJupyter(conn, transport=platform.agent_transport) as client:
        store = platform.agent_artifacts
        if name in ('jupyter_doctor', 'login_webstudio'):
            return {'studio_id': conn.studio_id, 'kernels': client.request('GET', 'api/kernelspecs'),
                    'terminals': client.request('GET', 'api/terminals')}
        if name == 'jupyter_exec':
            return execute(client, max_output=20000, startup_timeout=30, **a)
        if name == 'jupyter_notebook_run':
            source = store.path(a.pop('artifact_id'))
            with tempfile.TemporaryDirectory() as temp:
                result = run_notebook(client, source, Path(temp), startup_timeout=30, emit=lambda _: None, **a)
                path = Path(result.pop('notebook'))
                result['artifact'] = store.put(path.name, path.read_bytes())
                return result
        if name.startswith('jupyter_terminal_'):
            return terminal(client, name.removeprefix('jupyter_terminal_'), a)
        action = name.removeprefix('jupyter_files_')
        path = a['path']
        if action in ('list', 'stat', 'read'):
            return files.get(client, path, content=action != 'stat', format='text' if action == 'read' else None)
        if action in ('write', 'upload'):
            data = a['content'].encode() if action == 'write' else store.path(a['artifact_id']).read_bytes()
            return files.save(client, path, data, a['overwrite'], text=action == 'write')
        if action == 'mkdir': return files.mkdir(client, path)
        if action == 'move': return files.move(client, path, a['destination'])
        if action == 'copy': return files.copy(client, path, a['destination'])
        if action == 'delete': return files.delete(client, path)
        if action == 'download':
            with tempfile.TemporaryDirectory() as temp:
                local = Path(temp) / 'download'
                files.download(client, path, local)
                return store.put(path.rsplit('/', 1)[-1], local.read_bytes())
        raise ValueError('未知 Jupyter 操作')


def terminal(client, action, args):
    if action == 'list': return client.request('GET', 'api/terminals')
    if action == 'create': return client.request('POST', 'api/terminals', {})
    name = args['name']
    if name not in [x['name'] for x in client.request('GET', 'api/terminals')]:
        raise AppError('TERMINAL_NOT_FOUND', '当前身份不可见该终端', 404)
    if action == 'stop':
        client.request('DELETE', 'api/terminals/' + quote(name, safe=''))
        return {'closed': True}
    socket = client.socket('terminals/websocket/' + quote(name, safe=''))
    try:
        if args['input']: socket.send(json.dumps(['stdin', args['input']]))
        socket.settimeout(1)
        messages, size, deadline = [], 0, time.monotonic() + 3
        while time.monotonic() < deadline and size < 20000:
            try: data = socket.recv()
            except websocket.WebSocketTimeoutException: break
            if not data: break
            size += len(data)
            messages.append(data[:max(0, 20000 - sum(map(len, messages)))])
        return {'name': name, 'output': messages, 'complete_history': False,
                'note': '本次仅断开连接，终端继续运行；不自动重复输入'}
    finally:
        socket.close()
