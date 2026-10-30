"""质量监控契约、环境隔离、表格和原始 JSON。"""
import inspect
import json
from io import StringIO
from unittest.mock import patch

import httpx
import pytest
from rich.console import Console
from typer.testing import CliRunner

from test_webstudio import rt
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.commands.quality_display import display_value, render_page
from wiserec_cli.services.quality import PREFIX, TYPES, QualityService
from wiserec_cli.errors import ApiError, BusinessError

ID = "33b1a068-0c3d-4d23-b4aa-a6001ee33342"
FEATURE = {"featureId": ID, "featureName": "feature_" * 30,
           "featTableName": "table_" * 20, "featureType": "DOUBLE",
           "featureValueType": "", "indicatorType": "CATEGORICAL", "creator": "user",
           "latestCycleTime": "2026102800", "freshnessValue": None,
           "nullValueRate": 0.0, "extra": {"retained": True}}
WIDE = {"setId": ID, "setName": "set_" * 30, "version": "latest",
        "outTableName": "table_" * 20, "scene": "测试", "creator": "user",
        "modifier": "user", "createTime": "2026-10-10 10:35:05",
        "updateTime": "2026-10-30T02:56:46Z", "extra": True}


def payload(wide=False, items=None):
    return {"result": {"code": 0, "des": "success", "totalCount": 30,
            "pageIndex": 1, "pageSize": 1,
            "featureSetList" if wide else "featureList":
                ([WIDE if wide else FEATURE] if items is None else items)}}


