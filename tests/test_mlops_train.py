"""老管理台训练列表协议和离线能力门禁。"""
import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.models import Profile, Credentials
from wiserec_cli.business import BusinessSelection
from wiserec_cli.services.train import TrainService
from wiserec_cli.commands.train import display_value
from wiserec_cli.errors import ApiError


def configuration(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"current": "old", "profiles": [{"name": "old",
                    "platform_type": "mlops", "api_endpoint": "https://old.example"}]}))
    return path


def test_request_response_and_business_header():
    record = {"taskId": "79c380e3-70ad-4bdb-8d85-b61d34f332a6", "taskName": "alarm",
              "updateTime": 1793934137000, "fileSize": 0, "extra": {"preserved": True}}
    def handler(request):
        assert request.url.path == "/ai/backend/mtp/traintask/queryList"
        assert request.headers["businessid"] == "selected-business"
        body = json.loads(request.content)
        assert body["businessId"] == "selected-business"
        assert (body["taskName"], body["pageIndex"], body["pageSize"]) == ("alarm", 2, 200)
        assert "data" not in body and "reverseTaskTags" not in body
        assert body["inputJobId"] == body["jobStr"] == body["jobId"] == ""
        assert body["jobStatus"] == [] and body["tags"] is None
        return httpx.Response(200, json={"result": {"code": 0, "count": 201, "taskInfos": [record]}})
    with PlatformClient(Profile("old", "https://old.example", platform_type="mlops"),
                        Credentials.create("old", "a=b", "csrf", "user", 60),
                        1000, 0, True, transport=httpx.MockTransport(handler),
                        business_selection=SimpleNamespace(business_id="selected-business")) as client:
        result = TrainService(client).list_tasks(2, 200, "alarm")
    assert result == dict(count=201, pageIndex=2, pageSize=200, items=[record])
    assert display_value("updateTime", record["updateTime"]) == "2026-11-06 11:02:17"
    assert display_value("fileSize", 0) == "0B"
    assert display_value("fileSize", 1024) == "1.00K"
    assert display_value("fileSize", 1024**2) == "1.00M"


@pytest.mark.parametrize("size", [0, 201])
def test_page_size_rejected_before_request(size):
    client = SimpleNamespace(platform_type="mlops", business_id="b")
    with pytest.raises(ValueError):
        TrainService(client).list_tasks(page_size=size)


def test_tree_and_unsupported_command_offline(tmp_path):
    config = configuration(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["--config", str(config), "tree"])
    assert result.exit_code == 0, result.output
    assert "mlops" in result.output and "── list" in result.output
    assert "立即执行指定训练任务" not in result.output and "── dataset" not in result.output
    result = runner.invoke(app, ["--config", str(config), "tree", "--all"])
    assert result.exit_code == 0, result.output
    assert "start  不支持" in result.output
    with patch("wiserec_cli.auth.AuthManager.ensure_credentials", side_effect=AssertionError("must not login")), \
         patch("wiserec_cli.cli.ping.auto_start", side_effect=AssertionError("must not ping")):
        result = runner.invoke(app, ["--config", str(config), "train", "start", "TASK_ID"])
    assert result.exit_code == 1
    assert "不支持" in result.output


@pytest.mark.parametrize("payload", [
    {"result": {"code": 1, "des": "denied"}},
    {"result": {"code": 0, "count": 1}},
    {"result": {"code": 0, "count": None, "taskInfos": []}},
    {"result": {"code": 0, "count": 1, "taskInfos": [None]}},
])
def test_invalid_responses_rejected(payload):
    client = SimpleNamespace(platform_type="mlops", business_id="b", request=lambda *a, **kw: payload)
    with pytest.raises(ApiError):
        TrainService(client).list_tasks()


def test_platform_validation_and_help(tmp_path):
    from wiserec_cli.config import ConfigManager
    from wiserec_cli.errors import ConfigError
    path = configuration(tmp_path)
    result = CliRunner().invoke(app, ["--config", str(path), "train", "start", "--help"])
    assert result.exit_code == 0, result.output
    settings = json.loads(path.read_text())
    settings["profiles"][0]["platform_type"] = []
    path.write_text(json.dumps(settings))
    with pytest.raises(ConfigError):
        ConfigManager(path)


def test_default_body_and_empty_result():
    requests = []
    def request(method, path, json_body):
        requests.append(json_body)
        return {"result": {"code": 0, "count": 0, "taskInfos": []}}
    client = SimpleNamespace(platform_type="mlops", business_id="current-business", request=request)
    result = TrainService(client).list_tasks()
    body = requests[0]
    assert body["taskName"] == "" and body["businessId"] == "current-business"
    assert (body["pageIndex"], body["pageSize"]) == (1, 10)
    assert set(body) == set('taskName taskType taskType1 businessId cronFlag depTask scene subScene noticeTime updateNoticeTime jobStatus teamId noRunDays createUser updateUser taskTags trainEngine trainMode distFramework tags category private baseInfo isDeleted region scope inputName algorithmName algoInputName algorithmVersion taskOwner imagePackageId bucketName external inputTaskId taskStr inputJobId jobStr customLabels sharing beginTime endTime updateBeginTime updateEndTime pageIndex pageSize running excludeSpecFlag taskId jobId'.split())
    assert result == dict(count=0, pageIndex=1, pageSize=10, items=[])


def test_install_sync_preserves_mlops_profile(tmp_path):
    from wiserec_cli.config import _sync_packaged_config, ConfigManager
    path = configuration(tmp_path)
    with patch('wiserec_cli.config._packaged_config_text', return_value=json.dumps({
            'current': 'new', 'profiles': [{'name': 'new', 'api_endpoint': 'https://new.example'}]})):
        _sync_packaged_config(path, force=True)
    assert ConfigManager(path).current_profile().platform_type == 'mlops'
    assert ConfigManager(path).current_profile().api_endpoint == 'https://old.example'


def test_cli_mlops_list_dispatch(tmp_path):
    from wiserec_cli.runtime import Runtime
    config = configuration(tmp_path)
    runtime = Runtime(config_path=config, credential_path=tmp_path / 'credentials.json',
                      business_path=tmp_path / 'business.json')
    calls = []
    def request(method, path, json_body):
        calls.append((path, json_body))
        return {'result': {'code': 0, 'count': 0, 'taskInfos': []}}
    client = SimpleNamespace(platform_type='mlops', business_id='selected', request=request)
    with patch('wiserec_cli.cli.Runtime', return_value=runtime), \
         patch.object(runtime, 'authenticated_call', side_effect=lambda operation: operation(client)):
        result = CliRunner().invoke(app, ['--config', str(config), 'train', 'list',
                                         '--name', 'alarm', '--page-size', '200', '-o', 'json'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['count'] == 0
    assert calls[0][0] == '/ai/backend/mtp/traintask/queryList'
    assert calls[0][1]['taskName'] == 'alarm'
