"""非交互执行：每次独立 Kernel，不自动重放请求。"""
import time
from pathlib import Path
from uuid import uuid4

from .connection import JupyterError, remote_path
from .protocol import KernelChannel

MIME = 'application/vnd.wiserec.exec+json'


def execute(client, argv, cwd='', timeout=60, startup_timeout=60, max_output=1048576, kernel=None):
    cwd = remote_path(cwd)
    if client.request('GET', client.contents(cwd) + '?content=0')['type'] != 'directory':
        raise JupyterError('--cwd 必须是远端已有目录')
    result = {'id': str(uuid4()), 'status': 'STARTING', 'exit_code': None,
              'stdout': '', 'stderr': '', 'cwd': cwd, 'cleanup_errors': [],
              'remote_state': 'not_started'}
    kernel_id = socket = None
    submitted = False
    try:
        created = client.request('POST', 'api/kernels', {
            'name': kernel or client.connection.kernel, 'path': cwd})
        kernel_id = created['id']
        result['kernel_id'] = kernel_id
        socket = client.socket('api/kernels/' + kernel_id + '/channels')
        channel = KernelChannel(socket)
        info = channel.ready(startup_timeout)
        if info.get('language_info', {}).get('name', '').lower() != 'python':
            raise JupyterError('exec 需要 Python Kernel；请使用 --kernel 指定')
        worker = Path(__file__).with_name('exec_worker.py').read_text(encoding='utf-8')
        code = worker + '\nfrom IPython.display import display\n'
        code += f'display({{{MIME!r}: run_process({argv!r}, {timeout!r}, {max_output!r})}}, raw=True)'
        submitted = True
        request = channel.send('execute_request', {'code': code, 'silent': False,
            'store_history': False, 'user_expressions': {}, 'allow_stdin': False, 'stop_on_error': True})
        payload = reply = None
        idle = False
        for message in channel.messages(request, time.monotonic() + timeout + 15):
            kind = message.get('header', {}).get('msg_type')
            content = message.get('content', {})
            if kind == 'display_data':
                payload = content.get('data', {}).get(MIME, payload)
            elif kind == 'execute_reply':
                reply = content
            elif kind == 'status' and content.get('execution_state') == 'idle':
                idle = True
            if reply is not None and idle:
                if reply.get('status') != 'ok' or not isinstance(payload, dict):
                    raise JupyterError('远端执行助手失败，进程状态待确认')
                result.update(payload)
                result['remote_state'] = 'finished'
                break
        else:
            raise JupyterError('执行通道提前结束')
    except KeyboardInterrupt:
        result.update(status='INTERRUPTED', error='本地中断；远端进程状态待确认', remote_state='unknown' if submitted else 'not_started')
    except Exception as exc:
        result.update(status='LOST' if submitted else 'FAILED',
                      error=str(exc) if isinstance(exc, (JupyterError, TimeoutError)) else type(exc).__name__,
                      remote_state='unknown' if submitted else 'not_started')
    finally:
        if socket is not None:
            try:
                socket.close()
            except Exception:
                pass
        if kernel_id:
            try:
                client.request('DELETE', 'api/kernels/' + kernel_id)
            except Exception:
                result['cleanup_errors'].append('释放专用 Kernel 失败，请检查 kernel_id')
    return result
