"""Real local HTTP, WebSocket and kernel execution through the demo entry."""
import json
import os
import signal
import socket
import subprocess
import sys
import time

import httpx
import nbformat
from test_demo import invoke
from helpers import initialize
from wiserec_cli_mock.seeds import uid


def test_demo_jupyter_roundtrip(tmp_path):
    root = initialize(tmp_path/'demo')
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen([sys.executable, '-m', 'wiserec_cli_mock.manage', '--workspace', str(root),
        'jupyter', '--port', str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic()+30
        while True:
            try:
                connection = json.loads((root/'jupyter.json').read_text())
                with httpx.Client(trust_env=False) as client:
                    response = client.get(connection['url']+'api/kernelspecs',
                        headers={'Authorization': 'token '+connection['token']})
                    if response.status_code == 200:
                        break
            except (OSError, ValueError, httpx.HTTPError):
                pass
            assert process.poll() is None and time.monotonic() < deadline
            time.sleep(.1)
        control = [sys.executable, '-m', 'wiserec_cli_mock.manage', '--workspace', str(root)]
        assert subprocess.run(control+['jupyter-status'], capture_output=True).returncode == 0
        invoke(root, 'login')
        invoke(root, 'webstudio', 'start', uid('studio'))
        invoke(root, 'webstudio', 'login', uid('studio'))
        invoke(root, 'webstudio', 'show')
        invoke(root, 'jupyter', 'doctor')
        invoke(root, 'jupyter', 'files', 'mkdir', 'roundtrip')
        local = root/'samples/hello.txt'
        local.write_text('hello real execution')
        invoke(root, 'jupyter', 'files', 'upload', local, 'roundtrip/hello.txt')
        assert 'hello real execution' in invoke(root, 'jupyter', 'files', 'read', 'roundtrip/hello.txt').stdout
        output = root/'exports/downloaded.txt'
        invoke(root, 'jupyter', 'files', 'download', 'roundtrip/hello.txt', output)
        assert output.read_bytes() == local.read_bytes()
        notebook = root/'samples/run.ipynb'
        nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("print('DEMO_KERNEL_OK')")]), notebook)
        result = invoke(root, 'jupyter', 'notebook', 'run', notebook, '--download', root/'exports/notebook', '-o', 'json')
        summary = json.loads(result.stdout)
        assert summary['status'] == 'SUCCEEDED'
        saved = nbformat.read(summary['notebook'], as_version=4)
        assert 'DEMO_KERNEL_OK' in saved.cells[0].outputs[0]['text']
        result = invoke(root, 'jupyter', 'exec', '--', 'python', '-c', "print('DEMO_EXEC_OK')")
        assert 'DEMO_EXEC_OK' in result.stdout+result.stderr
        invoke(root, 'webstudio', 'stop', uid('studio'))
        invoke(root, 'jupyter', 'doctor', success=False)
        assert connection['token'] not in result.stdout+result.stderr
        assert subprocess.run(control+['jupyter-stop'], capture_output=True).returncode == 0
        assert process.wait(timeout=15) == 0
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=15)
    assert not (root/'jupyter.json').exists()
