"""装配查询契约、环境隔离、分页及最终输出。"""
import json
from io import StringIO
from unittest.mock import patch

import httpx
import pytest
from rich.console import Console

from test_quality import invoke, Client, ID
from test_webstudio import rt
from wiserec_cli.commands.quality_assembly import display_value, render_assembly
from wiserec_cli.errors import ApiError, BusinessError
from wiserec_cli.services.quality import PREFIX, QualityService

DEFINITION = {"definitionId": ID, "definitionName": "sample", "outputTable": "table_" * 30,
              "latestCycle": "2026110100", "latestRatio": 0.1538, "extra": {"keep": True}}
FEATURE = {"featureId": ID, "featureName": "seq_time", "featureType": "string",
           "featureValueType": "", "latestCycleTime": "2026110112", "nullValueRate": 0.017,
           "extra": {"keep": True}}


def payload(features=False, items=None):
    result = {"code": 0, "des": "success",
              "featureList" if features else "sampleDefinitionList":
                  ([FEATURE if features else DEFINITION] if items is None else items)}
    if features:
        result.update(totalCount=777, pageIndex=1, pageSize=1)
    else:
        result["featureSetId"] = "returned-id"
    return {"result": result}


def command(kind, features=False):
    return ["wide-featureset", kind, *(["feature"] if features else []), "list",
            "--set-id", "input-id", *(["--definition-id", ID] if features else [])]


@pytest.mark.parametrize("kind", ["feature-assemble", "label-assemble"])
@pytest.mark.parametrize("features", [False, True])
@pytest.mark.parametrize("paging", [False, True])
def test_http_and_json_contract(invoke, kind, features, paging):
    args = command(kind, features) + ["-o", "json"]
    expected = {"setId": "input-id", "type": kind.replace("-", "_")}
    if features:
        expected.update(definitionId=ID, pageIndex=2 if paging else 1, pageSize=100 if paging else 10)
        if paging:
            args += ["--page", "2", "--page-size", "100"]
    def handler(request):
        assert request.method == "POST"
        assert request.url.host == "console.example"
        assert request.url.path == PREFIX + "/feature-sets/query" + ("/feature-indicators" if features else "")
        assert request.headers.get_list("businessid") == ["pps"]
        assert json.loads(request.content) == expected
        return httpx.Response(200, json=payload(features))
    result = invoke(args, handler)
    assert result.exit_code == 0, result.output
    expected_result = {"items": [FEATURE if features else DEFINITION], "count": 777 if features else 1}
    expected_result.update({"pageIndex": 1, "pageSize": 1} if features else {"featureSetId": "returned-id"})
    assert json.loads(result.stdout) == expected_result


@pytest.mark.parametrize("features", [False, True])
@pytest.mark.parametrize("options", [["--set-id", " "], ["--output", "yaml"], ["--business-id", "bad"]])
def test_invalid_options_before_auth(invoke, rt, features, options):
    result = invoke(command("label-assemble", features) + options, lambda r: pytest.fail("不应请求"))
    assert result.exit_code != 0
    rt.auth.ensure_credentials.assert_not_called()


@pytest.mark.parametrize("options", [["--page", "0"], ["--page-size", "0"],
    ["--page-size", "101"], ["--definition-id", " "], ["--page", "abc"]])
def test_invalid_feature_paging(invoke, rt, options):
    result = invoke(command("feature-assemble", True) + options, lambda r: pytest.fail("不应请求"))
    assert result.exit_code != 0
    rt.auth.ensure_credentials.assert_not_called()


@pytest.mark.parametrize("features", [False, True])
def test_missing_ids_and_environment_isolation(invoke, rt, features):
    args = command("label-assemble", features)
    result = invoke(args[:args.index("--set-id")], lambda r: pytest.fail("不应请求"))
    assert result.exit_code != 0
    rt.business.selected_business_id = lambda *a: "different-environment"
    result = invoke(args, lambda r: pytest.fail("不应请求"))
    assert result.exit_code == 1
    assert "selected.businessId" in result.stderr


@pytest.mark.parametrize("features", [False, True])
def test_empty_error_and_default_json(invoke, rt, features):
    args = command("label-assemble", features)
    result = invoke(args, lambda r: httpx.Response(200, json=payload(features, [])))
    assert result.exit_code == 0
    assert ("暂无特征记录" if features else "暂无标签装配样本定义") in result.stdout
    if not features:
        assert "returned-id" in result.stderr
        assert "input-id" in result.stderr
    rt.config._data["profiles"][0]["output_format"] = "json"
    result = invoke(args, lambda r: httpx.Response(200, json=payload(features)))
    assert result.exit_code == 0
    assert json.loads(result.stdout)["items"][0]["extra"] == {"keep": True}
    for response in (httpx.Response(500), httpx.Response(200, json={"result": {"code": 2, "des": "denied"}})):
        result = invoke(args + ["-o", "json"], lambda r: response)
        assert result.exit_code == 1
        assert result.stdout == ""


