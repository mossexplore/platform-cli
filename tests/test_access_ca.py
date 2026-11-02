"""Real local TLS handshakes; fixture keys are public test-only data, never production credentials."""
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import socket
import ssl
from threading import Thread
from unittest.mock import patch

import httpx
import pytest

from test_access import inputs
from wiserec_cli.access import check_access, validate_settings
from wiserec_cli.access_diagnostics import AccessDiagnostics
from wiserec_cli.access_guidance import check_user_access
from wiserec_cli.access_transport import connection_error, tls_verify
from wiserec_cli.env_access import query_environment_access
from wiserec_cli.errors import ConfigError, MlError

FIXTURES = Path(__file__).parent / 'fixtures/access_tls'


@pytest.fixture
def server():
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path, self.headers, body))
            if self.path.endswith('/check'):
                result = {'allowed': True, 'username': 'alice', 'environment': 'dev'}
            elif self.path.endswith('/summary'):
                result = {'username': 'alice', 'has_access': True}
            else:
                result = {'username': 'alice', 'has_access': True, 'environments': []}
            data = json.dumps(result).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(FIXTURES / 'server.pem', FIXTURES / 'server-key.pem')
    httpd = HTTPServer(('127.0.0.1', 0), Handler)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    thread = Thread(target=lambda: httpd.serve_forever(poll_interval=0.02), daemon=True)
    thread.start()
    try:
        yield f'https://127.0.0.1:{httpd.server_port}', requests
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=3)


def call(endpoint, settings, inputs, diagnostics=None):
    if endpoint == 'check':
        return check_access(settings, *inputs[1:], diagnostics=diagnostics)
    if endpoint == 'summary':
        return check_user_access(settings, 'alice', 'current-business')
    return query_environment_access(settings, 'alice', [], 'current-business')


@pytest.mark.parametrize('endpoint', ['check', 'summary', 'environments'])
@pytest.mark.parametrize('source', ['certifi', 'custom', 'env', 'legacy'])
def test_real_tls_sources_and_polluted_agent_environment(server, inputs, monkeypatch, endpoint, source):
    url, requests = server
    # The local root substitutes for certifi solely to verify real TLS offline.
    monkeypatch.setattr('certifi.where', lambda: str(FIXTURES / 'ca.pem'))
    monkeypatch.setenv('SSL_CERT_FILE', str(FIXTURES / 'unrelated-ca.pem'))
    monkeypatch.setenv('SSL_CERT_DIR', '/nonexistent/agent-ca-directory')
    settings = {'url': url, 'timeout_seconds': 3, 'use_env_proxy': False}
    if source != 'legacy':
        settings['ca_source'] = source
    if source == 'custom':
        settings['ca_file'] = str(FIXTURES / 'ca.pem')
    elif source in {'env', 'legacy'}:
        monkeypatch.setenv('SSL_CERT_FILE', str(FIXTURES / 'ca.pem'))
    result = call(endpoint, settings, inputs)
    assert result
    assert len(requests) == 1
    assert requests[0][0].endswith('/' + endpoint)
    assert requests[0][1]['businessid'] == 'current-business'
    assert requests[0][2]['username'] == 'alice'
    assert 'SSL_CERT_FILE' in os.environ  # No process-wide mutation.


@pytest.mark.parametrize('endpoint', ['check', 'summary', 'environments'])
@pytest.mark.parametrize('source', ['certifi', 'custom', 'env'])
def test_untrusted_certificate_fails_without_fallback(server, inputs, monkeypatch, endpoint, source):
    url, requests = server
    monkeypatch.setattr('certifi.where', lambda: str(FIXTURES / ('unrelated-ca.pem' if source == 'certifi' else 'ca.pem')))
    monkeypatch.setenv('SSL_CERT_FILE', str(FIXTURES / ('unrelated-ca.pem' if source == 'env' else 'ca.pem')))
    settings = {'url': url, 'ca_source': source, 'timeout_seconds': 3}
    if source == 'custom':
        settings['ca_file'] = str(FIXTURES / 'unrelated-ca.pem')
    with pytest.raises(MlError, match='证书校验失败') as error:
        call(endpoint, settings, inputs)
    assert source in str(error.value)
    assert not requests  # No HTTP request reached the service.


