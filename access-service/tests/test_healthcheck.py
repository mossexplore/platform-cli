import io
from urllib.error import URLError
import pytest
from app.healthcheck import main


@pytest.mark.parametrize('body,status,expected', [
    (b'{"status":"ok"}', 200, 0),
    (b'{"status":"schema_not_ready"}', 503, 1),
    (b'{"status":"schema_not_ready"}', 200, 1),
    (b'not json', 200, 1),
])
def test_probe_requires_healthy_http_and_database(monkeypatch, body, status, expected):
    class Response(io.BytesIO):
        pass
    response = Response(body)
    response.status = status
    class Opener:
        def open(self, url, timeout):
            assert url == 'http://127.0.0.1:8008/cli-permission/healthz'
            assert timeout == 3
            return response
    monkeypatch.delenv('HEALTHCHECK_URL', raising=False)
    monkeypatch.setattr('app.healthcheck.urllib.request.build_opener', lambda handler: Opener())
    assert main() == expected


def test_connection_failure_is_unhealthy(monkeypatch):
    class Opener:
        def open(self, *args, **kwargs):
            raise URLError('connection refused')
    monkeypatch.setattr('app.healthcheck.urllib.request.build_opener', lambda handler: Opener())
    assert main() == 1
