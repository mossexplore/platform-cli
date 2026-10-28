import httpx
import pytest
from permission_notifier.diagnostics import response_summary, target
from permission_notifier.service import Service, ServiceError
from permission_notifier.sender import Sender
from permission_notifier.config import Config


def test_summary_bounds_and_redacts():
    response = httpx.Response(200, json={'code': 42, 'message': 'bad secret-token',
        'auth': 'hidden', 'data': {'auth': 'hidden'}, 'trace_id': 'trace-123'})
    summary = response_summary(response, ['secret-token'])
    assert 'secret-token' not in summary and 'hidden' not in summary
    assert 'trace-123' in summary and '42' in summary
    assert '<html>secret</html>' == response_summary(httpx.Response(200, text='<html>secret</html>'), [])
    assert target('https://example.com/private-token?auth=secret') == 'https://example.com'


def test_200_business_error_is_visible_and_not_success():
    config = Config().model_dump()
    config['message'].update(url='https://example.com/send', auth='secret')
    sender = Sender(lambda *_: httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={'code': 4001, 'message': 'receiver not found'}))))
    result = sender.send(config, config['message'], '123', 'test')
    assert result['state'] == 'uncertain'
    assert 'receiver not found' in result['diagnostic']['response_summary']
    assert result['diagnostic']['elapsed_ms'] >= 0


@pytest.mark.parametrize('error,code', [(httpx.ConnectTimeout, 'SERVICE_CONNECT_TIMEOUT'),
    (httpx.ProxyError, 'SERVICE_PROXY_ERROR'), (httpx.ReadTimeout, 'SERVICE_READ_TIMEOUT')])
def test_service_errors_are_classified_without_exception_text(error, code):
    def handler(request):
        raise error('private credentials')
    service = Service(lambda *_: httpx.Client(transport=httpx.MockTransport(handler)))
    config = Config(permission_service_url='https://example.com').model_dump()
    with pytest.raises(ServiceError) as caught:
        service.call(config, 'installation', 'check')
    assert str(caught.value) == code


def test_nested_response_and_text_redaction():
    response = httpx.Response(200, json={'data': [{'result': 'invalid receiver',
        'access_token': 'unknown-token', 'nested': {'auth': 'private'}}],
        'echo': 'configured-secret'})
    result = response_summary(response, ['configured-secret'])
    assert 'invalid receiver' in result
    assert all(secret not in result for secret in ('unknown-token', 'private', 'configured-secret'))
    assert '[已隐藏]' in result
    result = response_summary(httpx.Response(200, text='token=private-value auth=configured-secret'), ['configured-secret'])
    assert 'private-value' not in result and 'configured-secret' not in result


def test_response_size_and_empty_body():
    result = response_summary(httpx.Response(200, text='x'*9000), [])
    assert len(result) < 8100 and '已截断' in result
    assert response_summary(httpx.Response(204), []) == '（空响应体）'
