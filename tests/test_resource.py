"""资源模板接口契约、业务隔离、框架联查与展示。"""
import inspect
import json
from copy import deepcopy
from io import StringIO
from unittest.mock import Mock, patch

import httpx
import pytest
from rich.console import Console
from typer.testing import CliRunner

from test_webstudio import rt
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.commands.resource import render_list, resource_spec
from wiserec_cli.business import Department, Tenant
from wiserec_cli.models import Credentials
from wiserec_cli.errors import BusinessError
from wiserec_cli.services.resource import ResourceTemplateService

ID = '0d3dc78d-1511-4c45-aaf9-c5d17e830db1'
CONFIG = {'jvm.args': {'HEAP_OPTS': '-Xms1g -Xmx1g'},
          'rtc.properties': {'password': 'original-secret', 'address': '[red]literal[/red]'},
          'additional.group': {'extra': {'retained': True}}}
ITEM = {'dockerId': ID, 'dockerResourceTemplateName': 'template', 'env': 'cn_dev_default',
        'containerSpec': 'spec.yaml', 'appImageName': 'registry/image', 'imageTag': 'tag',
        'businessId': 'pps', 'clusterName': 'cluster', 'createTime': '2026-08-19 10:04:50',
        'updateTime': '2026-09-08T06:54:36.000+00:00', 'status': 0}
LIST = {'result': {'code': 0, 'count': 1, 'resourceTemplateInfoList': [ITEM], 'extra': True}}
DETAIL = {'result': {**ITEM, 'code': 0, 'templateType': 'docker', 'cpu': '1', 'memory': '2G',
    'npu': '0', 'quotaType': 'guaranteed', 'replicas': 100, 'frameworkType': 'rtc',
    'frameworkPkgId': 'framework-id', 'frameworkConfiguration': json.dumps(CONFIG),
    'envs': [{'envKey': 'KEY', 'envValue': 'VALUE'}],
    'hostIpNames': [{'hostName': 'example.local', 'hostIp': '10.1.1.1'}],
    'hostLabels': [{'hostLabelKey': 'host', 'hostLabelValue': '123'}],
    'args': ['/start.sh', '--debug'], 'customStartupCommand': 'sleep 30;', 'sfsLocation': '/sfs',
    'extra': {'preserved': True}}}
FRAMEWORK = {'result': {'code': 0, 'data': {'name': 'PredictionService', 'version': '1.9.1', 'extra': True}}}
DEFAULT = {'pageIndex': 1, 'pageSize': 10, 'quotaType': None, 'env': None,
    'frameworkType': None, 'frameworkPkgId': '', 'frameworkPkgName': '', 'gatewayName': '',
    'resourceType': 'docker', 'dockerResourceTemplateName': '', 'clusterName': None,
    'businessId': 'pps', 'dockerType': None, 'containerSpec': None, 'appImageName': None,
    'imageTag': None, 'domain': None, 'templateType': 'docker'}


@pytest.fixture
def invoke(rt):
    options = {'mix_stderr': False} if 'mix_stderr' in inspect.signature(CliRunner).parameters else {}
    def run(args, handler):
        with patch('wiserec_cli.cli.Runtime', return_value=rt), \
             patch('wiserec_cli.runtime.PlatformClient', side_effect=lambda *a, **kw:
                   PlatformClient(*a, transport=httpx.MockTransport(handler), **kw)):
            return CliRunner(**options).invoke(app, ['--config', str(rt.config.path), 'resource', 'template', *args])
    return run


def test_default_contract(invoke):
    def handler(request):
        assert request.method == 'POST'
        assert request.url.host == 'console.example'
        assert request.url.path == '/ai/backend/mep/resourcetemp/queryList'
        assert request.headers['businessid'] == 'pps'
        assert json.loads(request.content) == DEFAULT
        return httpx.Response(200, json=LIST)
    result = invoke(['list', '-o', 'json'], handler)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == LIST


