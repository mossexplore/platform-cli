import io
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest
from rich.console import Console
from rich.table import Table
from typer.testing import CliRunner

from wiserec_cli.business import BusinessSelection
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.commands.sample_execution import display_value, render_page
from wiserec_cli.errors import ApiError, BusinessError
from wiserec_cli.models import Credentials, Profile
from wiserec_cli.services.sample_execution import SampleExecutionService, parse_time

ITEM = {"jobId": "d8296624-c742-4d54-a504-9e2c6c839c23", "algorithmName": "FeatureFlow",
        "status": "COMPLETED", "fileSize": 183835, "periodDate": "20261017-000000",
        "runningTime": 232, "latestFlag": True, "checkTime": 1792530453000,
        "createTime": 1792514090000, "statusTime": 1792528056000, "extra": None}


class Client:
    business_id = "chosen"

    def __init__(self, field="instances", payload=None):
        self.payload = payload if payload is not None else {"result": {"code": 0, "count": 1, field: [ITEM]}}
        self.calls = []

    def request(self, method, path, json_body):
        self.calls.append((method, path, json_body))
        return self.payload


@pytest.mark.parametrize("periods", [True, False])
@pytest.mark.parametrize("filtered", [True, False])
def test_http_contract(periods, filtered):
    field = "instances" if periods else "jobs"
    expected = {"taskId": "task", "pageIndex": 2 if filtered else 1,
                "pageSize": 30 if filtered else (20 if periods else 10)}
    if periods:
        expected.update(businessId="chosen", latestFlag=True, sortField="periodDate", taskClass=3)
        if filtered:
            expected.update(periodStartTime=1790784000000, periodEndTime=1790870400000, states=["COMPLETED", "FAILED"])
        path = "/ai/backend/dpp/proxy/schedule-service/task/instances/query"
    else:
        expected.update(source="history", latestFlag="all" if filtered else "true")
        path = "/ai/backend/dpp/featuretask/queryScheduleTaskList"

    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == "https://dev.example.com" + path
        assert request.headers.get_list("businessid") == ["chosen"]
        body = json.loads(request.content)
        if periods:
            assert body["version"] == "1.0"
            assert UUID(body["meta"]["uuid"]).version == 4
            body = body["data"]
        assert body == expected
        return httpx.Response(200, json={"result": {"code": 0, field: [ITEM], "count": 375}})

    selection = BusinessSelection(type="team", department_id="d", department_name="D",
        tenant_id="t", tenant_name="T", team_id="team", team_name="Team", business_id="chosen")
    with PlatformClient(Profile("dev", "https://dev.example.com/dashboard"),
        Credentials.create("dev", "session=a", "csrf", "jack", 1800), 30000, 0, True,
        transport=httpx.MockTransport(handler), business_selection=selection) as client:
        service = SampleExecutionService(client)
        if periods:
            result = service.list_periods(" task ", 2, 30, "2026-10-01 00:00:00", "2026-10-02 00:00:00",
                                          ["COMPLETED", "FAILED", "COMPLETED"]) if filtered else service.list_periods("task")
        else:
            result = service.list_executions("task", 2, 30, True) if filtered else service.list_executions("task")
        assert result == {"taskId": "task", "page": expected["pageIndex"],
                          "pageSize": expected["pageSize"], "total": 375, "items": [ITEM]}


@pytest.mark.parametrize("kwargs,key", [({"start_time": "2026-10-01 00:00:00"}, "periodStartTime"),
                                        ({"end_time": "2026-10-01 00:00:00"}, "periodEndTime")])
def test_single_time_boundary(kwargs, key):
    client = Client()
    SampleExecutionService(client).list_periods("t", **kwargs)
    data = client.calls[0][2]["data"]
    assert data[key] == 1790784000000
    assert ("periodEndTime" if key == "periodStartTime" else "periodStartTime") not in data


@pytest.mark.parametrize("value", ["2026-2-01 00:00:00", "2026-02-30 00:00:00", "2026-10-01", "", "1790784000000"])
def test_bad_time(value):
    with pytest.raises(ValueError):
        parse_time(value)


@pytest.mark.parametrize("method,field", [("list_periods", "instances"), ("list_executions", "jobs")])
def test_response_validation_and_missing_business(method, field):
    for payload in ({}, {"result": {"code": 0}}, {"result": {"code": 1, "des": "denied"}},
                    {"result": {"code": False, field: [], "count": 0}},
                    {"result": {"code": 0, field: [None], "count": 1}},
                    {"result": {"code": 0, field: [], "count": -1}},
                    {"result": {"code": 0, field: [], "count": True}}):
        with pytest.raises(ApiError):
            getattr(SampleExecutionService(Client(payload=payload)), method)("task")
    client = Client()
    client.business_id = " "
    with pytest.raises(BusinessError):
        getattr(SampleExecutionService(client), method)("task")
    assert client.calls == []


