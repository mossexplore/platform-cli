"""Foreground-only local Jupyter: no unverified PID termination."""
import json
import os
import secrets
import subprocess
import sys
from urllib.parse import urlsplit


def validate_connection(root, connection):
    path = root / 'jupyter.json'
    if not path.is_file():
        raise ValueError('请先通过演示管理脚本启动本地 Jupyter')
    settings = json.loads(path.read_text())
    parts = urlsplit(connection.url)
    if parts.hostname != '127.0.0.1' or connection.url != settings['url'] or connection.token != settings['token']:
        raise ValueError('演示环境禁止连接外部 Jupyter 或使用其他凭据')


def run(root, port):
    if not 1024 <= port <= 65535:
        raise ValueError('端口必须在 1024–65535 范围')
    metadata = root / 'jupyter.json'
    if metadata.exists():
        raise ValueError('本地 Jupyter 已登记；请关闭原启动进程')
    token = secrets.token_urlsafe(32)
    url = f'http://127.0.0.1:{port}/demo/'
    for name in ('runtime', 'config', 'data', 'ipython', 'files'):
        (root / 'jupyter' / name).mkdir(exist_ok=True)
    settings = {'ServerApp': {'ip': '127.0.0.1', 'port': port, 'port_retries': 0,
                'open_browser': False, 'root_dir': str(root / 'jupyter/files'),
                'base_url': '/demo/', 'log_level': 'ERROR'}, 'IdentityProvider': {'token': token}}
    server_config = root / 'jupyter/server.json'
    server_config.write_text(json.dumps(settings))
    server_config.chmod(0o600)
    config_path = root / 'config.json'
    config = json.loads(config_path.read_text())
    for profile in config['profiles']:
        profile['jupyter'] = {'mode': 'webstudio', 'server_url': f'http://127.0.0.1:{port}/'}
    config_path.write_text(json.dumps(config, indent=2))
    metadata.write_text(json.dumps({'url': url, 'token': token}))
    metadata.chmod(0o600)
    environment = dict(os.environ, JUPYTER_RUNTIME_DIR=str(root/'jupyter/runtime'),
                       JUPYTER_CONFIG_DIR=str(root/'jupyter/config'), JUPYTER_DATA_DIR=str(root/'jupyter/data'),
                       IPYTHONDIR=str(root/'jupyter/ipython'))
    process = None
    try:
        process = subprocess.Popen([sys.executable, '-m', 'jupyterlab', '--config='+str(server_config)], env=environment)
        process.wait()
        if process.returncode:
            raise ValueError(f'Jupyter 启动或运行失败，退出码 {process.returncode}')
    except KeyboardInterrupt:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    finally:
        metadata.unlink(missing_ok=True)
        server_config.unlink(missing_ok=True)
        from wiserec_cli.webstudio.cache import ConnectionCache
        ConnectionCache.clear(root/'client/credentials.json')


def control(root, stop=False):
    import httpx
    metadata = root/'jupyter.json'
    if not metadata.exists():
        print('本地 Jupyter 未运行')
        return
    settings = json.loads(metadata.read_text())
    parts = urlsplit(settings['url'])
    if (parts.scheme != 'http' or parts.hostname != '127.0.0.1' or parts.path != '/demo/'
            or parts.username or parts.password or parts.query or parts.fragment):
        raise ValueError('本地 Jupyter 登记地址无效')
    try:
        with httpx.Client(trust_env=False, timeout=5, follow_redirects=False) as client:
            response = client.request('POST' if stop else 'GET',
                settings['url']+('api/shutdown' if stop else 'api/status'),
                headers={'Authorization': 'token '+settings['token']})
            response.raise_for_status()
    except httpx.HTTPError:
        raise ValueError('本地 Jupyter 无法连接或身份不匹配，未终止任何外部进程') from None
    print('已请求停止本地 Jupyter' if stop else '本地 Jupyter 运行中')