def test_filters_do_not_switch_connection_environment(invoke):
    def handler(request):
        assert request.url.host == 'console.example'
        assert json.loads(request.content) == {**DEFAULT, 'pageIndex': 2, 'pageSize': 20,
            'env': 'target', 'frameworkType': 'rtc', 'frameworkPkgName': 'framework',
            'dockerResourceTemplateName': 'name', 'resourceType': 'custom', 'templateType': 'other'}
        return httpx.Response(200, json=LIST)
    result = invoke(['list', '--page', '2', '--page-size', '20', '--env', 'target', '--name', 'name',
                     '--framework-type', 'rtc', '--framework-name', 'framework',
                     '--resource-type', 'custom', '--template-type', 'other'], handler)
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize('output', ['table', 'json'])
def test_detail_chain_and_complete_values(invoke, output):
    calls = []
    def handler(request):
        calls.append(request)
        assert request.headers['businessid'] == 'pps'
        if len(calls) == 1:
            assert request.url.path == '/ai/backend/mep/resourcetemp/queryDetail'
            assert json.loads(request.content) == {'dockerId': ID}
            return httpx.Response(200, json=DETAIL)
        assert request.url.path == '/ai/backend/mep/scm/frameworkPkg/queryFrameworkPkgDetail'
        assert json.loads(request.content) == {'frameworkPkgId': 'framework-id'}
        return httpx.Response(200, json=FRAMEWORK)
    result = invoke(['detail', ID, '-o', output], handler)
    assert result.exit_code == 0, result.output
    assert len(calls) == 2
    if output == 'json':
        assert json.loads(result.stdout) == {'resourceTemplate': DETAIL, 'frameworkPackage': FRAMEWORK}
    else:
        for text in ['PredictionService@1.9.1', '1C2G', '核心配额', 'registry/image tag',
                     'original-secret', '[red]literal[/red]', 'additional.group', 'KEY', 'VALUE',
                     '1、基本信息', '2、推理框架', '2.1、推理框架名称', '2.2、参数配置',
                     '2.2.1、jvm.args', '3、扩展信息', '3.1、环境变量', '3.4、启动参数',
                     'example.local', '10.1.1.1', '/start.sh', '--debug', 'sleep 30;', '/sfs', '100']:
            assert text in result.stdout


def test_active_environment_for_both_requests(rt, invoke):
    rt.config._data['profiles'].append({'name': 'dev', 'api_endpoint': 'https://dev.example/dashboard'})
    rt.config._data['current'] = 'dev'
    rt.auth.ensure_credentials.return_value = Credentials.create('dev', 'cookie', 'csrf', 'current-user', 3600)
    rt.business.refresh('dev', 'current-user',
        [Department('d', 'D', (Tenant('dev-business', 'Dev', (), ()),))], browser_business_id='dev-business')
    def handler(request):
        assert request.url.host == 'dev.example'
        assert request.headers['businessid'] == 'dev-business'
        if request.url.path.endswith('queryList'):
            assert json.loads(request.content)['businessId'] == 'dev-business'
            return httpx.Response(200, json=LIST)
        return httpx.Response(200, json=FRAMEWORK if 'frameworkPkg' in request.url.path else DETAIL)
    assert invoke(['list'], handler).exit_code == 0
    assert invoke(['detail', ID], handler).exit_code == 0


def test_narrow_list_keeps_id_and_beijing_time():
    payload = deepcopy(LIST)
    payload['result']['resourceTemplateInfoList'][0]['dockerResourceTemplateName'] = 'long-name-' * 30
    stream = StringIO()
    with patch('wiserec_cli.commands.resource.console', Console(file=stream, width=80, color_system=None)):
        render_list(payload, 1, 10, 'table')
    assert ID in stream.getvalue()
    with patch('wiserec_cli.commands.resource.console') as mocked:
        render_list(payload, 1, 10, 'table')
    table = mocked.print.call_args_list[0].args[0]
    assert table.columns[0].width == table.columns[0].min_width == table.columns[0].max_width == 36
    assert table.columns[0].no_wrap and table.columns[0].overflow == 'ignore'
    cells = [str(column._cells[0]) for column in table.columns]
    assert '2026-09-08 14:54:36' in cells and '2026-08-19 10:04:50' in cells
    assert '在用' in cells
    assert payload['result']['resourceTemplateInfoList'][0]['updateTime'] == ITEM['updateTime']


@pytest.mark.parametrize('data,expected', [({'cpu': '1', 'memory': '2G', 'npu': '0'}, '1C2G'),
    ({'cpu': '4', 'memory': '8G', 'npu': '1'}, '4C8G1NPU'),
    ({'cpu': '0.5', 'memory': '1G', 'npu': 0}, '0.5C1G'), ({}, '-')])
