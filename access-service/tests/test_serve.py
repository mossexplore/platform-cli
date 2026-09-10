import pytest
from app.serve import main


def test_http_listens_without_certificates(monkeypatch):
    monkeypatch.setenv('LISTEN_HOST', '0.0.0.0')
    monkeypatch.setenv('LISTEN_PORT', '8008')
    monkeypatch.setenv('TLS_CERT_FILE', '')
    monkeypatch.setenv('TLS_KEY_FILE', '')
    calls = []
    monkeypatch.setattr('app.serve.uvicorn.run', lambda *args, **kwargs: calls.append(kwargs))
    main()
    assert calls[0]['host'] == '0.0.0.0'
    assert calls[0]['ssl_certfile'] is None
    assert calls[0]['ssl_keyfile'] is None


def test_partial_tls_configuration_rejected(monkeypatch):
    monkeypatch.setenv('TLS_CERT_FILE', '/some/cert.pem')
    monkeypatch.setenv('TLS_KEY_FILE', '')
    with pytest.raises(RuntimeError, match='同时配置'):
        main()


def test_https_still_supported(monkeypatch):
    monkeypatch.setenv('TLS_CERT_FILE', '/some/cert.pem')
    monkeypatch.setenv('TLS_KEY_FILE', '/some/key.pem')
    calls = []
    monkeypatch.setattr('app.serve.uvicorn.run', lambda *args, **kwargs: calls.append(kwargs))
    main()
    assert calls[0]['ssl_certfile'] == '/some/cert.pem'
    assert calls[0]['ssl_keyfile'] == '/some/key.pem'


@pytest.mark.parametrize('trusted', ['', '172.30.0.10', '172.30.0.0/24'])
def test_proxy_trust_can_be_disabled_or_limited(monkeypatch, trusted):
    monkeypatch.setenv('FORWARDED_ALLOW_IPS', trusted)
    monkeypatch.setenv('TLS_CERT_FILE', '')
    monkeypatch.setenv('TLS_KEY_FILE', '')
    calls = []
    monkeypatch.setattr('app.serve.uvicorn.run', lambda *args, **kwargs: calls.append(kwargs))
    main()
    assert calls[0]['forwarded_allow_ips'] == trusted