@pytest.fixture
def invoke(rt):
    options = {"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {}
    def run(args, handler):
        with patch("wiserec_cli.cli.Runtime", return_value=rt), patch(
            "wiserec_cli.runtime.PlatformClient", side_effect=lambda *a, **kw:
                PlatformClient(*a, transport=httpx.MockTransport(handler), **kw)):
            return CliRunner(**options).invoke(app, ["quality", *args])
    return run


@pytest.mark.parametrize("wide", [False, True])
@pytest.mark.parametrize("filtered", [False, True])
def test_http_contract_and_raw_json(invoke, wide, filtered):
    expected = {"pageIndex": 1, "pageSize": 10}
    expected.update({"setName": ""} if wide else {"featureName": "", "tableName": ""})
    args = ["wide-featureset" if wide else "feature", "list", "-o", "json"]
    if filtered:
        expected.update(pageIndex=2, pageSize=100)
        expected["setName" if wide else "featureName"] = "name"
        args += ["--name", "name", "--page", "2", "--page-size", "100"]
        if not wide:
            args += ["--table-name", "table", "--feature-value-type", "离散",
                     "--indicator-type", "vector"]
            expected.update(tableName="table", featureValueType="DISCRETE", indicatorType="VECTOR")
    def handler(request):
        assert request.method == "POST"
        assert request.url.host == "console.example"
        assert request.url.path == PREFIX + ("/wide-feature-sets" if wide else "")
        assert request.headers.get_list("businessid") == ["pps"]
        assert json.loads(request.content) == expected
        return httpx.Response(200, json=payload(wide))
    result = invoke(args, handler)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == {"items": [WIDE if wide else FEATURE],
                                         "count": 30, "pageIndex": 1, "pageSize": 1}


@pytest.mark.parametrize("wide", [False, True])
@pytest.mark.parametrize("args", [["--page", "0"], ["--page-size", "0"],
    ["--page-size", "101"], ["--output", "yaml"], ["--business-id", "other"]])
def test_cli_invalid_options_never_request(invoke, wide, args):
    result = invoke(["wide-featureset" if wide else "feature", "list", *args],
                    lambda request: pytest.fail("不应请求"))
    assert result.exit_code != 0


@pytest.mark.parametrize("option", ["--feature-value-type", "--indicator-type"])
def test_invalid_enum_before_auth(invoke, rt, option):
    result = invoke(["feature", "list", option, "bad"], lambda r: pytest.fail("不应请求"))
    assert result.exit_code != 0
    rt.auth.ensure_credentials.assert_not_called()


@pytest.mark.parametrize("wide", [False, True])
def test_environment_selected_business_is_checked(invoke, rt, wide):
    rt.business.selected_business_id = lambda *args: "different-environment"
    result = invoke(["wide-featureset" if wide else "feature", "list"],
                    lambda r: pytest.fail("不应请求"))
    assert result.exit_code == 1
    assert "selected.businessId" in result.stderr


class Client:
    business_id = "selected"
    def __init__(self, data=None):
        self.data = payload() if data is None else data
        self.calls = []
    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self.data


@pytest.mark.parametrize("wide", [False, True])
@pytest.mark.parametrize("kwargs", [{"page": 0}, {"page": True}, {"page_size": 101}, {"page_size": 0}])
def test_service_paging_validation(wide, kwargs):
    client = Client()
    with pytest.raises(ValueError):
        service = QualityService(client)
        (service.list_wide_featuresets if wide else service.list_features)(**kwargs)
    assert client.calls == []


@pytest.mark.parametrize("field", ["feature_value_type", "indicator_type"])
@pytest.mark.parametrize("key,label", TYPES.items())
def test_all_enum_input_forms(field, key, label):
    for value in (key, key.lower(), label):
        client = Client()
        QualityService(client).list_features(**{field: value})
        body = client.calls[0][1]["json_body"]
        assert body["featureValueType" if field == "feature_value_type" else "indicatorType"] == key


def test_missing_business_and_fallback_paging():
    client = Client()
    client.business_id = " "
    with pytest.raises(BusinessError):
        QualityService(client).list_features()
    assert client.calls == []
    client.business_id = "selected"
    del client.data["result"]["pageIndex"]
    del client.data["result"]["pageSize"]
    assert QualityService(client).list_features(3, 20)["pageIndex"] == 3
    assert QualityService(client).list_features(3, 20)["pageSize"] == 20


@pytest.mark.parametrize("data", [[], {}, {"result": []}, {"result": {"code": 2, "des": "denied"}},
    {"result": {"code": False}}, {"result": {"code": 0, "featureList": [None]}},
    {"result": {"code": 0, "featureList": [], "totalCount": None}},
    {"result": {"code": 0, "featureList": [], "totalCount": False}},
    {"result": {"code": 0, "featureList": [], "totalCount": 0, "pageIndex": None}}])
def test_bad_response(data):
    with pytest.raises(ApiError):
        QualityService(Client(data)).list_features()


@pytest.mark.parametrize("wide", [False, True])
def test_empty_error_and_default_json(invoke, rt, wide):
    command = ["wide-featureset" if wide else "feature", "list"]
    result = invoke(command, lambda r: httpx.Response(200, json=payload(wide, [])))
    assert result.exit_code == 0
    assert ("暂无宽表特征集质量记录" if wide else "暂无特征质量记录") in result.stdout
    assert "每页 1 条" in result.stdout
    failed = invoke(command + ["-o", "json"], lambda r: httpx.Response(200,
                    json={"result": {"code": 2, "des": "denied"}}))
    assert failed.exit_code == 1
    assert failed.stdout == ""
    assert "denied" in failed.stderr
    failed = invoke(command, lambda r: httpx.Response(500, text="server error"))
    assert failed.exit_code == 1
    rt.config._data["profiles"][0]["output_format"] = "json"
    result = invoke(command, lambda r: httpx.Response(200, json=payload(wide)))
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["items"] == [WIDE if wide else FEATURE]


@pytest.mark.parametrize("field,value,expected", [
    ("featureValueType", None, "-"), ("featureValueType", "", "-"),
    ("indicatorType", "CATEGORICAL", "分类"), ("indicatorType", "NEW", "NEW"),
    ("nullValueRate", 0, "0%"), ("nullValueRate", 0.125, "12.5%"),
    ("nullValueRate", 1, "100%"), ("nullValueRate", None, "-"),
    ("nullValueRate", 0.000001, "0.0001%"), ("freshnessValue", 0, "0"),
    ("latestCycleTime", "2026102800", "2026102800"),
    ("createTime", "2026-10-10 10:35:05", "2026-10-10 10:35:05"),
    ("updateTime", "2026-09-08T06:54:36.000+00:00", "2026-09-08 14:54:36"),
    ("updateTime", "2026-10-30T02:56:46Z", "2026-10-30 10:56:46"),
    ("updateTime", "2026-10-30T23:56:46-05:00", "2026-10-31 12:56:46"),
])
def test_display_values(field, value, expected):
    assert display_value(field, value) == expected


@pytest.mark.parametrize("wide", [False, True])
@pytest.mark.parametrize("width", [80, 240])
def test_complete_id_in_narrow_terminal(wide, width):
    stream = StringIO()
    item = dict(WIDE if wide else FEATURE, creator="[red]literal[/red]")
    with patch("wiserec_cli.commands.quality_display.console", Console(file=stream, width=width)):
        render_page({"items": [item], "count": 30, "pageIndex": 1, "pageSize": 1}, "table", wide)
    assert ID in stream.getvalue()
    if width == 240:
        assert "[red]literal[/red]" in stream.getvalue()


@pytest.mark.parametrize("wide", [False, True])
def test_environment_switch_and_auth_diagnostics(invoke, rt, wide):
    from wiserec_cli.business import Department, Tenant
    from wiserec_cli.models import Credentials
    rt.config._data["profiles"].append({"name": "dev", "api_endpoint": "https://dev.example/dashboard"})
    rt.config._data["current"] = "dev"
    credentials = Credentials.create("dev", "cookie", "csrf", "current-user", 3600)
    def authenticate(**kwargs):
        print("刷新认证")
        return credentials
    rt.auth.ensure_credentials.side_effect = authenticate
    rt.business.refresh("dev", "current-user", [Department("d", "D", (
        Tenant("dev-business", "Dev", (), ()),))], browser_business_id="dev-business")
    def handler(request):
        assert request.url.host == "dev.example"
        assert request.headers["businessid"] == "dev-business"
        return httpx.Response(200, json=payload(wide))
    result = invoke(["wide-featureset" if wide else "feature", "list", "-o", "json"], handler)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["items"] == [WIDE if wide else FEATURE]
    assert "刷新认证" in result.stderr


def test_missing_stored_selected_business_does_not_fallback(invoke, rt):
    data = json.loads(rt.business.path.read_text())
    data["profiles"]["prod"]["selected"].pop("businessId")
    rt.business.path.write_text(json.dumps(data))
    result = invoke(["feature", "list"], lambda r: pytest.fail("不应请求"))
    assert result.exit_code == 1
    assert "selected.businessId" in result.stderr
