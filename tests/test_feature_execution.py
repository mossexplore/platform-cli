import io
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest
from rich.console import Console
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.business import BusinessSelection
from wiserec_cli.client import PlatformClient
from wiserec_cli.models import Profile, Credentials
from wiserec_cli.errors import ApiError, BusinessError
from wiserec_cli.services.feature_execution import FeatureExecutionService
from wiserec_cli.commands.feature_execution import display_value, render_page

ITEM = {"jobId": "4a395a88-86d8-478e-9659-05f17b89be78", "algorithmName": "algorithm",
        "runningTime": 93, "fileSize": 276007, "latestFlag": True,
        "checkTime": 1792458601000, "createTime": 1792452900000,
        "statusTime": 1792458523000, "extra": [1]}


class Client:
    business_id = "chosen"

    def __init__(self, payload=None):
        self.payload = payload if payload is not None else {"result": {
            "code": 0, "des": "query execution record success", "jobs": [ITEM], "count": 1}}
        self.calls = []

    def request(self, method, path, json_body):
        self.calls.append((method, path, json_body))
        return self.payload


@pytest.mark.parametrize("include", [False, True])
def test_list_request(include):
    client = Client()
    result = FeatureExecutionService(client).list_executions(" task ", 2, 20, include)
    assert client.calls == [("POST", "/ai/backend/dpp/featuretask/queryScheduleTaskList",
        {"pageIndex": 2, "pageSize": 20, "taskId": "task", "source": "history", "latestFlag": "all" if include else "true"})]
    assert result == {"items": [ITEM], "count": 1, "pageIndex": 2, "pageSize": 20}


def test_log_defaults_optional_fields_and_unique_uuid():
    client = Client()
    service = FeatureExecutionService(client)
    assert service.search_logs("job") == client.payload
    body = client.calls[-1][2]
    assert body["data"] == {"jobId": "job", "businessId": "chosen", "searchStartLine": 1, "searchEndLine": 2000}
    assert body["version"] == "1.0"
    assert UUID(body["meta"]["uuid"]).version == 4
    for scope in "ABC":
        service.search_logs("job", 2001, 4000, ["123", " ERROR "], scope, 20)
        other = client.calls[-1][2]
        assert other["meta"]["uuid"] != body["meta"]["uuid"]
        assert other["data"] == {"jobId": "job", "businessId": "chosen", "searchStartLine": 2001,
            "searchEndLine": 4000, "keywords": ["123", " ERROR "], "searchScope": scope, "searchScopeLine": 20}
    service.search_logs("job", scope="A")
    assert "keywords" not in client.calls[-1][2]["data"]
    assert "searchScopeLine" not in client.calls[-1][2]["data"]


@pytest.mark.parametrize("kind", ["list", "logs"])
def test_actual_request_uses_selected_business_header(kind):
    def handler(request):
        assert request.headers.get_list("businessid") == ["selected"]
        body = json.loads(request.content)
        assert str(request.url).startswith("https://dev.example.com/ai/backend/")
        if kind == "logs":
            assert body["data"]["businessId"] == "selected"
        else:
            assert "businessId" not in body
        return httpx.Response(200, json=Client().payload)
    selection = BusinessSelection(type="team", department_id="d", department_name="D", tenant_id="t",
        tenant_name="T", team_id="team", team_name="Team", business_id="selected")
    with PlatformClient(Profile("dev", "https://dev.example.com/dashboard"),
        Credentials.create("dev", "session=a", "csrf", "jack", 1800), 30000, 0, True,
        transport=httpx.MockTransport(handler), business_selection=selection) as client:
        service = FeatureExecutionService(client)
        service.search_logs("job") if kind == "logs" else service.list_executions("task")


@pytest.mark.parametrize("kwargs", [{"job_id": " "}, {"start_line": 0}, {"end_line": 0},
    {"start_line": 3, "end_line": 2}, {"keywords": [" "]}, {"scope": "D"}, {"scope_lines": 0}])
def test_invalid_logs_no_request(kwargs):
    client = Client()
    with pytest.raises(ValueError):
        FeatureExecutionService(client).search_logs(**dict({"job_id": "job"}, **kwargs))
    assert not client.calls


@pytest.mark.parametrize("kind", ["list", "logs"])
def test_missing_business_and_bad_response(kind):
    client = Client()
    service = FeatureExecutionService(client)
    call = lambda: service.search_logs("job") if kind == "logs" else service.list_executions("task")
    client.business_id = ""
    with pytest.raises(BusinessError):
        call()
    assert not client.calls
    client.business_id = "chosen"
    for payload in ({}, {"result": []}, {"result": {"code": False}}, {"result": {"code": 2, "des": "denied"}}):
        client.payload = payload
        with pytest.raises(ApiError):
            call()


@pytest.mark.parametrize("result", [{"code": 0}, {"code": 0, "jobs": [None], "count": 1},
    {"code": 0, "jobs": [], "count": False}, {"code": 0, "jobs": [], "count": -1}])