def test_spec(data, expected):
    assert resource_spec(data) == expected


@pytest.mark.parametrize('payload', [{}, {'result': None}, {'result': {'code': False}},
    {'result': {'code': 2, 'des': 'denied'}}, {'result': {'code': 0, 'count': True, 'resourceTemplateInfoList': []}},
    {'result': {'code': 0, 'count': -1, 'resourceTemplateInfoList': []}},
    {'result': {'code': 0, 'count': 1, 'resourceTemplateInfoList': [None]}}])
def test_bad_list_response(invoke, payload):
    result = invoke(['list', '-o', 'json'], lambda r: httpx.Response(200, json=payload))
    assert result.exit_code == 1 and not result.stdout


@pytest.mark.parametrize('args', [['list', '--page', '0'], ['list', '--page-size', '0'],
    ['list', '-o', 'yaml'], ['detail', ' '], ['list', '--quota-type', 'guaranteed'],
    ['list', '--business-id', 'other']])
def test_bad_arguments_no_requests(invoke, args):
    handler = Mock()
    assert invoke(args, handler).exit_code != 0
    handler.assert_not_called()


def test_empty_page(invoke):
    result = invoke(['list', '--page', '3'], lambda r: httpx.Response(200,
        json={'result': {'code': 0, 'count': 0, 'resourceTemplateInfoList': []}}))
    assert result.exit_code == 0
    assert '暂无容器资源模板' in result.stdout and '第 3 页' in result.stdout


def test_no_framework_and_missing_fields(invoke):
    handler = Mock(return_value=httpx.Response(200, json={'result': {'code': 0}}))
    result = invoke(['detail', ID], handler)
    assert result.exit_code == 0 and '未关联推理框架' in result.stdout
    assert '暂无参数配置' in result.stdout
    assert handler.call_count == 1


@pytest.mark.parametrize('payload', [{'result': {'code': 9, 'des': 'denied'}},
    {'result': {'code': 0, 'data': {}}}, {'result': {'code': False}}])
def test_framework_failure_keeps_detail(invoke, payload):
    def handler(request):
        return httpx.Response(200, json=payload if 'frameworkPkg' in request.url.path else DETAIL)
    result = invoke(['detail', ID], handler)
    assert result.exit_code == 1
    assert 'sleep 30;' in result.stdout
    assert '推理框架查询失败' in result.stderr


def test_malformed_config_preserves_other_detail_and_raw_json(invoke):
    payload = deepcopy(DETAIL)
    payload['result']['frameworkConfiguration'] = '{bad json'
    def handler(request):
        return httpx.Response(200, json=FRAMEWORK if 'frameworkPkg' in request.url.path else payload)
    result = invoke(['detail', ID], handler)
    assert result.exit_code == 1 and '参数配置解析失败' in result.stdout
    assert 'sleep 30;' in result.stdout
    result = invoke(['detail', ID, '-o', 'json'], handler)
    assert result.exit_code == 0
    assert json.loads(result.stdout)['resourceTemplate'] == payload


def test_framework_authentication_refresh_is_not_swallowed(invoke, rt):
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if len(calls) == 2:
            return httpx.Response(401)
        return httpx.Response(200, json=FRAMEWORK if 'frameworkPkg' in request.url.path else DETAIL)
    result = invoke(['detail', ID, '-o', 'json'], handler)
    assert result.exit_code == 0, result.output
    assert len(calls) == 4
    assert json.loads(result.stdout)['frameworkPackage'] == FRAMEWORK
    assert rt.auth.ensure_credentials.call_args.kwargs['force_refresh'] is True


def test_business_mismatch_prevents_requests(rt, invoke):
    data = json.loads(rt.business.path.read_text())
    data['profiles']['prod']['selected']['businessId'] = 'wrong'
    rt.business.path.write_text(json.dumps(data))
    handler = Mock()
    assert invoke(['list'], handler).exit_code == 1
    handler.assert_not_called()


def test_no_business_service():
    client = Mock(business_id='')
    service = ResourceTemplateService(client)
    for operation in [lambda: service.list_templates(), lambda: service.detail(ID), lambda: service.framework('id')]:
        with pytest.raises(BusinessError):
            operation()
    client.request.assert_not_called()


