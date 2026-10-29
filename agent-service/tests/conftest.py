import json
import time
from pathlib import Path
import httpx
import pytest
from fastapi.testclient import TestClient
from wiserec_cli.models import Credentials
from app.settings import Settings
from app.db import connect, migrate
from app.main import create_app

BUSINESS = {
    "type": "tenant",
    "department_id": "d",
    "department_name": "部门",
    "tenant_id": "b1",
    "tenant_name": "推荐业务",
    "businessId": "b1",
    "team_id": "",
    "team_name": "",
}


class Upstream:
    def __init__(self):
        self.calls = []
        self.allow = True
        self.identity_valid = True

    def __call__(self, request):
        self.calls.append(request)
        if request.url.path.endswith("/gateway/check"):
            return httpx.Response(
                200 if self.allow else 403, json={"allowed": self.allow}
            )
        if request.url.path == "/ai/user/info":
            return httpx.Response(
                200,
                json={
                    "result": {
                        "code": 0 if self.identity_valid else 1,
                        "username": "zhangsan",
                        "cnName": "张三",
                        "department": "测试",
                    }
                },
            )
        if request.url.path.endswith("queryList"):
            return httpx.Response(
                200,
                json={
                    "result": {
                        "code": 0,
                        "count": 1,
                        "models": [
                            {
                                "id": "model-1",
                                "name": "推荐模型",
                                "createdAt": "2026-10-29T02:00:00Z",
                                "secret": "should-hide",
                            }
                        ],
                    }
                },
            )
        return httpx.Response(500, json={"result": {"code": 1}})


class TestEngine:
    async def run(self, history, message, context, invoke, delta, progress=None):
        await invoke("list_models", {"name": "", "page": 1, "page_size": 10})
        answer = "已找到推荐模型。查询时间：2026-10-29 10:00:00"
        await delta(answer)
        return (
            answer,
            [
                {"role": "user", "content": message},
                {"role": "assistant", "content": answer},
            ],
            {"requests": 1},
        )


def provider(config, env, attempt, stop, status):
    status("verifying")
    return Credentials.create(
        env.id, "platform-secret-cookie", "csrf-secret", "zhangsan", 1800
    ), [BUSINESS]


@pytest.fixture
def settings(tmp_path):
    data = json.loads((Path(__file__).parents[1] / "config.example.json").read_text())
    data["login"]["profile_root"] = str(tmp_path / "profiles")
    data["runtime"]["state_dir"] = str(tmp_path / "state")
    return Settings.model_validate(data)


@pytest.fixture
def app(settings, tmp_path):
    url = "sqlite:///" + str(tmp_path / "test.db")
    engine, _ = connect(settings, url)
    migrate(engine)
    engine.dispose()
    upstream = Upstream()
    app = create_app(
        settings,
        test_url=url,
        platform_transport=httpx.MockTransport(upstream),
        login_provider=provider,
        agent_engine=TestEngine(),
    )
    app.test_upstream = upstream
    return app


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


def headers(c):
    s = c.get("/api/session").json()
    return {"Origin": "http://testserver", "X-Agent-CSRF": s["csrf_token"]}


def login(c):
    r = c.post(
        "/api/login-attempts", json={"environment_id": "dev"}, headers=headers(c)
    )
    assert r.status_code == 202, r.text
    for _ in range(100):
        result = c.get("/api/login-attempts/" + r.json()["attempt_id"]).json()
        if result["status"] == "succeeded":
            break
        assert result["status"] != "failed", result
        time.sleep(0.02)
    else:
        raise AssertionError("login did not finish")
    return c.get("/api/session").json()


def ready(c):
    login(c)
    result = c.post(
        "/api/business-selection", json={"business_id": "b1"}, headers=headers(c)
    )
    assert result.status_code == 200, result.text
    return result.json()