def test_bad_page(result):
    with pytest.raises(ApiError):
        FeatureExecutionService(Client({"result": result})).list_executions("task")


def invoke(client, args):
    def authenticated(operation):
        print("刷新认证")
        return operation(client)
    runtime = SimpleNamespace(authenticated_call=authenticated,
        config=SimpleNamespace(current_profile=lambda: SimpleNamespace(output_format="table")))
    with patch("wiserec_cli.cli.Runtime", return_value=runtime), patch(
        "wiserec_cli.commands.feature_execution.runtime_from_context", return_value=runtime):
        return CliRunner().invoke(app, ["feature-task", "execution", *args])


def test_cli_list_and_logs_json():
    client = Client()
    result = invoke(client, ["list", "task", "--page", "2", "--page-size", "20", "--include-history", "-o", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["items"] == [ITEM]
    assert "刷新认证" in result.stderr
    assert client.calls[-1][2]["latestFlag"] == "all"
    # Unknown response fields must survive until the actual log schema is supplied.
    client.payload = {"version": "1.0", "result": {"code": 0, "opaque": {"lines": ["a\nb"]}}}
    result = invoke(client, ["logs", "search", "job", "--keyword", "ERROR", "--keyword", "123", "--scope", "C", "--scope-lines", "20", "-o", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == client.payload
    assert client.calls[-1][2]["data"]["keywords"] == ["ERROR", "123"]


@pytest.mark.parametrize("args", [["list", " "], ["list", "task", "--page", "0"],
    ["logs", "search", "job", "--scope", "D"], ["logs", "search", "job", "--start-line", "2001"],
    ["logs", "search", "job", "--keyword", " "], ["logs", "search", "job", "-o", "yaml"]])
def test_cli_invalid_no_request(args):
    client = Client()
    assert invoke(client, args).exit_code != 0
    assert not client.calls


def test_formatting_and_complete_id():
    for field, expected in {"runningTime": "1h33min", "fileSize": "269.54K", "latestFlag": "是",
        "checkTime": "2026-10-20 09:10:01", "createTime": "2026-10-20 07:35:00", "statusTime": "2026-10-20 09:08:43"}.items():
        assert display_value(field, ITEM[field]) == expected
    for value, expected in [(0, "0min"), (35, "35min"), (120, "2h0min")]:
        assert display_value("runningTime", value) == expected
    assert display_value("latestFlag", False) == "否"
    assert display_value("gpuSize", 0) == "0"
    assert display_value("fileSize", 0) == "0B"
    assert display_value("fileSize", 1024 ** 2) == "1.00M"
    assert display_value("fileSize", 1024 ** 3) == "1.00G"
    assert display_value("statusTime", None) == "-"
    for width in (80, 260):
        out = io.StringIO()
        with patch("wiserec_cli.commands.feature_execution.console", Console(file=out, width=width)):
            render_page({"items": [ITEM], "count": 1, "pageIndex": 1, "pageSize": 10}, "task", "table")
        assert ITEM["jobId"] in out.getvalue()
    result = invoke(Client({"result": {"code": 0, "jobs": [], "count": 0}}), ["list", "task"])
    assert result.exit_code == 0
    assert "暂无执行记录" in result.stdout


@pytest.mark.parametrize("text", [
    "     1\t{'3tower_filip_1': 128} %%%%%%%%%%%%%%%%%\n     2\t/opt/abc/doc.json !!!&&&\n",
    "[red]literal[/red]\n中文日志\t  indented\n\n",
    "a" * 500 + "\nno trailing newline",
    "line1\r\nline2\r\n",
    "",
])
def test_logs_text_preserves_exact_content(text):
    payload = {"result": {"code": 0, "des": "get log success", "logs": [
        {"podName": "pod", "log": text, "status": 0},
        {"podName": "other", "log": "must not be concatenated", "status": 0},
    ], "totalLineNum": 1}}
    for options in ([], ["-o", "text"]):
        result = invoke(Client(payload), ["logs", "search", "job", *options])
        assert result.exit_code == 0, result.output
        # Bytes avoid Click's newline normalization in the stdout property.
        assert result.stdout_bytes == text.encode("utf-8")
        assert "刷新认证" in result.stderr
    result = invoke(Client(payload), ["logs", "search", "job", "-o", "json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout) == payload


def test_empty_logs_and_malformed_text_response():
    result = invoke(Client({"result": {"code": 0, "logs": [], "totalLineNum": 0}}),
                    ["logs", "search", "job"])
    assert result.exit_code == 0
    assert result.stdout == ""
    for logs in (None, {}, [None], [{}], [{"log": None}], [{"log": 123}]):
        result = invoke(Client({"result": {"code": 0, "logs": logs}}),
                        ["logs", "search", "job"])
        assert result.exit_code == 1
        assert result.stdout == ""
        assert "日志响应缺少有效的" in result.stderr
