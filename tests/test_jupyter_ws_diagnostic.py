"""诊断脚本复用真实连接路径，但不触碰远程资源或泄漏凭据。"""
import importlib.util
import json
from pathlib import Path
import socket
import ssl
from unittest.mock import patch

import httpx
import pytest
import websocket

from wiserec_cli.jupyter.connection import Connection, JupyterClient, JupyterError


spec = importlib.util.spec_from_file_location(
    "diagnose_jupyter_ws", Path(__file__).parents[1] / "scripts/diagnose_jupyter_ws.py"
)
diagnostic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(diagnostic)


def run_probe(failure=None, terminal="1"):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=[{"name": "1"}], headers={
            "set-cookie": "session=PRIVATE_COOKIE; Path=/base/; Secure"
        })

    connection = Connection("https://host/base/", "PRIVATE_TOKEN", "selected-business")
    with JupyterClient(connection, transport=httpx.MockTransport(handler)) as client:
        with patch("wiserec_cli.jupyter.connection.JupyterClient", return_value=client), patch(
            "wiserec_cli.jupyter.connection.websocket.create_connection"
        ) as create:
            create.return_value.getstatus.return_value = 101
            create.side_effect = failure
            report = diagnostic.probe(connection, terminal)
    return report, requests, create


def test_success_uses_existing_terminal_and_same_headers_without_shell_input():
    report, requests, create = run_probe()
    assert report["ok"] is True
    assert [(r.method, r.url.path) for r in requests] == [("GET", "/base/api/terminals")]
    assert requests[0].headers["businessid"] == "selected-business"
    assert create.call_args.args[0] == "wss://host/base/terminals/websocket/1"
    assert create.call_args.kwargs["header"]["businessid"] == "selected-business"
    assert "PRIVATE_COOKIE" in create.call_args.kwargs["cookie"]
    create.return_value.close.assert_called_once_with(timeout=1)
    create.return_value.send.assert_not_called()
    payload = json.dumps(report)
    assert "PRIVATE_TOKEN" not in payload
    assert "PRIVATE_COOKIE" not in payload


@pytest.mark.parametrize("terminal", [None, "missing"])
def test_no_terminal_does_not_create_or_connect(terminal):
    report, requests, create = run_probe(terminal=terminal)
    assert report["ok"] is False
    assert len(requests) == 1
    assert requests[0].method == "GET"
    create.assert_not_called()


@pytest.mark.parametrize("failure,expected", [
    (ssl.SSLCertVerificationError(1, "PRIVATE_TOKEN"), "SSLCertVerificationError"),
    (socket.gaierror(-2, "PRIVATE_TOKEN"), "gaierror"),
    (TimeoutError("PRIVATE_TOKEN"), "TimeoutError"),
    (ConnectionResetError(104, "PRIVATE_TOKEN"), "ConnectionResetError"),
])
def test_generic_cli_wrapper_preserves_safe_underlying_error(failure, expected):
    report, _, _ = run_probe(failure)
    assert report["ok"] is False
    step = report["steps"][-1]
    assert step["stage"] == "WebSocket handshake"
    assert [item["type"] for item in step["exception_chain"]] == ["JupyterError", expected]
    assert step["hints"]
    assert "PRIVATE_TOKEN" not in json.dumps(report)


def test_rejected_handshake_keeps_status_not_response_secrets():
    failure = websocket.WebSocketBadStatusException(
        "PRIVATE_TOKEN", 403, resp_headers={"set-cookie": "PRIVATE_COOKIE"},
        resp_body="PRIVATE_RESPONSE_BODY"
    )
    report, _, _ = run_probe(failure)
    assert report["steps"][-1]["exception_chain"][-1]["status_code"] == 403
    assert "PRIVATE_" not in json.dumps(report)


def test_safe_url_removes_credentials_query_fragment_and_known_path_secret():
    result = diagnostic.safe_url(
        "wss://user:password@[::1]:8443/base/PRIVATE_TOKEN?token=secret#fragment", ("PRIVATE_TOKEN",)
    )
    assert result == "wss://[::1]:8443/base/[REDACTED]"


def test_main_writes_safe_report_on_discovery_failure(tmp_path, capsys, monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setenv("HTTPS_PROXY", "http://user:PRIVATE_PROXY_PASSWORD@proxy:8888")
    output = tmp_path / "report.json"
    runtime = SimpleNamespace(config=SimpleNamespace(current_name="explore"))
    with patch("wiserec_cli.runtime.Runtime", return_value=runtime), patch(
        "wiserec_cli.jupyter.connection.from_runtime", side_effect=JupyterError("PRIVATE_TOKEN")
    ):
        assert diagnostic.main(["--output", str(output)]) == 1
    assert runtime.invocation_command == "ml jupyter terminal list"
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["steps"][0]["stage"] == "认证与解析连接"
    assert "HTTPS_PROXY" in report["environment_variables_present"]
    assert "PRIVATE_" not in output.read_text(encoding="utf-8")
    assert "PRIVATE_" not in capsys.readouterr().out
    with pytest.raises(SystemExit):
        diagnostic.main(["--output", str(output)])