@pytest.mark.parametrize("features", [False, True])
def test_service_validation_and_fallback(features):
    client = Client(payload(features))
    service = QualityService(client)
    operation = (lambda **kw: service.list_assembly_features("set", ID, "label_assemble", **kw)) if features else (
        lambda **kw: service.list_assemblies("set", "feature_assemble"))
    client.business_id = " "
    with pytest.raises(BusinessError):
        operation()
    assert client.calls == []
    client.business_id = "selected"
    if features:
        for kwargs in ({"page": 0}, {"page_size": 101}, {"page": True}):
            with pytest.raises(ValueError):
                operation(**kwargs)
        assert client.calls == []
        del client.data["result"]["pageIndex"]
        del client.data["result"]["pageSize"]
        assert operation(page=3, page_size=20)["pageIndex"] == 3
        assert operation(page=3, page_size=20)["pageSize"] == 20
    else:
        del client.data["result"]["featureSetId"]
        assert "featureSetId" not in operation()
    key = "featureList" if features else "sampleDefinitionList"
    for value in (None, {}, [None]):
        client.data["result"][key] = value
        with pytest.raises(ApiError):
            operation()


@pytest.mark.parametrize("set_id,kind,definition", [(" ", "label_assemble", ID),
    ("set", "bad", ID), ("set", "feature_assemble", ""), ("set", "feature_assemble", None)])
def test_service_invalid_ids(set_id, kind, definition):
    client = Client()
    with pytest.raises(ValueError):
        QualityService(client).list_assembly_features(set_id, definition, kind)
    assert client.calls == []


@pytest.mark.parametrize("value,expected", [(None, "-"), ("", "-"), (0, "0%"),
    (1, "100%"), (0.1538, "15%"), (0.017, "2%"), (0.125, "13%"), ("0.005", "1%")])
@pytest.mark.parametrize("field", ["latestRatio", "nullValueRate"])
def test_integer_percentages(field, value, expected):
    assert display_value(field, value) == expected


@pytest.mark.parametrize("features", [False, True])
@pytest.mark.parametrize("width", [45, 80, 180])
def test_final_table_ids_columns_and_values(features, width):
    stream = StringIO()
    result = {"items": [FEATURE if features else DEFINITION], "count": 777 if features else 1,
              "pageIndex": 1, "pageSize": 1}
    with patch("wiserec_cli.commands.quality_assembly.console", Console(file=stream, width=width)):
        render_assembly(result, "table", "标签装配", "set", features)
    assert ID in stream.getvalue()
    if width == 180:
        assert ("2%" if features else "15%") in stream.getvalue()
        assert ("标签装配最新周期" if features else "样本定义名称") in stream.getvalue()
        assert ("2026110112" if features else "2026110100") in stream.getvalue()


@pytest.mark.parametrize("kind", ["feature-assemble", "label-assemble"])
@pytest.mark.parametrize("features", [False, True])
def test_environment_switch_and_auth_output(invoke, rt, kind, features):
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
        return httpx.Response(200, json=payload(features))
    result = invoke(command(kind, features) + ["-o", "json"], handler)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["items"] == [FEATURE if features else DEFINITION]
    assert "刷新认证" in result.stderr


@pytest.mark.parametrize("features", [False, True])
def test_missing_selected_business_never_requests(invoke, rt, features):
    data = json.loads(rt.business.path.read_text())
    del data["profiles"]["prod"]["selected"]["businessId"]
    rt.business.path.write_text(json.dumps(data))
    result = invoke(command("feature-assemble", features), lambda r: pytest.fail("不应请求"))
    assert result.exit_code == 1
    assert "selected.businessId" in result.stderr


@pytest.mark.parametrize("kind", ["feature-assemble", "label-assemble"])
@pytest.mark.parametrize("features", [False, True])
def test_permission_command_and_denial(invoke, kind, features):
    path = "ml quality wide-featureset " + kind + (" feature list" if features else " list")
    def deny(*args, **kwargs):
        assert kwargs["command"] == path
        raise BusinessError("permission denied")
    with patch("wiserec_cli.runtime.check_access", side_effect=deny):
        result = invoke(command(kind, features) + ["-o", "json"], lambda r: pytest.fail("不应请求"))
    assert result.exit_code == 1
    assert result.stdout == ""
    assert "permission denied" in result.stderr
