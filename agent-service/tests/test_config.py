import pytest
from pydantic import ValidationError
from app.settings import Settings
from app.tools import build_tools, REGISTRY


def test_local_only(settings):
    data = settings.model_dump(mode="json")
    data["server"]["host"] = "0.0.0.0"
    with pytest.raises(ValidationError):
        Settings.model_validate(data)


def test_tools_are_read_only():
    async def invoke(name, args):
        return args

    tools = build_tools(invoke)
    assert len(tools) == 13
    assert not any(
        x in name
        for name in REGISTRY
        for x in ("delete", "start", "cancel", "deploy_model", "exec")
    )
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
