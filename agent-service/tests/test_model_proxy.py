"""Use the SDK's real HTTP transport selection with a blocked environment proxy."""

import httpx2
import pytest
from openai import AsyncOpenAI, APIConnectionError
from app.agent_engine import model_http_client


@pytest.mark.parametrize("use_proxy", [False, True])
async def test_model_proxy_is_explicit(settings, monkeypatch, use_proxy):
    for key in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "NO_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "no_proxy",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("HTTPS_PROXY", "http://unreachable-proxy.invalid:9")
    monkeypatch.setenv("NO_PROXY", "")
    settings.llm.use_env_proxy = use_proxy
    seen = []
    original = httpx2.AsyncHTTPTransport.__init__

    def init(self, *args, **kwargs):
        self.test_proxy = kwargs.get("proxy")
        original(self, *args, **kwargs)

    async def send(self, request):
        seen.append(self.test_proxy is not None)
        if self.test_proxy is not None:
            raise httpx2.ProxyError("blocked test proxy")
        return httpx2.Response(
            200,
            json={
                "id": "chat-test",
                "object": "chat.completion",
                "created": 1,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "ok"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "__init__", init)
    monkeypatch.setattr(httpx2.AsyncHTTPTransport, "handle_async_request", send)
    async with (
        model_http_client(settings.llm) as http,
        AsyncOpenAI(
            base_url=settings.llm.base_url,
            api_key="test-only",
            http_client=http,
            max_retries=0,
        ) as client,
    ):
        if use_proxy:
            with pytest.raises(APIConnectionError):
                await client.chat.completions.create(
                    model="test", messages=[{"role": "user", "content": "hi"}]
                )
        else:
            result = await client.chat.completions.create(
                model="test", messages=[{"role": "user", "content": "hi"}]
            )
            assert result.choices[0].message.content == "ok"
    assert seen == [use_proxy]
    assert http.is_closed


async def test_model_direct_preserves_ca_and_timeout(settings, monkeypatch, tmp_path):
    import ssl
    import certifi
    from pathlib import Path

    ca = tmp_path / "enterprise.pem"
    ca.write_bytes(Path(certifi.where()).read_bytes())
    monkeypatch.setenv("SSL_CERT_FILE", str(ca))
    seen = []
    original = ssl.create_default_context

    def context(*args, **kwargs):
        if kwargs.get("cafile") == str(ca):
            seen.append(True)
        return original(*args, **kwargs)

    monkeypatch.setattr(ssl, "create_default_context", context)
    async with model_http_client(settings.llm) as http:
        assert http.timeout.read == settings.llm.timeout_seconds
    assert seen and http.is_closed
