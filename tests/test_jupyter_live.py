"""显式指定专用开发服务后运行；默认测试套件不连接外部服务。"""
import json
import os
import select
import shlex
import subprocess
import sys
import time
from pathlib import Path

import nbformat
import pytest
import websocket

from wiserec_cli.jupyter.connection import Connection, JupyterClient, JupyterError, from_runtime
from wiserec_cli.runtime import Runtime

CONFIG = os.environ.get("ML_JUPYTER_TEST_CONFIG")
pytestmark = pytest.mark.skipif(not CONFIG, reason="需要 ML_JUPYTER_TEST_CONFIG 指向专用开发服务")


@pytest.fixture
def client():
    connection = from_runtime(Runtime(config_path=Path(CONFIG)))
    with JupyterClient(connection) as instance:
        yield instance


def run_cli(*args, timeout=60):
    return subprocess.run([sys.executable, "-m", "wiserec_cli.cli", "--config", CONFIG,
                           "jupyter", *args], capture_output=True, text=True, timeout=timeout)


@pytest.mark.parametrize("kind", ["success", "error", "timeout", "stdin"])
def test_notebook_real_kernel(tmp_path, client, kind):
    code = {"success": "from IPython.display import display, HTML\nprint('LIVE_OK')\ndisplay(HTML('<b>rich</b>'))\n21 * 2",
            "error": "print('BEFORE_ERROR')\nraise ValueError('expected failure')",
            "timeout": "print('BEFORE_TIMEOUT', flush=True)\nimport time\ntime.sleep(20)",
            "stdin": "input('not allowed')"}[kind]
    source = tmp_path / "input.ipynb"
    notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell(code), nbformat.v4.new_code_cell("print('SECOND_CELL')")])
    nbformat.write(notebook, source)
    before = source.read_bytes()
    existing = {item["id"] for item in client.request("GET", "api/kernels")}
    result = run_cli("notebook", "run", str(source), "--download", str(tmp_path / "out"),
                     "--timeout", "1" if kind == "timeout" else "15", "--output", "json")
    summary = json.loads(result.stdout)
    expected = {"success": (0, "SUCCEEDED"), "error": (1, "FAILED"),
                "timeout": (124, "TIMED_OUT"), "stdin": (1, "FAILED")}[kind]
    assert (result.returncode, summary["status"]) == expected, (result.stdout, result.stderr)
    assert source.read_bytes() == before
    assert not summary["cleanup_errors"], summary
    saved = nbformat.read(summary["notebook"], as_version=4)
    nbformat.validate(saved)
    assert saved.cells[0].outputs
    if kind == "success":
        assert any("text/html" in out.get("data", {}) for out in saved.cells[0].outputs)
        assert "SECOND_CELL" in result.stderr
    else:
        assert saved.cells[1].execution_count is None
    assert {item["id"] for item in client.request("GET", "api/kernels")} == existing
    remote = client.request("GET", client.contents(summary["remote_directory"] + "/executed.ipynb"))
    assert remote["type"] == "notebook"


def receive_until(socket, marker, timeout=10):
    output = ""
    deadline = time.monotonic() + timeout
    socket.settimeout(0.3)
    while time.monotonic() < deadline:
        try:
            raw = socket.recv()
        except websocket.WebSocketTimeoutException:
            continue
        assert raw, "terminal closed unexpectedly"
        message = json.loads(raw)
        if message[0] == "stdout":
            output += message[1]
        if marker in output:
            return output
    pytest.fail("Terminal 未收到预期输出: " + repr(output))


def test_terminal_create_execute_reconnect_close(client):
    name = client.request("POST", "api/terminals", {})["name"]
    try:
        socket = client.socket("terminals/websocket/" + name)
        socket.send(json.dumps(["set_size", 31, 97, 0, 0]))
        socket.send(json.dumps(["stdin", "printf 'LIVE_%s\\n' 'TERMINAL'; export ML_TEST_STATE=alive\n"]))
        receive_until(socket, "LIVE_TERMINAL")
        socket.close()
        assert name in [item["name"] for item in client.request("GET", "api/terminals")]
        socket = client.socket("terminals/websocket/" + name)
        socket.send(json.dumps(["stdin", "printf 'STATE:%s\\n' \"$ML_TEST_STATE\"; stty size\n"]))
        text = receive_until(socket, "31 97")
        assert "STATE:alive" in text
        script = "import time; print('SLEEP_' + 'START', flush=True); time.sleep(30)"
        socket.send(json.dumps(["stdin", shlex.quote(sys.executable) + " -u -c " + shlex.quote(script) + "\n"]))
        receive_until(socket, "SLEEP_START")
        socket.send(json.dumps(["stdin", "\u0003"]))
        receive_until(socket, "KeyboardInterrupt")
        socket.send(json.dumps(["stdin", "printf 'INTERRUPT_%s\\n' 'OK'\n"]))
        receive_until(socket, "INTERRUPT_OK")
        socket.close()
    finally:
        client.request("DELETE", "api/terminals/" + name)
    assert name not in [item["name"] for item in client.request("GET", "api/terminals")]