def invoke(client, group, args, output="table"):
    def authenticated(operation):
        print("正在刷新认证")
        return operation(client)
    runtime = SimpleNamespace(authenticated_call=authenticated,
        config=SimpleNamespace(current_profile=lambda: SimpleNamespace(output_format=output)))
    with patch("wiserec_cli.cli.Runtime", return_value=runtime), patch(
        "wiserec_cli.commands.sample_execution.runtime_from_context", return_value=runtime):
        return CliRunner().invoke(app, ["sample-task", group, "list", *args])


@pytest.mark.parametrize("group,field", [("period", "instances"), ("execution", "jobs")])
def test_cli_json_errors_empty(group, field):
    result = invoke(Client(field), group, ["task"], "json")
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["items"] == [ITEM]
    assert "正在刷新认证" in result.stderr
    failed = invoke(Client(payload={"result": {"code": 1, "des": "denied"}}), group, ["task", "-o", "json"])
    assert failed.exit_code == 1 and failed.stdout == ""
    assert "denied" in failed.stderr
    empty = invoke(Client(payload={"result": {"code": 0, field: [], "count": 0}}), group, ["task"])
    assert empty.exit_code == 0
    assert "暂无执行" in empty.stdout
    assert "┌" not in empty.stdout


@pytest.mark.parametrize("args", [[" "], ["task", "--page", "0"], ["task", "--page-size", "0"],
    ["task", "--state", "bad"], ["task", "--start-time", "2026-10-02 00:00:00", "--end-time", "2026-10-01 00:00:00"],
    ["task", "-o", "csv"], ["task", "--source", "new"]])
def test_invalid_cli(args):
    client = Client()
    assert invoke(client, "period", args).exit_code != 0
    assert not client.calls


def test_cli_filters():
    client = Client()
    result = invoke(client, "period", ["task", "--state", "INIT", "--state", "RUNNING", "--page", "2", "--page-size", "7"])
    assert result.exit_code == 0, result.output
    assert client.calls[0][2]["data"]["states"] == ["INIT", "RUNNING"]
    assert client.calls[0][2]["data"]["pageSize"] == 7
    client = Client("jobs")
    assert invoke(client, "execution", ["task", "--include-history"]).exit_code == 0
    assert client.calls[0][2]["latestFlag"] == "all"


@pytest.mark.parametrize("size", [1, 4, 7, 20, 21])
def test_period_grid(size):
    items = [{"period": f"period-{i}", "state": "INIT"} for i in range(size)]
    with patch("wiserec_cli.commands.sample_execution.console") as console:
        render_page({"taskId": "task", "page": 2, "pageSize": 30, "total": size, "items": items}, "table", periods=True)
    table = next(call.args[0] for call in console.print.call_args_list if isinstance(call.args[0], Table))
    assert len(table.columns) == 4
    assert not table.show_header
    assert len(table.rows) == (size + 3) // 4
    for i in range(size):
        assert table.columns[i % 4]._cells[i // 4].plain == f"{i + 1} period-{i} 初始化"
    for i in range(size, len(table.rows) * 4):
        assert table.columns[i % 4]._cells[i // 4].plain == ""


def test_execution_format_and_id():
    expected = {"status": "执行完成", "fileSize": "179.53K", "runningTime": "3h52min", "latestFlag": "是",
                "checkTime": "2026-10-21 05:07:33", "createTime": "2026-10-21 00:34:50", "statusTime": "2026-10-21 04:27:36"}
    for field, value in expected.items():
        assert display_value(field, ITEM[field]) == value
    assert display_value("checkTime", "2026-09-08T06:54:36.000+00:00") == "2026-09-08 14:54:36"
    assert display_value("status", "UNKNOWN") == "UNKNOWN"
    assert display_value("latestFlag", False) == "否"
    assert display_value("runningTime", 180) == "3h0min"
    assert display_value("runningTime", 0) == "0min"
    assert display_value("fileSize", 0) == "0B"
    assert display_value("fileSize", None) == "-"
    for width in (80, 240):
        stream = io.StringIO()
        with patch("wiserec_cli.commands.sample_execution.console", Console(file=stream, width=width)):
            render_page({"taskId": "task", "page": 1, "pageSize": 10, "total": 1, "items": [ITEM]}, "table")
        assert ITEM["jobId"] in stream.getvalue()