def test_default_output_and_permissions(rt, invoke):
    rt.config._data['profiles'][0]['output_format'] = 'json'
    result = invoke(['list'], lambda r: httpx.Response(200, json=LIST))
    assert json.loads(result.stdout) == LIST
    handler = Mock()
    with patch('wiserec_cli.runtime.check_access', side_effect=BusinessError('denied')):
        assert invoke(['detail', ID], handler).exit_code == 1
    handler.assert_not_called()


@pytest.mark.parametrize('status', [403, 500])
def test_http_failure(invoke, status):
    result = invoke(['list', '-o', 'json'], lambda r: httpx.Response(status, text='unavailable'))
    assert result.exit_code == 1 and not result.stdout


@pytest.mark.parametrize('payload', [{}, {'result': []}, {'result': {'code': '0'}}, {'result': {'code': 9}}])
def test_invalid_detail_stops_framework_request(invoke, payload):
    handler = Mock(return_value=httpx.Response(200, json=payload))
    result = invoke(['detail', ID, '-o', 'json'], handler)
    assert result.exit_code == 1 and not result.stdout
    assert handler.call_count == 1


def test_framework_failure_json_is_complete(invoke):
    def handler(request):
        return httpx.Response(500) if 'frameworkPkg' in request.url.path else httpx.Response(200, json=DETAIL)
    result = invoke(['detail', ID, '-o', 'json'], handler)
    assert result.exit_code == 1
    assert json.loads(result.stdout) == {'resourceTemplate': DETAIL, 'frameworkPackage': None}


def test_stopped_status_and_elastic_quota(invoke):
    payload = deepcopy(DETAIL)
    payload['result']['quotaType'] = 'other'
    payload['result']['npu'] = '1'
    result = invoke(['detail', ID], lambda r: httpx.Response(200,
        json=FRAMEWORK if 'frameworkPkg' in r.url.path else payload))
    assert result.exit_code == 0
    assert '弹性配额' in result.stdout and '1C2G1NPU' in result.stdout
    payload = deepcopy(LIST)
    payload['result']['resourceTemplateInfoList'][0]['status'] = 1
    with patch('wiserec_cli.commands.resource.console') as mocked:
        render_list(payload, 1, 10, 'table')
    table = mocked.print.call_args_list[0].args[0]
    assert str(table.columns[-1]._cells[0]) == '停用'


@pytest.mark.parametrize('resource_type,framework_type,expected_resource,expected_framework', [
    ('docker', 'rtc', '容器', '推理框架'),
    ('vm', 'gateway', '虚拟机', '网关框架'),
    ('other', 'algo', '虚拟机', '算子框架'),
    (None, None, '-', '-'),
    ('docker', 'custom-framework', '容器', 'custom-framework'),
])
def test_detail_type_translations(resource_type, framework_type, expected_resource, expected_framework):
    from wiserec_cli.commands.resource import render_detail
    payload = deepcopy(DETAIL)
    payload['result'].update(templateType=resource_type, frameworkType=framework_type)
    with patch('wiserec_cli.commands.resource.console') as mocked:
        render_detail(payload, FRAMEWORK, 'table')
    table = mocked.print.call_args_list[1].args[0]
    fields = {str(key): str(val) for key, val in zip(table.columns[0]._cells, table.columns[1]._cells)}
    assert fields['资源类型'] == expected_resource
    assert fields['框架类型'] == expected_framework
    # 人工展示的转换不得改变原始响应或 JSON 数据
    assert payload['result']['templateType'] == resource_type
    assert payload['result']['frameworkType'] == framework_type


def test_detail_tables_have_no_numbering_columns():
    from wiserec_cli.commands.resource import render_detail
    with patch('wiserec_cli.commands.resource.console') as mocked:
        render_detail(DETAIL, FRAMEWORK, 'table')
    tables = [call.args[0] for call in mocked.print.call_args_list if hasattr(call.args[0], 'columns')]
    assert len(tables) == 8
    assert all(column.header != '编号' for table in tables for column in table.columns)
    assert [column.header for column in tables[0].columns] == ['字段', '值']
    assert [column.header for column in tables[-1].columns] == ['参数']