@pytest.mark.parametrize('proxy', [True, False])
def test_certifi_ignores_invalid_ca_variables_with_either_proxy_setting(monkeypatch, proxy):
    monkeypatch.setenv('SSL_CERT_FILE', '/missing/agent/secret-token.pem')
    monkeypatch.setenv('SSL_CERT_DIR', '/missing/agent/secret-cookie')
    context = tls_verify({'ca_source': 'certifi', 'use_env_proxy': proxy})
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    assert context.cert_store_stats()['x509_ca'] > 0


@pytest.mark.parametrize('settings', [
    {'ca_source': None}, {'ca_source': 'wrong'}, {'ca_source': []},
    {'ca_source': 'custom'}, {'ca_source': 'custom', 'ca_file': ''},
    {'ca_source': 'custom', 'ca_file': 'relative.pem'}, {'ca_source': 'custom', 'ca_file': 12},
    {'ca_source': 'certifi', 'ca_file': '/tmp/test.pem'}, {'ca_file': '/tmp/test.pem'},
])
def test_invalid_ca_configuration(settings):
    with pytest.raises(ConfigError, match='access_control.ca_'):
        validate_settings(settings)


@pytest.mark.parametrize('source', ['env', 'custom'])
def test_unloadable_ca_fails_closed_without_exposing_path(monkeypatch, source, tmp_path):
    monkeypatch.setenv('SSL_CERT_FILE', '/missing/secret-cookie.pem')
    settings = {'ca_source': source}
    if source == 'custom':
        settings['ca_file'] = str(tmp_path / 'secret-cookie.pem')
    with pytest.raises(ConfigError, match='CA 配置无法加载') as error:
        tls_verify(settings)
    assert source in str(error.value)
    assert 'secret-cookie' not in str(error.value)


def test_ca_source_is_visible_in_diagnostics(inputs, monkeypatch):
    lines = []
    monkeypatch.setenv('SSL_CERT_FILE', '/missing/secret-cookie.pem')
    with patch('wiserec_cli.access.create_client', side_effect=httpx.ConnectError('secret-cookie')):
        with pytest.raises(MlError):
            check_access(dict(inputs[0], ca_source='certifi'), *inputs[1:], diagnostics=AccessDiagnostics(lines.append))
    output = '\n'.join(lines)
    assert 'CA 来源: certifi 公共 CA' in output
    assert 'secret-cookie' not in output


def test_error_classification_does_not_echo_exception_content():
    outer = httpx.ConnectError('secret-cookie')
    outer.__cause__ = socket.gaierror('secret-token')
    assert '域名解析失败' in str(connection_error(outer, {}, 'fallback'))
    assert 'secret' not in str(connection_error(outer, {}, 'fallback'))
    for exc, label in [(httpx.ConnectTimeout('secret'), '连接权限服务超时'),
                       (httpx.ReadTimeout('secret'), '等待权限服务响应超时')]:
        assert label in str(connection_error(exc, {}, 'fallback'))


@pytest.mark.parametrize('endpoint', ['check', 'summary', 'environments'])
@pytest.mark.parametrize('use_proxy', [True, False])
def test_ca_mode_keeps_proxy_setting_independent(inputs, endpoint, use_proxy):
    seen = []
    def handler(request):
        if endpoint == 'check':
            body = {'allowed': True, 'username': 'alice', 'environment': 'dev'}
        elif endpoint == 'summary':
            body = {'username': 'alice', 'has_access': True}
        else:
            body = {'username': 'alice', 'has_access': True, 'environments': []}
        return httpx.Response(200, json=body)
    def client(**kwargs):
        seen.append(kwargs)
        return httpx.Client(transport=httpx.MockTransport(handler))
    module = {'check': 'access', 'summary': 'access_guidance', 'environments': 'env_access'}[endpoint]
    with patch('wiserec_cli.' + module + '.create_client', side_effect=client):
        call(endpoint, dict(inputs[0], ca_source='certifi', use_env_proxy=use_proxy), inputs)
    assert len(seen) == 1
    assert seen[0]['trust_env'] is use_proxy
    assert seen[0]['verify'].verify_mode == ssl.CERT_REQUIRED
    assert seen[0]['verify'].check_hostname
