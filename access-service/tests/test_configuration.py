import io
from pathlib import Path

import pytest
from app import configuration, healthcheck, manage, serve


@pytest.fixture
def mounted(monkeypatch, tmp_path):
    path = tmp_path / 'service.env'
    monkeypatch.setattr(configuration, 'DEFAULT_ENV_FILE', str(path))
    monkeypatch.delenv('SERVICE_ENV_FILE', raising=False)
    # Restore the environment after dotenv's writes, too.
    monkeypatch.setattr('os.environ', dict(__import__('os').environ))
    return path


def test_optional_and_required_file(monkeypatch, mounted):
    assert configuration.load_service_config() is False
    monkeypatch.setenv('SERVICE_ENV_FILE', str(mounted))
    with pytest.raises(RuntimeError, match='不存在'):
        configuration.load_service_config()


def test_mount_overrides_defaults_and_keeps_password_literal(monkeypatch, mounted):
    mounted.write_text('LISTEN_PORT=9000\nDATABASE_URL=mysql+pymysql://user:${PASSWORD}@db/test\n')
    monkeypatch.setenv('LISTEN_PORT', '8008')
    monkeypatch.setenv('PASSWORD', 'should-not-expand')
    assert configuration.load_service_config()
    import os
    assert os.environ['LISTEN_PORT'] == '9000'
    assert '${PASSWORD}' in os.environ['DATABASE_URL']


def test_unreadable_file_fails_without_content(monkeypatch, mounted):
    def denied(*args, **kwargs):
        raise PermissionError('secret must not appear')
    monkeypatch.setattr(Path, 'open', denied)
    with pytest.raises(RuntimeError, match='文件权限') as exc:
        configuration.load_service_config()
    assert 'secret' not in str(exc.value)


def test_startup_reads_mount_before_listening(monkeypatch, mounted):
    mounted.write_text('LISTEN_HOST=0.0.0.0\nLISTEN_PORT=9000\nTLS_CERT_FILE=\nTLS_KEY_FILE=\n')
    calls = []
    monkeypatch.setattr(serve.uvicorn, 'run', lambda *a, **kw: calls.append(kw))
    serve.main()
    assert calls[0]['host'] == '0.0.0.0'
    assert calls[0]['port'] == 9000


def test_probe_reads_mounted_url(monkeypatch, mounted):
    mounted.write_text('HEALTHCHECK_URL=http://127.0.0.1:9000/cli-permission/healthz\n')
    class Response(io.BytesIO):
        status = 200
    class Opener:
        def open(self, url, timeout):
            assert ':9000/' in url
            return Response(b'{"status":"ok"}')
    monkeypatch.setattr(healthcheck.urllib.request, 'build_opener', lambda *a: Opener())
    assert healthcheck.main() == 0
    monkeypatch.setenv('SERVICE_ENV_FILE', str(mounted.parent / 'missing'))
    assert healthcheck.main() == 1


def test_management_uses_mounted_database(monkeypatch, mounted):
    mounted.write_text('DATABASE_URL=mysql+pymysql://user:password@db/test\n')
    monkeypatch.setattr('sys.argv', ['manage', 'migrate'])
    class Engine:
        def dispose(self):
            pass
    def database(url):
        assert url == 'mysql+pymysql://user:password@db/test'
        return Engine(), 'sessions'
    calls = []
    monkeypatch.setattr(manage, 'database', database)
    monkeypatch.setattr(manage, 'migrate', lambda *a: calls.append(a))
    manage.main()
    assert len(calls) == 1
