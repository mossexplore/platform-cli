from unittest.mock import Mock, patch
import httpx
import pytest
from wiserec_cli.access import check_access
from wiserec_cli.access_diagnostics import AccessDiagnostics, endpoint
from wiserec_cli.errors import MlError
from test_access import inputs, response_mock


def test_504_diagnostics_and_redaction(inputs):
    lines = []
    diagnostics = AccessDiagnostics(lines.append)
    response = httpx.Response(504, headers={'server':'gateway', 'via':'secret-cookie',
        'set-cookie':'do-not-print', 'x-request-id':'trace-123'}, text='private response body')
    manager = response_mock(response)
    with patch('wiserec_cli.access.httpx.Client', return_value=manager):
        with pytest.raises(MlError, match='504'):
            check_access(*inputs, diagnostics=diagnostics)
    trace = manager.__enter__().post.call_args.kwargs['extensions']['trace']
    trace('connection.connect_tcp.started', {'host':b'gateway.internal', 'port':8008, 'request':'do-not-print'})
    stream = Mock()
    stream.get_extra_info.return_value = ('10.0.1.1', 8008)
    trace('connection.connect_tcp.complete', {'return_value':stream})
    output = '\n'.join(lines)
    for expected in ['HTTP 状态: 504','server: gateway','trace-123','请求耗时','gateway.internal:8008','10.0.1.1:8008','current-business','账号: alice']:
        assert expected in output
    for forbidden in ['secret-cookie','do-not-print','private response body']:
        assert forbidden not in output


def test_timeout_has_elapsed_without_fabricated_response(inputs):
    lines = []
    with patch('wiserec_cli.access.httpx.Client', side_effect=httpx.ReadTimeout('secret-cookie')):
        with pytest.raises(MlError):
            check_access(*inputs, diagnostics=AccessDiagnostics(lines.append))
    output = '\n'.join(lines)
    assert '请求耗时' in output
    assert 'HTTP 状态' not in output
    assert 'secret-cookie' not in output


def test_url_credentials_and_query_are_removed():
    assert endpoint('http://u:password@proxy:8008/path?token=secret') == 'http://proxy:8008/path'


def test_diagnose_option_is_available(tmp_path):
    from typer.testing import CliRunner
    from wiserec_cli.cli import app
    config = tmp_path / 'config.json'
    config.write_text('{"current":"dev","profiles":[{"name":"dev","api_endpoint":"https://example.com"}]}')
    result = CliRunner().invoke(app, ['--config', str(config), 'access', 'status', '--help'])
    assert result.exit_code == 0
    assert '--diagnose' in result.output
