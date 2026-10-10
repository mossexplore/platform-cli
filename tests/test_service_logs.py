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
    hosts = [{'nodeName': str(i), 'clusterName': 'other', 'infraType': 'infer-python'} for i in range(10)]
    hosts.append({'nodeName': 'pod', 'clusterName': 'cluster', 'infraType': 'infer-python'})
    handler, calls = handler_for(hosts=hosts)
    result = invoke(['logs', 'service', '--pod', 'pod', '--cluster-name', 'cluster', '--type', 'interface', '--file', 'app.log'], handler)
    assert result.exit_code == 0, result.output
    assert [body['pageIndex'] for path, body in calls if path.endswith('queryServiceHostList')] == [1]


@pytest.mark.parametrize('extra', [[], ['--type', 'bad']])
def test_unresolved_or_invalid_selection_stops(invoke, extra):
    handler, calls = handler_for()
    result = invoke(['logs', 'service', '--no-input'] + extra, handler)
    assert result.exit_code != 0
    assert len(calls) == 1


@pytest.mark.parametrize('extra', [
    ['--file', 'a'], ['-k', 'error'], ['-n', '200'],
    ['--search-order', 'tail'], ['--grep-scope', 'C'], ['--grep-line', '0'],
])
def test_list_conflicts_before_request(invoke, extra):
    handler, calls = handler_for()
    result = invoke(['logs', 'service', '--list'] + extra, handler)
    assert result.exit_code != 0
    assert calls == []
    assert '--list 不能与' in result.stderr


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


@pytest.mark.parametrize('extra', [['--pod', 'pod'], ['--cluster-name', 'cluster']])
def test_pod_cluster_pair_required(invoke, extra):
    handler, calls = handler_for()
    result = invoke(['logs', 'service'] + extra, handler)
    assert result.exit_code != 0
    assert calls == []


@pytest.mark.parametrize('answers,expected_pages', [(['1'], [1]), (['n', 'p', 'n', '1'], [1, 2])])
def test_lazy_pages_and_previous_page_cache(invoke, answers, expected_pages):
    hosts = [{'nodeName': 'pod', 'clusterName': 'cluster', 'infraType': 'infer-python'} for _ in range(11)]
    handler, calls = handler_for(hosts=hosts)
    with patch('wiserec_cli.commands.service_logs.can_prompt', return_value=True), \
         patch('wiserec_cli.commands.service_logs.click.prompt', side_effect=answers):
        result = invoke(['logs', 'service', '--type', 'interface'], handler)
    assert result.exit_code == 0, result.stderr
    assert [b['pageIndex'] for p, b in calls if p.endswith('queryServiceHostList')] == expected_pages


def test_multiple_hosts_no_input_stops_at_first_page(invoke):
    handler, calls = handler_for(hosts=[{'nodeName': 'other'}] * 20)
    result = invoke(['logs', 'service', '--no-input'], handler)
    assert result.exit_code != 0
    assert len(calls) == 1
    assert '--cluster-name' in result.stderr


def test_explicit_pod_uses_first_host_type_without_matching(invoke):
    handler, calls = handler_for(hosts=[{'nodeName': 'unrelated', 'infraType': 'infer-python'}] * 20)
    result = invoke(['logs', 'service', '--pod', 'pod', '--cluster-name', 'cluster', '--type', 'interface'], handler)
    assert result.exit_code == 0, result.stderr
    assert len(calls) == 3


def test_paging_quit(invoke):
    handler, calls = handler_for(hosts=[{'nodeName': 'pod'}] * 20)
    with patch('wiserec_cli.commands.service_logs.can_prompt', return_value=True), \
         patch('wiserec_cli.commands.service_logs.click.prompt', return_value='q'):
        result = invoke(['logs', 'service'], handler)
    assert result.exit_code == 130
    assert len(calls) == 1


def test_host_table_columns_values_and_beijing_time():
    from wiserec_cli.commands.service_logs import host_table
    table = host_table([{'clusterName': 'cluster', 'nodeName': '[red]pod[/red]',
                        'nodeHost': '10.0.0.1', 'hostIp': '10.0.0.2', 'health_status': 0,
                        'create_time': '2026-09-08T06:54:36.000+00:00',
                        'update_time': '2026-09-08T07:54:36.000Z'}, {}])
    assert [c.header for c in table.columns] == [
        '编号', '集群', 'pod名称', 'podIP', '主机IP', '状态', '创建时间', '更新时间']
    assert [str(c._cells[0]) for c in table.columns] == [
        '1', 'cluster', '[red]pod[/red]', '10.0.0.1', '10.0.0.2', '正常',
        '2026-09-08 14:54:36', '2026-09-08 15:54:36']
    assert [str(c._cells[1]) for c in table.columns] == ['2'] + ['-'] * 7


def test_category_and_file_tables_are_not_duplicated(invoke):
    from wiserec_cli.commands.service_logs import LOG_TYPES
    from rich.table import Table
    handler, _ = handler_for(files=[{'fileName': 'other.log'}, {'fileName': 'app.log'}])
    events = []
    def printed(value):
        if isinstance(value, Table):
            events.append(('table', [column.header for column in value.columns]))
            if value.columns[1].header == '日志类别':
                assert [str(v) for v in value.columns[1]._cells] == list(LOG_TYPES['infer-python'])
        else:
            assert '1. ' not in str(value) and '2. ' not in str(value)
    def prompt(label, **kwargs):
        events.append(('prompt', label))
        return 2
    with patch('wiserec_cli.commands.service_logs.can_prompt', return_value=True), \
         patch('wiserec_cli.commands.service_logs.error_console.print', side_effect=printed), \
         patch('wiserec_cli.commands.service_logs.click.prompt', side_effect=prompt):
        result = invoke(['logs', 'service'], handler)
    assert result.exit_code == 0, result.output
    assert events == [
        ('table', ['编号', '日志类别']), ('prompt', '请选择日志类别'),
        ('table', ['编号', '文件名称', '大小', '修改时间']), ('prompt', '请选择日志文件')]
    assert result.stdout == '[INFO] line\nsecond'
