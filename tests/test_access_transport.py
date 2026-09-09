from unittest.mock import patch
import httpcore
import pytest
from wiserec_cli.access import check_access, validate_settings
from wiserec_cli.access_transport import permission_url, tls_verify
from wiserec_cli.errors import ConfigError, MlError
from test_access import inputs


@pytest.mark.parametrize('base', ['http://access.example.com', 'http://access.example.com/',
    'http://access.example.com/cli-permission', 'http://access.example.com/cli-permission/'])
def test_prefix_once(base):
    assert validate_settings({'url':base})
    assert permission_url(base) == 'http://access.example.com/cli-permission/api/v1/access/check'


@pytest.mark.parametrize('value', ['true', 1, None])
def test_proxy_setting_requires_boolean(value):
    with pytest.raises(ConfigError):
        validate_settings({'url':'http://example.com', 'use_env_proxy':value})


@pytest.mark.parametrize('use_proxy,expected', [(False, 'access.example.com'), (True, 'proxy.example.com')])
def test_actual_transport_target_with_environment_proxy(inputs, monkeypatch, use_proxy, expected):
    for name in ['HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy','SSL_CERT_FILE','SSL_CERT_DIR']:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv('HTTPS_PROXY','http://user:secret@proxy.example.com:6998')
    targets = []
    def connect(self, host, port, **kwargs):
        targets.append(host)
        raise httpcore.ConnectError('connection intercepted without network')
    monkeypatch.setattr(httpcore.SyncBackend, 'connect_tcp', connect)
    settings = dict(inputs[0])
    if use_proxy:
        settings['use_env_proxy'] = True
    with pytest.raises(MlError):
        check_access(settings, *inputs[1:])
    assert targets == [expected]


def test_ca_environment_preserved(monkeypatch):
    monkeypatch.setenv('SSL_CERT_FILE','enterprise.pem')
    monkeypatch.setenv('SSL_CERT_DIR','enterprise-dir')
    with patch('wiserec_cli.access_transport.ssl.create_default_context') as create:
        assert tls_verify() is create.return_value
        create.assert_called_once_with(cafile='enterprise.pem')
    monkeypatch.delenv('SSL_CERT_FILE')
    with patch('wiserec_cli.access_transport.ssl.create_default_context') as create:
        tls_verify()
        create.assert_called_once_with(capath='enterprise-dir')


def test_bad_ca_is_not_reported_as_json_error(inputs, monkeypatch):
    monkeypatch.setenv('SSL_CERT_FILE','/nonexistent/enterprise-ca.pem')
    with pytest.raises(ConfigError, match='CA 配置无法加载'):
        check_access(*inputs)
