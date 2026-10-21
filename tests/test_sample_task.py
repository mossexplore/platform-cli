import io
import json
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

import httpx
import pytest
from rich.console import Console
from typer.testing import CliRunner

from wiserec_cli.business import BusinessSelection
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.commands.sample_task import display_value, render_page
from wiserec_cli.errors import ApiError, BusinessError
from wiserec_cli.models import Credentials, Profile
from wiserec_cli.services.sample_task import SampleTaskService

ITEM = {"taskId": "43a7851f-32c4-4746-b601-4d1715c3fbc8", "taskName": "browser",
        "category": "feature_preprocess_offline", "updateTime": 1780450555000,
        "description": None, "extra": {"keep": True}}
DEFAULT_CATEGORY = "feature_preprocess_realtime,feature_preprocess_offline,feature_assemble,label_assemble"


def response(source="legacy", items=None):
    items = [ITEM] if items is None else items
    if source == "legacy":
        return {"result": {"code": 0, "count": len(items), "taskInfos": items}}
    return {"result": {"code": 0, "data": {"total": len(items), "list": items}}}


class Client:
    business_id = "chosen"

    def __init__(self, payload=None):
        self.payload = response() if payload is None else payload
        self.calls = []

    def request(self, method, path, json_body):
        self.calls.append((method, path, json_body))
        return self.payload


@pytest.mark.parametrize("source", ["legacy", "new"])
@pytest.mark.parametrize("filtered", [False, True])
def test_http_contract_and_business_header(source, filtered):
    expected = {"businessId": "chosen", "pageSize": 20 if filtered else 10}
    kwargs = {"source": source}
    if filtered:
        kwargs.update(page=2, page_size=20, name="browser", creator="creator", updater="updater")
    if source == "legacy":
        expected.update(pageIndex=2 if filtered else 1, category=DEFAULT_CATEGORY)
        path = "/ai/backend/dpp/proxy/schedule-service/task/list"
        if filtered:
            kwargs.update(types=["spark_jar", "feature_monitor", "spark_jar"], status="started")
            expected.update(category="spark_jar,feature_monitor", taskStatusList="START",
                            taskName="browser", createUser="creator", updateUser="updater")
    else:
        path = "/ai/backend/dpp/proxy/featureStore/v2/task/list"
        expected.update(pageNo=2 if filtered else 1, sortType="desc", taskName="", createBy="", updateBy="")
        if filtered:
            kwargs.update(types=["FEATURE_SYNC", "FEATURE_ASSEMBLE", "FEATURE_SYNC"], sort="desc")
            expected.update(taskName="browser", createBy="creator", updateBy="updater",
                            taskSubCategoryList=["FEATURE_SYNC", "FEATURE_ASSEMBLE"])

    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == "https://dev.example.com" + path
        assert request.headers.get_list("businessid") == ["chosen"]
        body = json.loads(request.content)
        assert body["version"] == "1.0"
        assert UUID(body["meta"]["uuid"]).version == 4
        assert body["data"] == expected
        return httpx.Response(200, json=response(source))

    selection = BusinessSelection(type="team", department_id="d", department_name="D",
        tenant_id="t", tenant_name="T", team_id="team", team_name="Team", business_id="chosen")
    with PlatformClient(Profile("dev", "https://dev.example.com/dashboard"),
        Credentials.create("dev", "session=a", "csrf", "jack", 1800), 30000, 0, True,
        transport=httpx.MockTransport(handler), business_selection=selection) as client:
        assert SampleTaskService(client).list_tasks(**kwargs) == {
            "source": source, "page": 2 if filtered else 1, "pageSize": expected["pageSize"],
            "total": 1, "items": [ITEM]}


@pytest.mark.parametrize("status,expected", [(None, None), ("all", None), ("stopped", "STOP")])
def test_legacy_status(status, expected):
    client = Client()
    SampleTaskService(client).list_tasks(status=status)
    data = client.calls[0][2]["data"]
    if expected is None:
        assert "taskStatusList" not in data
    else:
        assert data["taskStatusList"] == expected


@pytest.mark.parametrize("items", [[], [ITEM], [[ITEM]], [[], [ITEM]]])
def test_new_list_shapes(items):
    assert SampleTaskService(Client(response("new", items))).list_tasks(source="new")["items"] == ([] if not items else [ITEM])


@pytest.mark.parametrize("source", ["legacy", "new"])
@pytest.mark.parametrize("items", [None, {}, [None], [[[ITEM]]], ["bad"]])
def test_invalid_items(source, items):
    payload = response(source)
    if source == "legacy":
        payload["result"]["taskInfos"] = items
    else:
        payload["result"]["data"]["list"] = items
    with pytest.raises(ApiError):
        SampleTaskService(Client(payload)).list_tasks(source=source)