def test_bad_token_rejected(client):
    config = client.connection
    with JupyterClient(Connection(config.url, "incorrect-token", config.business_id)) as wrong:
        with pytest.raises(JupyterError, match="认证"):
            wrong.request("GET", "api/kernelspecs")


def test_real_server_with_url_prefix(tmp_path):
    """真实 /user/name/ 路由，验证 HTTP、Kernel WS 和 Terminal WS 均保留前缀。"""
    import socket as sockets
    from wiserec_cli.jupyter.notebook import run_notebook
    import secrets
    with sockets.socket() as port_socket:
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
    token = secrets.token_urlsafe(24)
    root = tmp_path / "workspace"
    root.mkdir()
    server_config = tmp_path / "server.json"
    server_config.write_text(json.dumps({"ServerApp": {
        "ip": "127.0.0.1", "port": port, "port_retries": 0, "open_browser": False,
        "root_dir": str(root), "base_url": "/user/local/", "log_level": "ERROR"},
        "IdentityProvider": {"token": token}}))
    server_config.chmod(0o600)
    env = dict(os.environ)
    for name in ["JUPYTER_RUNTIME_DIR", "JUPYTER_CONFIG_DIR", "JUPYTER_DATA_DIR", "IPYTHONDIR"]:
        target = tmp_path / name
        target.mkdir()
        env[name] = str(target)
    process = subprocess.Popen([sys.executable, "-m", "jupyter_server", "--config=" + str(server_config)],
                               env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        with JupyterClient(Connection(f"http://127.0.0.1:{port}/user/local/", token, "prefix-test")) as prefixed:
            deadline = time.monotonic() + 20
            while True:
                try:
                    prefixed.request("GET", "api/kernelspecs")
                    break
                except JupyterError:
                    if time.monotonic() > deadline or process.poll() is not None:
                        raise
                    time.sleep(0.1)
            source = tmp_path / "prefix.ipynb"
            nbformat.write(nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("print('PREFIX_OK')")]), source)
            result = run_notebook(prefixed, source, tmp_path / "results", emit=lambda _: None)
            assert result["status"] == "SUCCEEDED", result
            assert not result["cleanup_errors"]
            name = prefixed.request("POST", "api/terminals", {})["name"]
            try:
                socket = prefixed.socket("terminals/websocket/" + name)
                socket.send(json.dumps(["stdin", "printf 'PREFIX_%s\\n' 'TERMINAL'\n"]))
                receive_until(socket, "PREFIX_TERMINAL")
                socket.close()
            finally:
                prefixed.request("DELETE", "api/terminals/" + name)
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


@pytest.mark.skipif(os.name == "nt", reason="POSIX PTY 验证")
@pytest.mark.parametrize("attempt", range(3))
def test_cli_terminal_real_tty_detach(client, attempt):
    import pty
    name = client.request("POST", "api/terminals", {})["name"]
    master, slave = pty.openpty()
    process = subprocess.Popen([sys.executable, "-m", "wiserec_cli.cli", "--config", CONFIG,
                                "jupyter", "terminal", "attach", name], stdin=slave, stdout=slave, stderr=slave)
    os.close(slave)
    collected = b""
    try:
        deadline = time.monotonic() + 15
        sent = False
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.2)[0]:
                collected += os.read(master, 4096)
            if not sent and "按 Ctrl+]".encode() in collected:
                # 等待 WebSocket 与 raw mode 建立；输入仍可由 TTY 缓冲。
                time.sleep(0.5)
                os.write(master, b"printf 'TTY_%s\\n' 'OK'\n")
                sent = True
            if b"TTY_OK" in collected:
                os.write(master, b"\x1d")
                break
        assert b"TTY_OK" in collected, collected
        # 模拟终端模拟器持续读取输出；macOS TCSADRAIN 会等待 PTY 输出被读取。
        deadline = time.monotonic() + 5
        while process.poll() is None and time.monotonic() < deadline:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    collected += os.read(master, 4096)
                except OSError:
                    break
        assert process.wait(timeout=1) == 0, collected
        assert name in [item["name"] for item in client.request("GET", "api/terminals")]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        client.request("DELETE", "api/terminals/" + name)
