"""ML_JUPYTER_AGENT_LIVE=1：启动独立临时服务，验证完整 CLI 链路。"""
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from wiserec_cli.business import BusinessStore, Department, Tenant
from wiserec_cli.jupyter.connection import Connection, JupyterClient, JupyterError

pytestmark = pytest.mark.skipif(os.environ.get('ML_JUPYTER_AGENT_LIVE') != '1',
                                reason='需显式启用临时本地 Jupyter 联调')


def test_agent_files_and_exec_roundtrip(tmp_path):
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    root = tmp_path / 'workspace'
    root.mkdir()
    token = secrets.token_urlsafe(24)
    server_config = tmp_path / 'server.json'
    server_config.write_text(json.dumps({'ServerApp': {
        'ip': '127.0.0.1', 'port': port, 'port_retries': 0, 'open_browser': False,
        'root_dir': str(root), 'base_url': '/user/agent/', 'log_level': 'ERROR'},
        'IdentityProvider': {'token': token}}))
    server_config.chmod(0o600)
    env = dict(os.environ)
    for name in ('JUPYTER_RUNTIME_DIR', 'JUPYTER_CONFIG_DIR', 'JUPYTER_DATA_DIR', 'IPYTHONDIR'):
        directory = tmp_path / name
        directory.mkdir()
        env[name] = str(directory)
    env['AGENT_TEST_TOKEN'] = token
    config = tmp_path / 'config.json'
    url = f'http://127.0.0.1:{port}/user/agent/'
    config.write_text(json.dumps({'current': 'agent', 'access_control': {'enable': False}, 'profiles': [{
        'name': 'agent', 'api_endpoint': url, 'jupyter': {'token_env': 'AGENT_TEST_TOKEN',
            'business_file': 'business.json', 'kernel': 'python3'}}]}))
    BusinessStore(tmp_path / 'business.json').refresh('agent', 'tester',
        [Department('d', 'D', (Tenant('agent-business', 'B', (), ()),))], browser_business_id='agent-business')

    def cli(*args, input=None, expected=0):
        completed = subprocess.run([sys.executable, '-m', 'wiserec_cli.cli', '--config', str(config),
            'jupyter', *args], input=input, capture_output=True, text=True, env=env, timeout=90)
        assert completed.returncode == expected, (completed.stdout, completed.stderr)
        assert token not in completed.stdout + completed.stderr
        return json.loads(completed.stdout)

    process = subprocess.Popen([sys.executable, '-m', 'jupyter_server', '--config=' + str(server_config)],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with JupyterClient(Connection(url, token, 'agent-business')) as client:
            deadline = time.monotonic() + 30
            while True:
                try:
                    client.request('GET', 'api/kernelspecs')
                    break
                except JupyterError:
                    if time.monotonic() > deadline or process.poll() is not None:
                        raise
                    time.sleep(.1)
            initial = client.request('GET', 'api/kernels')
            cli('files', 'mkdir', 'demo', '-o', 'json')
            code = 'import os, sys\nprint(os.getcwd())\nprint(sys.argv[1])\nprint("error-output", file=sys.stderr)\n'
            cli('files', 'write', 'demo/main.py', '--stdin', '-o', 'json', input=code)
            assert cli('files', 'read', 'demo/main.py', '-o', 'json')['result']['content'] == code
            assert cli('files', 'stat', 'demo/main.py', '-o', 'json')['result']['type'] == 'file'
            assert cli('files', 'list', 'demo', '-o', 'json')['result']['content'][0]['name'] == 'main.py'
            cli('files', 'write', 'demo/main.py', '--stdin', '-o', 'json', input='wrong', expected=1)
            run = cli('exec', '--cwd', 'demo', '-o', 'json', '--', sys.executable, 'main.py', 'a b; $(echo nope)')['result']
            assert run['status'] == 'SUCCEEDED', run
            assert str(root / 'demo') in run['stdout']
            assert 'a b; $(echo nope)' in run['stdout']
            assert run['stderr'] == 'error-output\n'
            assert not run['cleanup_errors']
            run = cli('exec', '-o', 'json', '--', sys.executable, '-c', 'raise SystemExit(7)', expected=7)['result']
            assert run['exit_code'] == 7
            run = cli('exec', '--timeout', '.2', '-o', 'json', '--', sys.executable,
                      '-u', '-c', 'import time; print("started"); time.sleep(30)', expected=124)['result']
            assert run['status'] == 'TIMED_OUT' and run['stdout'] == 'started\n'
            assert not run['cleanup_errors']
            data = tmp_path / 'binary.bin'
            data.write_bytes(bytes(range(256)))
            cli('files', 'upload', str(data), 'demo/binary.bin', '-o', 'json')
            dest = tmp_path / 'download.bin'
            cli('files', 'download', 'demo/binary.bin', str(dest), '-o', 'json')
            assert dest.read_bytes() == data.read_bytes()
            copied = cli('files', 'copy', 'demo/binary.bin', 'demo', '-o', 'json')['result']['path']
            cli('files', 'move', copied, 'demo/moved.bin', '-o', 'json')
            cli('files', 'delete', 'demo/moved.bin', '-o', 'json')
            cli('files', 'delete', 'demo', '-o', 'json', expected=1)
            assert client.request('GET', 'api/kernels') == initial
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
