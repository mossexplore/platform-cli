import json
import struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import nbformat
import pytest
from typer.testing import CliRunner

from wiserec_cli.business import BusinessStore, Department, Tenant
from wiserec_cli.cli import app
from wiserec_cli.config import ConfigManager
from wiserec_cli.jupyter.connection import Connection, JupyterClient, JupyterError, from_runtime, remote_path
from wiserec_cli.jupyter.notebook import run_notebook
from wiserec_cli.jupyter.protocol import KernelChannel, Outputs, decode_message, execute_cell
from wiserec_cli.commands.jupyter import display_time


def runtime(tmp_path):
    config = tmp_path / "config.json"
    (tmp_path / "token").write_text("secret-value")
    config.write_text(json.dumps({"current": "local", "profiles": [
        {"name": "other", "api_endpoint": "http://other/"},
        {"name": "local", "api_endpoint": "http://127.0.0.1:8888/user/local/",
         "jupyter": {"token_env": "TEST_JUPYTER_TOKEN", "token_file": "token", "business_file": "business.json"}}]}))
    business = BusinessStore(tmp_path / "business.json")
    for env in ("local", "other"):
        business.refresh(env, "user", [Department("department", "D", (Tenant(env + "-business", "B", (), ()),))],
                         browser_business_id=env + "-business")
    return SimpleNamespace(config=ConfigManager(config), business=business)


def test_current_environment_business_and_no_token_repr(tmp_path):
    config = from_runtime(runtime(tmp_path))
    assert config.business_id == "local-business"
    assert config.url.endswith("/user/local/")
    assert "secret-value" not in repr(config)


def test_mismatched_selected_id_is_rejected(tmp_path):
    rt = runtime(tmp_path)
    data = json.loads(rt.business.path.read_text())
    data["profiles"]["local"]["selected"]["businessId"] = "other-business"
    rt.business.path.write_text(json.dumps(data))
    with pytest.raises(JupyterError, match="businessId"):
        from_runtime(rt)


def test_missing_current_business_never_falls_back(tmp_path):
    rt = runtime(tmp_path)
    data = json.loads(rt.business.path.read_text())
    del data["profiles"]["local"]
    rt.business.path.write_text(json.dumps(data))
    with pytest.raises(Exception, match="当前环境"):
        from_runtime(rt)


