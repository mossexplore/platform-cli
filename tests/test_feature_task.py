import io
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from rich.console import Console
from typer.testing import CliRunner

from wiserec_cli.business import BusinessSelection
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.commands.feature_task import display_value, render_page
from wiserec_cli.errors import ApiError, BusinessError
from wiserec_cli.models import Credentials, Profile
from wiserec_cli.services.feature_task import FeatureTaskService, TASK_TYPES

DEFAULTS = {
    "taskName": "", "taskType": "", "taskType1": "ALL", "businessId": "chosen",
    "scene": "", "subScene": "", "cronFlag": "", "noticeTime": [], "jobStatus": [],
    "depTask": "", "teamId": "", "noRunDays": "", "createUser": "", "updateUser": "",
    "taskTags": [], "trainEngine": "", "tags": [], "category": "dpp-all",
    "trainMode": "", "distFramework": "", "private": False, "reverseTaskTags": [],
    "reverseTags": [], "region": "", "scope": "", "subDataZoneId": "",
    "pageIndex": 1, "pageSize": 10, "running": False,
}
ITEM = {"taskId": "ed99888f-0744-4cde-a9fb-ea84bafbb84a", "taskName": "embedding_to_increase_rank_sfps_v2",
        "taskType": "train_fi", "scene": "NLP", "jobStatus": "RUNNING", "createUser": "l00123456",
        "updateUser": "l00123456", "updateTime": 1731998960000, "fileSize": 112016136,
        "description": "", "extraField": {"retained": True}}


class Client:
    business_id = "chosen"

    def __init__(self, payload=None):
        self.calls = []
        self.payload = payload if payload is not None else {"result": {"code": 0, "count": 1, "taskInfos": [ITEM]}}

    def request(self, method, path, json_body):
        self.calls.append((method, path, json_body))
        return self.payload


@pytest.mark.parametrize("filtered", [False, True])
def test_request_defaults_and_business_header(filtered):
    expected = dict(DEFAULTS)
    if filtered:
        expected.update(taskName="embedding", category="train_fi", createUser="user", pageIndex=2, pageSize=20)

    def handler(request):
        assert request.method == "POST"
        assert str(request.url) == "https://dev.example.com/ai/backend/mtp/traintask/queryList"
        assert request.headers.get_list("businessid") == ["chosen"]
        assert json.loads(request.content) == expected
        return httpx.Response(200, json={"result": {"code": 0, "count": 1, "taskInfos": [ITEM]}})

    selection = BusinessSelection(type="team", department_id="d", department_name="D",
        tenant_id="t", tenant_name="T", team_id="team", team_name="Team", business_id="chosen")
    with PlatformClient(Profile("dev", "https://dev.example.com/dashboard"),
        Credentials.create("dev", "session=a", "csrf", "jack", 1800), 30000, 0, True,
        transport=httpx.MockTransport(handler), business_selection=selection) as client:
        service = FeatureTaskService(client)
        result = service.list_tasks(2, 20, "embedding", "train_fi", "user") if filtered else service.list_tasks()
        assert result == {"items": [ITEM], "count": 1, "pageIndex": expected["pageIndex"], "pageSize": expected["pageSize"]}


@pytest.mark.parametrize("kwargs", [{"page_index": 0}, {"page_size": -1}, {"page_index": True}, {"category": "bad"}])
def test_invalid_options_do_not_request(kwargs):
    client = Client()
    with pytest.raises(ValueError):
        FeatureTaskService(client).list_tasks(**kwargs)
    assert client.calls == []


def test_missing_business_does_not_request():
    client = Client()
    client.business_id = " "
    with pytest.raises(BusinessError, match="ml business use"):
        FeatureTaskService(client).list_tasks()
    assert client.calls == []


@pytest.mark.parametrize("payload", [[], {}, {"result": []},
    {"result": {"code": 1, "des": "denied"}}, {"result": {"code": False}},
    {"result": {"code": 0, "count": 0}},
    {"result": {"code": 0, "count": 0, "taskInfos": [None]}},
    {"result": {"code": 0, "count": -1, "taskInfos": []}},
    {"result": {"code": 0, "count": False, "taskInfos": []}}])
def test_malformed_response(payload):
    with pytest.raises(ApiError):
        FeatureTaskService(Client(payload)).list_tasks()


def invoke(client, args, output="table"):
    def authenticated(operation):
        print("正在刷新认证")
        return operation(client)
    runtime = SimpleNamespace(authenticated_call=authenticated,
        config=SimpleNamespace(current_profile=lambda: SimpleNamespace(output_format=output)))
    with patch("wiserec_cli.cli.Runtime", return_value=runtime), patch(
        "wiserec_cli.commands.feature_task.runtime_from_context", return_value=runtime):
        return CliRunner().invoke(app, ["feature-task", "list", *args])


def test_cli_json_keeps_raw_fields_and_filters():
    client = Client()
    result = invoke(client, ["--name", "embedding", "--category", "train_fi", "--create-user", "user",
                             "--page", "2", "--page-size", "20", "-o", "json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"items": [ITEM], "count": 1, "pageIndex": 2, "pageSize": 20}
    assert "正在刷新认证" in result.stderr
    assert client.calls[0][2] == dict(DEFAULTS, taskName="embedding", category="train_fi",
                                     createUser="user", pageIndex=2, pageSize=20)
    assert json.loads(invoke(Client(), [], output="json").stdout)["items"] == [ITEM]


@pytest.mark.parametrize("args", [["--category", "bad"], ["--page", "0"], ["--page-size", "0"],
    ["--output", "yaml"], ["--running"], ["--business-id", "other"], ["--task-type", "train_fi"]])
def test_cli_rejects_options_before_request(args):
    client = Client()
    assert invoke(client, args).exit_code != 0
    assert client.calls == []


def test_display_and_table():
    for key, label in TASK_TYPES.items():
        assert display_value("taskType", key) == label
    assert display_value("taskType", "future") == "future"
    assert display_value("taskName", "train_fi") == "train_fi"
    assert display_value("updateTime", ITEM["updateTime"]) == "2024-11-19 14:49:20"
    assert display_value("fileSize", ITEM["fileSize"]) == "106.83M"
    assert display_value("fileSize", 0) == "0B"
    assert display_value("fileSize", 1024 ** 3) == "1.00G"
    assert display_value("description", None) == "-"
    for width in (80, 240):
        buffer = io.StringIO()
        with patch("wiserec_cli.commands.feature_task.console", Console(file=buffer, width=width)):
            render_page({"items": [dict(ITEM, description="[red]literal[/red]")],
                         "count": 1, "pageIndex": 1, "pageSize": 10}, "table")
        assert ITEM["taskId"] in buffer.getvalue()
        if width == 240:
            assert "FI直连任务" in buffer.getvalue()
            assert "[red]literal[/red]" in buffer.getvalue()
    empty = invoke(Client({"result": {"code": 0, "count": 0, "taskInfos": []}}), [])
    assert empty.exit_code == 0
    assert "暂无特征任务" in empty.stdout
    failed = invoke(Client({"result": {"code": 2, "des": "denied"}}), ["-o", "json"])
    assert failed.exit_code == 1
    assert failed.stdout == ""
    assert "denied" in failed.stderr