@pytest.mark.parametrize("payload", [{}, [], {"result": {}}, {"result": {"code": False}},
    {"result": {"code": 5, "des": "denied"}}, {"result": {"code": 0}},
    {"result": {"code": 0, "count": "1", "taskInfos": []}},
    {"result": {"code": 0, "count": -1, "taskInfos": []}}])
def test_bad_response(payload):
    with pytest.raises(ApiError):
        SampleTaskService(Client(payload)).list_tasks()


def test_missing_business():
    client = Client()
    client.business_id = " "
    with pytest.raises(BusinessError):
        SampleTaskService(client).list_tasks()
    assert not client.calls


def invoke(client, args, output="table"):
    def authenticated(operation):
        print("正在刷新认证")
        return operation(client)
    runtime = SimpleNamespace(authenticated_call=authenticated,
        config=SimpleNamespace(current_profile=lambda: SimpleNamespace(output_format=output)))
    with patch("wiserec_cli.cli.Runtime", return_value=runtime), patch(
        "wiserec_cli.commands.sample_task.runtime_from_context", return_value=runtime):
        return CliRunner().invoke(app, ["sample-task", "list", *args])


def test_cli_defaults_and_new_json():
    client = Client()
    result = invoke(client, [])
    assert result.exit_code == 0, result.output
    assert "任务管理（旧）" in result.stdout
    assert client.calls[0][1].endswith("schedule-service/task/list")
    result = invoke(Client(response("new", [[ITEM]])), ["--source", "new", "-o", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"source": "new", "page": 1, "pageSize": 10, "total": 1, "items": [ITEM]}
    assert "正在刷新认证" in result.stderr
    assert json.loads(invoke(Client(), [], output="json").stdout)["source"] == "legacy"


def test_cli_filters():
    client = Client(response("new"))
    result = invoke(client, ["--source", "new", "--type", "FEATURE_SYNC", "--type", "FEATURE_ASSEMBLE",
        "--creator", "alice", "--updater", "bob", "--name", "sample", "--page", "3", "--page-size", "25"])
    assert result.exit_code == 0, result.output
    assert client.calls[0][2]["data"] == {"businessId": "chosen", "pageNo": 3, "pageSize": 25,
        "sortType": "desc", "taskName": "sample", "createBy": "alice", "updateBy": "bob",
        "taskSubCategoryList": ["FEATURE_SYNC", "FEATURE_ASSEMBLE"]}


@pytest.mark.parametrize("args", [["--source", "bad"], ["--page", "0"], ["--page-size", "-1"],
    ["--source", "new", "--status", "all"], ["--sort", "desc"], ["--status", "STOP"],
    ["--source", "new", "--sort", "asc"], ["--type", "FEATURE_SYNC"],
    ["--source", "new", "--type", "feature_assemble"], ["--output", "csv"]])
def test_cli_invalid_options(args):
    client = Client()
    result = invoke(client, args)
    assert result.exit_code != 0
    assert not client.calls


def test_empty_and_business_error():
    result = invoke(Client(response(items=[])), [])
    assert result.exit_code == 0
    assert "暂无样本任务" in result.stdout
    result = invoke(Client({"result": {"code": 1, "des": "denied"}}), ["-o", "json"])
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "denied" in result.stderr


def test_display_values_and_full_id():
    assert display_value("updateTime", ITEM) == "2026-06-03 09:35:55"
    assert display_value("updateTime", {"updateTime": "2026-09-08T06:54:36.000+00:00"}) == "2026-09-08 14:54:36"
    assert display_value("createTime", {"createTime": "2026-09-30 09:42:26"}) == "2026-09-30 09:42:26"
    assert display_value("category", ITEM) == "特征预处理(离线)"
    assert display_value("taskSubCategoryCn", {"taskSubCategory": "FEATURE_SYNC"}) == "特征同步任务"
    assert display_value("taskSubCategoryCn", {"taskSubCategory": "future"}) == "future"
    assert display_value("taskStateCn", {"taskStatus": "START"}) == "启动"
    assert display_value("taskStateCn", {"taskStateCn": "服务端状态", "taskState": "STOP"}) == "服务端状态"
    assert display_value("description", ITEM) == "-"
    for source in ("legacy", "new"):
        for width in (80, 240):
            buffer = io.StringIO()
            with patch("wiserec_cli.commands.sample_task.console", Console(file=buffer, width=width)):
                render_page({"source": source, "items": [ITEM], "total": 1, "page": 1, "pageSize": 10}, "table")
            assert ITEM["taskId"] in buffer.getvalue()