def test_http_path_headers_and_no_redirect():
    seen = []
    def handler(req):
        seen.append(req)
        return httpx.Response(302, headers={"location": "https://untrusted/"})
    with JupyterClient(Connection("http://localhost/base/", "secret", "business"),
                       transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(JupyterError):
            client.request("POST", "api/kernels", {})
    assert len(seen) == 1
    assert str(seen[0].url) == "http://localhost/base/api/kernels"
    assert seen[0].headers["businessid"] == "business"
    assert seen[0].headers["authorization"] == "token secret"


def test_websocket_headers_prefix_and_no_redirect():
    with patch("wiserec_cli.jupyter.connection.websocket.create_connection") as create:
        create.return_value.getstatus.return_value = 101
        with JupyterClient(Connection("https://host/user/a/", "secret", "business")) as client:
            client.socket("api/kernels/id/channels")
    args, kwargs = create.call_args
    assert args[0] == "wss://host/user/a/api/kernels/id/channels"
    assert kwargs["header"]["businessid"] == "business"
    assert kwargs["redirect_limit"] == 0


def test_websocket_redirect_is_rejected():
    with patch("wiserec_cli.jupyter.connection.websocket.create_connection") as create:
        create.return_value.getstatus.return_value = 302
        with JupyterClient(Connection("https://host/", "secret", "business")) as client:
            with pytest.raises(JupyterError):
                client.socket("api/kernels/id/channels")
        create.return_value.close.assert_called_once()


@pytest.mark.parametrize("value", ["../file", "/etc/passwd", "x/../../a", "x\\y"])
def test_invalid_remote_paths(value):
    with pytest.raises(JupyterError):
        remote_path(value)


def message(kind, content, channel="iopub"):
    return {"header": {"msg_type": kind}, "content": content, "channel": channel}


def test_cell_requires_reply_and_idle_and_collects_output_after_reply():
    cell = nbformat.v4.new_code_cell("print(1)")
    channel = Mock()
    channel.messages.return_value = iter([
        message("execute_reply", {"status": "ok", "execution_count": 1}, "shell"),
        message("stream", {"name": "stdout", "text": "1\n"}),
        message("status", {"execution_state": "idle"}),
    ])
    execute_cell(channel, cell, Outputs(lambda _: None), 100)
    assert cell.outputs[0].text == "1\n"
    assert cell.execution_count == 1
    assert channel.send.call_args.args[1]["allow_stdin"] is False


def test_display_updates_and_clear():
    first = nbformat.v4.new_code_cell("a")
    second = nbformat.v4.new_code_cell("b")
    outputs = Outputs(lambda _: None)
    outputs.accept(first, message("display_data", {"data": {"text/plain": "old"}, "transient": {"display_id": "d"}}))
    outputs.accept(second, message("update_display_data", {"data": {"text/plain": "new"}, "transient": {"display_id": "d"}}))
    assert first.outputs[0].data["text/plain"] == "new"
    outputs.accept(first, message("clear_output", {"wait": True}))
    assert len(first.outputs) == 1
    outputs.accept(first, message("stream", {"name": "stdout", "text": "replacement"}))
    assert len(first.outputs) == 1
    assert first.outputs[0].text == "replacement"


def test_binary_messages_and_unrelated_messages():
    msg = {"parent_header": {"msg_id": "target"}, "content": {"x": 1}}
    raw = json.dumps(msg).encode()
    assert decode_message(struct.pack("!II", 1, 8) + raw) == msg
    sock = Mock()
    sock.recv.side_effect = [json.dumps({"parent_header": {"msg_id": "other"}}), json.dumps(msg)]
    import time
    assert next(KernelChannel(sock).messages("target", time.monotonic() + 2)) == msg


@pytest.mark.parametrize("failure,status", [(JupyterError("failure"), "FAILED"),
    (TimeoutError(), "TIMED_OUT"), (KeyboardInterrupt(), "INTERRUPTED"),
    (JupyterError("连接中断，执行结果待确认"), "LOST")])
def test_partial_result_and_kernel_cleanup(tmp_path, failure, status):
    source = tmp_path / "input.ipynb"
    nb = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("x"), nbformat.v4.new_code_cell("y")])
    nbformat.write(nb, source)
    original = source.read_bytes()
    client = Mock()
    client.connection.kernel = "python3"
    client.request.return_value = {"id": "owned-kernel"}
    def execute(channel, cell, outputs, deadline):
        cell.outputs.append(nbformat.v4.new_output("stream", name="stdout", text="partial"))
        raise failure
    with patch("wiserec_cli.jupyter.notebook.KernelChannel"), patch("wiserec_cli.jupyter.notebook.execute_cell", side_effect=execute):
        result = run_notebook(client, source, tmp_path / "results", emit=lambda _: None)
    saved = nbformat.read(result["notebook"], as_version=4)
    assert result["status"] == status
    assert saved.cells[0].outputs[0].text == "partial"
    assert saved.cells[1].execution_count is None
    assert source.read_bytes() == original
    client.request.assert_any_call("DELETE", "api/kernels/owned-kernel")


def test_terminal_open_without_tty_creates_no_resource(tmp_path):
    rt = runtime(tmp_path)
    with patch("wiserec_cli.commands.jupyter.client_for") as client:
        result = CliRunner().invoke(app, ["--config", str(rt.config.path), "jupyter", "terminal", "open"])
    assert result.exit_code != 0
    assert "真实终端" in result.output
    client.assert_not_called()


def test_beijing_timestamp():
    assert display_time("2026-09-08T06:54:36.000+00:00") == "2026-09-08 14:54:36"
