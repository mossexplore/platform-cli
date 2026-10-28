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
    assert '正文未展示' in response_summary(httpx.Response(200, text='<html>secret</html>'), [])
    assert target('https://example.com/private-token?auth=secret') == 'https://example.com'


def test_200_business_error_is_visible_without_changing_success_contract():
    config = Config().model_dump()
    config['message'].update(url='https://example.com/send', auth='secret')
    sender = Sender(lambda *_: httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={'code': 4001, 'message': 'receiver not found'}))))
    result = sender.send(config, config['message'], '123', 'test')
    assert result['state'] == 'accepted'
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
