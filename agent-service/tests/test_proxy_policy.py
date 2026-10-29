"""Exercise HTTPX's actual environment proxy selection, without external traffic."""

import httpx
import pytest
from sqlalchemy import select
from wiserec_cli.models import Credentials
from app.platform import Platform
from app.models import Session
from app.errors import AppError
from conftest import ready, BUSINESS


@pytest.fixture
def proxy_network(monkeypatch):
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://unreachable-proxy.invalid:9")
    monkeypatch.setenv("NO_PROXY", "")
    seen = []
    original = httpx.HTTPTransport.__init__

    def init(self, *args, **kwargs):
        self.test_proxy = kwargs.get("proxy")
        original(self, *args, **kwargs)

    def send(self, request):
        seen.append((request.url.path, self.test_proxy is not None))
        if self.test_proxy is not None:
            raise httpx.ProxyError("unreachable test proxy")
        if request.url.path.endswith("/user/info"):
            return httpx.Response(
                200, json={"result": {"code": 0, "username": "zhangsan"}}
            )
        return httpx.Response(200, json={"allowed": True})

    monkeypatch.setattr(httpx.HTTPTransport, "__init__", init)
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", send)
    return seen


def test_identity_ignores_environment_proxy(settings, proxy_network):
    platform = Platform(settings, None)
    cred = Credentials.create("dev", "test-cookie", "test-csrf", "zhangsan", 1800)
    assert platform.identity(settings.env("dev"), cred)["username"] == "zhangsan"
    assert proxy_network == [("/ai/user/info", False)]


def test_gateway_default_direct_and_explicit_proxy_opt_in(client, app, proxy_network):
    ready(client)
    with app.state.db() as db:
        sid = db.scalar(select(Session).where(Session.user_id.is_not(None))).id
    platform = Platform(app.state.config, app.state.db)
    platform.gateway(sid, BUSINESS, "list_models", "invocation")
    assert proxy_network[-1][1] is False
    app.state.config.access_control.use_env_proxy = True
    with pytest.raises(AppError, match="权限服务暂时不可用"):
        platform.gateway(sid, BUSINESS, "list_models", "invocation")
    assert proxy_network[-1][1] is True


def test_direct_identity_preserves_custom_ca(
    settings, proxy_network, monkeypatch, tmp_path
):
    import ssl
    import certifi

    ca = tmp_path / "enterprise-ca.pem"
    ca.write_bytes(__import__("pathlib").Path(certifi.where()).read_bytes())
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    contexts = []
    original = ssl.create_default_context

    def context(*args, **kwargs):
        if kwargs.get("cafile") == str(ca):
            contexts.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(ssl, "create_default_context", context)
    Platform(settings, None).identity(
        settings.env("dev"), Credentials.create("dev", "cookie", "csrf", "u", 1800)
    )
    assert contexts and proxy_network[-1][1] is False
