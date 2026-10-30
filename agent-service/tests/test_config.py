import pytest
from pydantic import ValidationError
from app.settings import Settings
from app.tools import build_tools, REGISTRY


def test_local_only(settings):
    data = settings.model_dump(mode="json")
    data["server"]["host"] = "0.0.0.0"
    with pytest.raises(ValidationError):
        Settings.model_validate(data)


def test_tools_are_explicit_and_server_scoped():
    async def invoke(name, args):
        return args

    tools = build_tools(invoke)
    from app.business_tools import OPERATIONS
    assert len(tools) == len(REGISTRY) == 13 + len(OPERATIONS)
    assert all(op.write for name, op in OPERATIONS.items()
               if name.startswith(('delete_', 'start_', 'cancel_', 'publish_', 'upload_', 'update_')))
    for tool in tools:
        assert "cookie" not in str(tool.params_json_schema)
        assert "business_id" not in str(tool.params_json_schema)


def test_model_modes_explicit(settings):
    data = settings.model_dump()
    data["llm"]["api_mode"] = "unsupported"
    with pytest.raises(ValidationError):
        Settings.model_validate(data)


def test_missing_configuration_exposes_setup_state_without_mock(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from app.main import create_app

    monkeypatch.setenv("WISEREC_AGENT_CONFIG", str(tmp_path / "missing.json"))
    with TestClient(create_app()) as client:
        assert client.get("/api/health").json()["ready"] is False
        assert client.get("/api/environments").json() == []
        result = client.get("/api/session")
        assert result.status_code == 503
        assert result.json()["error"]["code"] == "SETUP_REQUIRED"
        assert client.get("/").status_code == 200


def test_config_diagnostics_hide_secrets(settings):
    from app.config_errors import describe_config_error

    data = settings.model_dump()
    data["access_control"]["gateway_token"] = "SECRET_VALUE"
    data["server"]["host"] = "SECRET_HOST"
    data["SECRET_FIELD_NAME"] = "SECRET_INPUT"
    with pytest.raises(ValidationError) as caught:
        Settings.model_validate(data)
    message = describe_config_error(caught.value)
    assert "access_control.gateway_token" in message and "server.host" in message
    assert "SECRET" not in message
    assert "32" in message


def test_migrate_config_error_is_actionable_and_does_not_connect(
    monkeypatch, tmp_path, capsys
):
    from app import manage

    config = tmp_path / "bad.json"
    config.write_text('{"password":"secret-do-not-print",}', encoding="utf-8")
    monkeypatch.setattr("sys.argv", ["manage", "migrate", "--config", str(config)])
    monkeypatch.setattr(manage, "connect", lambda *_: pytest.fail("must not connect"))
    assert manage.main() == 1
    message = capsys.readouterr().err
    assert "JSON 格式错误" in message and "第 1 行" in message
    assert "secret-do-not-print" not in message


@pytest.mark.parametrize("limit,accepted", [(200000, True), (200001, False)])
def test_tool_output_character_limit(settings, limit, accepted):
    data = settings.model_dump()
    data["runtime"]["max_tool_output_chars"] = limit
    if accepted:
        assert Settings.model_validate(data).runtime.max_tool_output_chars == limit
    else:
        with pytest.raises(ValidationError):
            Settings.model_validate(data)
