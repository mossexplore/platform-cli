"""服务日志引导流程与请求契约。"""
import json
from unittest.mock import patch

import httpx
import pytest
import test_service


@pytest.fixture
def invoke():
    base = test_service.ServiceCommandTest()
    base.setUp()
    yield base.invoke
    base.doCleanups()


def handler_for(infra='infer-python', hosts=None, files=None):
    calls = []
    hosts = hosts if hosts is not None else [{'nodeName': 'pod', 'clusterName': 'cluster', 'infraType': infra}]
    files = files if files is not None else [{'fileName': 'app.log', 'fileSize': '12', 'updateTime': '2026-10-08T00:00:00Z'}]
    def handler(request):
        body = json.loads(request.content)
        calls.append((request.url.path, body))
        assert request.headers['businessid'] == 'mep'
        assert request.url.host == 'dev.example.com'
        if request.url.path.endswith('queryServiceHostList'):
            page = body['pageIndex']
            return httpx.Response(200, json={'result': {'code': 0, 'count': len(hosts), 'data': hosts[(page-1)*10:page*10]}})
        data = body['data']
        assert data['podName'] == 'pod' and data['clusterName'] == 'cluster'
        assert data['serviceLogSearch']['type'] == 'interface'
        if infra == 'infer-python':
            assert data['type'] == 'rtc_python'
        else:
            assert 'type' not in data
        if request.url.path.endswith('queryPodAdvanceLogFileList'):
            result = {'code': 0, 'podLogFiles': files}
        else:
            result = {'code': 0, 'data': {'content': '[INFO] line\nsecond'}}
        return httpx.Response(200, json={'result': result})
    return handler, calls


@pytest.mark.parametrize('infra', ['infer-python', 'rtc'])
def test_auto_single_and_exact_body(invoke, infra):
    handler, calls = handler_for(infra)
    result = invoke(['logs', 'service', '--type', 'interface', '-k', 'error', '-n', '500', '--no-input'], handler)
    assert result.exit_code == 0, result.output
    assert result.stdout == '[INFO] line\nsecond'
    assert len(calls) == 3
    assert calls[-1][1]['data']['serviceLogSearch'] == {
        'type': 'interface', 'keywords': ['error'], 'line': 500, 'searchOrder': 'tail',
        'logFileName': 'app.log', 'grepScope': 'C', 'grepLine': 0}


def test_pagination_and_explicit_selection(invoke):
    hosts = [{'nodeName': str(i), 'clusterName': 'other', 'infraType': 'rtc'} for i in range(10)]
    hosts.append({'nodeName': 'pod', 'clusterName': 'cluster', 'infraType': 'infer-python'})
    handler, calls = handler_for(hosts=hosts)
    result = invoke(['logs', 'service', '--pod', 'pod', '--type', 'interface', '--file', 'app.log'], handler)
    assert result.exit_code == 0, result.output
    assert [body['pageIndex'] for path, body in calls if path.endswith('queryServiceHostList')] == [1, 2]


@pytest.mark.parametrize('extra', [[], ['--type', 'bad'], ['--pod', 'missing', '--type', 'interface']])
def test_unresolved_or_invalid_selection_stops(invoke, extra):
    handler, calls = handler_for()
    result = invoke(['logs', 'service', '--no-input'] + extra, handler)
    assert result.exit_code != 0
    assert len(calls) == 1


@pytest.mark.parametrize('extra', [['--file', 'a'], ['-k', 'error'], ['-n', '200']])
def test_list_conflicts_before_request(invoke, extra):
    handler, calls = handler_for()
    result = invoke(['logs', 'service', '--list'] + extra, handler)
    assert result.exit_code != 0
    assert calls == []


def test_list_only(invoke):
    handler, calls = handler_for()
    result = invoke(['logs', 'service', '--type', 'interface', '--list'], handler)
    assert result.exit_code == 0, result.output
    assert '2026-10-08 08:00:00' in result.stdout
    assert len(calls) == 2


def test_interactive_choices(invoke):
    hosts = [{'nodeName': 'other', 'clusterName': 'other', 'infraType': 'rtc'},
             {'nodeName': 'pod', 'clusterName': 'cluster', 'infraType': 'infer-python'}]
    handler, calls = handler_for(hosts=hosts, files=[{'fileName': 'other.log'}, {'fileName': 'app.log'}])
    with patch('wiserec_cli.commands.service_logs.can_prompt', return_value=True), \
         patch('wiserec_cli.commands.service_logs.click.prompt', side_effect=[2, 2, 2]) as prompt:
        result = invoke(['logs', 'service'], handler)
    assert result.exit_code == 0, result.output
    assert prompt.call_count == 3
    assert result.stdout == '[INFO] line\nsecond'


def test_cancel_has_no_log_request(invoke):
    handler, calls = handler_for()
    with patch('wiserec_cli.commands.service_logs.can_prompt', return_value=True), \
         patch('wiserec_cli.commands.service_logs.click.prompt', side_effect=EOFError):
        result = invoke(['logs', 'service'], handler)
    assert result.exit_code == 130
    assert len(calls) == 1


@pytest.mark.parametrize('infra', ['rtc_python', None, 'unknown'])
def test_unknown_infra_rejected(invoke, infra):
    handler, calls = handler_for(infra)
    result = invoke(['logs', 'service', '--type', 'interface'], handler)
    assert result.exit_code != 0
    assert len(calls) == 1


def test_empty_files(invoke):
    handler, calls = handler_for(files=[])
    result = invoke(['logs', 'service', '--type', 'interface'], handler)
    assert result.exit_code == 0
    assert len(calls) == 2
    assert result.stdout == ''
