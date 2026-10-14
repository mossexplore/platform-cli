"""部署模板查询的请求契约、关联过滤和展示。"""
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
from wiserec_cli.commands.deployment import display, render_list, render_detail
from wiserec_cli.business import Department, Tenant
from wiserec_cli.models import Credentials
from wiserec_cli.errors import BusinessError
from wiserec_cli.services.deployment import DeploymentTemplateService

ID = 'f6a91681-da0a-441d-a5e1-48c507d6aac4'
COMPONENTS = [{'name': 'Custom', 'version': '1', 'businessId': 'template-business'},
              {'name': 'Common', 'version': '2', 'businessId': 'common'}]
TEMPLATE = {'deployTemplateId': ID, 'deployTemplateName': '[red]literal[/red]',
    'deployTemplateType': 'docker', 'businessId': 'template-business', 'env': 'target-env',
    'dockerResourceTemplate': ['first', 'second'], 'defaultFlag': 0, 'isSystem': '0',
    'workNum': 4, 'threadNum': 1, 'executeLimit': '102', 'serviceTimeout': 101,
    'inferenceType': 'online', 'description': 'description', 'comptPkgInfoList': COMPONENTS,
    'createTime': 1781764655000, 'updateTime': 1781764655000,
    'healthType': 'httpGet', 'healthPath': 'healthvllm', 'startTimeOut': '120',
    'healthCheckTimeout': '102', 'initialDelaySeconds': '103', 'periodSeconds': '104',
    'failureThreshold': '105', 'terminationGracePeriodSeconds': '106', 'extra': {'keep': True}}
LIST = {'result': {'code': 0, 'count': 6, 'deployTemplates': [TEMPLATE]}, 'meta': {'uuid': 'trace'}}
DETAIL = {'result': {'code': 0, 'template': TEMPLATE}, 'extra': True}
DEFAULT = {'pageIndex': 1, 'pageSize': 10, 'inferenceType': None, 'env': None,
    'frameworkType': None, 'gatewayName': None, 'isSystem': None, 'frameworkPkgId': '',
    'frameworkPkgName': '', 'deployTemplateType': None, 'deployTemplateName': None,
    'businessId': 'pps', 'componentName': None, 'componentVersion': None}


def resource(name):
    return {'dockerResourceTemplateName': name, 'dockerId': name + '-id', 'containerSpec': 'spec.yaml',
            'appImageName': 'registry/image', 'imageTag': 'tag', 'clusterName': 'cluster',
            'replicas': 100, 'status': 0, 'createTime': '2026-08-19 10:04:50',
            'updateTime': '2026-09-08T06:54:36.000+00:00', 'extra': True}


def resources(items):
    return {'result': {'code': 0, 'resourceTemplateInfoList': items}, 'extra': 'preserved'}


@pytest.fixture
def invoke(rt):
    options = {'mix_stderr': False} if 'mix_stderr' in inspect.signature(CliRunner).parameters else {}
    def run(args, handler):
        with patch('wiserec_cli.cli.Runtime', return_value=rt), \
             patch('wiserec_cli.runtime.PlatformClient', side_effect=lambda *a, **kw:
                   PlatformClient(*a, transport=httpx.MockTransport(handler), **kw)):
            return CliRunner(**options).invoke(app, ['--config', str(rt.config.path), 'deployment', 'template', *args])
    return run


def test_list_default_contract(invoke):
    def handler(request):
        assert request.method == 'POST'
        assert request.url.host == 'console.example'
        assert request.url.path == '/ai/backend/mep/scm/deploytemplate/queryList'
        assert request.headers['businessid'] == 'pps'
        assert json.loads(request.content) == DEFAULT
        return httpx.Response(200, json=LIST)
    result = invoke(['list', '-o', 'json'], handler)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == LIST


def test_filters_and_page(invoke):
    def handler(request):
        assert request.url.host == 'console.example'
        assert json.loads(request.content) == {**DEFAULT, 'pageIndex': 2, 'pageSize': 20,
            'env': 'other', 'frameworkType': 'rtc', 'frameworkPkgName': 'PredictionService',
            'deployTemplateName': 'deployment-name'}
        return httpx.Response(200, json=LIST)
    assert invoke(['list', '--page', '2', '--page-size', '20', '--env', 'other',
                   '--framework-type', 'rtc', '--framework-name', 'PredictionService',
                   '--name', 'deployment-name'], handler).exit_code == 0


@pytest.mark.parametrize('output', ['json', 'table'])
def test_detail_exact_matching_and_three_field_requests(invoke, output):
    calls, responses = [], []
    def handler(request):
        assert request.method == 'POST'
        assert request.headers['businessid'] == 'pps'
        calls.append(request.url.path)
        if len(calls) == 1:
            assert request.url.path == '/ai/backend/mep/scm/deploytemplate/queryDetail'
            assert json.loads(request.content) == {'deployTemplateId': ID}
            return httpx.Response(200, json=DETAIL)
        name = ['first', 'second'][len(calls) - 2]
        assert request.url.path == '/ai/backend/mep/resourcetemp/queryList'
        assert json.loads(request.content) == {'templateType': 'docker', 'businessId': 'template-business',
                                              'dockerResourceTemplateName': name}
        response = resources([resource(name + '-fuzzy'), resource(name), resource(name.upper()), resource(' ' + name)])
        responses.append(response)
        return httpx.Response(200, json=response)
    result = invoke(['detail', ID, '-o', output], handler)
    assert result.exit_code == 0, result.output
    assert len(calls) == 3
    if output == 'json':
        assert json.loads(result.stdout) == {'deploymentTemplate': DETAIL, 'resourceTemplates': [
            {'requestedName': name, 'response': response, 'exactMatches': [resource(name)], 'error': None}
            for name, response in zip(['first', 'second'], responses)]}
    else:
        for text in ['[red]literal[/red]', 'Custom@1', 'Common@2', 'healthvllm', 'description', '100', '在用']:
            assert text in result.stdout
        assert all(title in result.stdout for title in ['1、基本信息', '2、健康检查参数', '3、容器资源模板'])
        assert '-fuzzy' not in result.stdout
        assert '容器类别' not in result.stdout


def test_active_profile_header_and_body(rt, invoke):
    rt.config._data['profiles'].append({'name': 'dev', 'api_endpoint': 'https://dev.example/dashboard'})
    rt.config._data['current'] = 'dev'
    rt.auth.ensure_credentials.return_value = Credentials.create('dev', 'cookie', 'csrf', 'current-user', 3600)
    rt.business.refresh('dev', 'current-user', [Department('d', 'D', (Tenant('dev-business', 'Dev', (), ()),))],
                        browser_business_id='dev-business')
    def handler(request):
        assert request.url.host == 'dev.example'
        assert request.headers['businessid'] == 'dev-business'
        if request.url.path.endswith('deploytemplate/queryList'):
            assert json.loads(request.content)['businessId'] == 'dev-business'
            return httpx.Response(200, json=LIST)
        if request.url.path.endswith('deploytemplate/queryDetail'):
            return httpx.Response(200, json=DETAIL)
        assert json.loads(request.content)['businessId'] == 'template-business'
        return httpx.Response(200, json=resources([resource(json.loads(request.content)['dockerResourceTemplateName'])]))
    assert invoke(['list'], handler).exit_code == 0
    assert invoke(['detail', ID], handler).exit_code == 0


def test_render_list_fixed_id_and_time():
    stream = StringIO()
    with patch('wiserec_cli.commands.deployment.console', Console(file=stream, width=80, color_system=None)):
        render_list(LIST, 1, 10, 'table')
    assert ID in stream.getvalue()
    with patch('wiserec_cli.commands.deployment.console') as mocked:
        render_list(LIST, 1, 10, 'table')
    table = mocked.print.call_args_list[0].args[0]
    assert table.columns[0].width == table.columns[0].min_width == table.columns[0].max_width == 36
    assert table.columns[0].no_wrap and table.columns[0].overflow == 'ignore'
    cells = [str(column._cells[0]) for column in table.columns]
    assert cells[4] == 'Custom@1,Common@2'
    assert cells[6] == 'first,second'
    assert cells[9] == '2026-06-18 14:37:35'
    assert cells[8] == cells[11] == '否'


@pytest.mark.parametrize('raw,expected', [(0, '否'), ('0', '否'), (1, '是'), ('1', '是'), (None, '-'), ('', '-')])
def test_flag(raw, expected):
    for key in ['defaultFlag', 'isSystem']:
        assert display(key, {key: raw}) == expected


def test_component_classification():
    assert display('customComponents', TEMPLATE) == 'Custom@1'
    assert display('commonComponents', TEMPLATE) == 'Common@2'
    assert display('comptPkgInfoList', {}) == '-'


def test_detail_fields_and_resource_order():
    payload = {'deploymentTemplate': DETAIL, 'resourceTemplates': [
        {'requestedName': name, 'response': None, 'exactMatches': [resource(name)], 'error': None}
        for name in ['first', 'second']]}
    with patch('wiserec_cli.commands.deployment.console') as mocked:
        render_detail(payload, 'table')
    tables = [c.args[0] for c in mocked.print.call_args_list if hasattr(c.args[0], 'columns')]
    assert len(tables) == 3
    basic = {str(k): str(v) for k, v in zip(tables[0].columns[0]._cells, tables[0].columns[1]._cells)}
    assert basic['单服务实例最大能承受并发数（超过了会触发流控）'] == '102'
    assert basic['服务调用方最大容忍超时时间（ms）'] == '101'
    assert basic['组件包'] == 'Custom@1' and basic['公共组件包（平台提供）'] == 'Common@2'
    assert len(tables[1].columns[0]._cells) == 8
    assert str(tables[1].columns[1]._cells[0]) == 'http'
    assert [str(c) for c in tables[2].columns[0]._cells] == ['first', 'second']
    assert len(tables[2].columns) == 9
    assert all(column.header != '编号' for table in tables for column in table.columns)


@pytest.mark.parametrize('args', [['list', '--page', '0'], ['list', '--page-size', '0'],
    ['list', '--is-system', '0'], ['list', '--business-id', 'other'],
    ['list', '--inference-type', 'online'], ['list', '-o', 'yaml'], ['detail', ' ']])
def test_invalid_arguments_no_request(invoke, args):
    handler = Mock()
    assert invoke(args, handler).exit_code != 0
    handler.assert_not_called()


@pytest.mark.parametrize('payload', [{}, {'result': None}, {'result': {'code': False}},
    {'result': {'code': 3}}, {'result': {'code': 0, 'count': True, 'deployTemplates': []}},
    {'result': {'code': 0, 'count': -1, 'deployTemplates': []}},
    {'result': {'code': 0, 'count': 1, 'deployTemplates': [None]}}])
def test_invalid_list_response(invoke, payload):
    result = invoke(['list', '-o', 'json'], lambda r: httpx.Response(200, json=payload))
    assert result.exit_code == 1 and not result.stdout


@pytest.mark.parametrize('payload', [{}, {'result': {'code': 0}}, {'result': {'code': 0, 'template': []}},
    {'result': {'code': '0', 'template': {}}},
    {'result': {'code': 0, 'template': {'dockerResourceTemplate': 'bad'}}},
    {'result': {'code': 0, 'template': {'dockerResourceTemplate': ['name']}}}])
def test_invalid_detail_stops_resources(invoke, payload):
    handler = Mock(return_value=httpx.Response(200, json=payload))
    result = invoke(['detail', ID, '-o', 'json'], handler)
    assert result.exit_code == 1 and not result.stdout
    assert handler.call_count == 1


@pytest.mark.parametrize('case', ['missing', 'ambiguous', 'http', 'malformed', 'code'])
def test_partial_failure_continues_and_preserves_json(invoke, case):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(200, json=DETAIL)
        if len(calls) == 2:
            if case == 'http':
                return httpx.Response(500)
            items = [] if case == 'missing' else [resource('first'), resource('first')]
            payload = resources(items)
            if case == 'malformed':
                payload['result']['resourceTemplateInfoList'] = [None]
            if case == 'code':
                payload['result']['code'] = 9
            return httpx.Response(200, json=payload)
        return httpx.Response(200, json=resources([resource('second')]))
    result = invoke(['detail', ID, '-o', 'json'], handler)
    assert result.exit_code == 1 and len(calls) == 3
    data = json.loads(result.stdout)
    assert data['deploymentTemplate'] == DETAIL
    assert data['resourceTemplates'][0]['error']
    assert data['resourceTemplates'][1]['exactMatches'] == [resource('second')]
    assert data['resourceTemplates'][1]['error'] is None


def test_empty_list_and_no_associations(invoke):
    result = invoke(['list'], lambda r: httpx.Response(200, json={'result': {'code': 0, 'count': 0, 'deployTemplates': []}}))
    assert result.exit_code == 0 and '暂无部署模板' in result.stdout
    handler = Mock(return_value=httpx.Response(200, json={'result': {'code': 0, 'template': {}}}))
    result = invoke(['detail', ID], handler)
    assert result.exit_code == 0 and '暂无关联容器资源模板' in result.stdout
    assert handler.call_count == 1


def test_auth_refresh_in_resource_chain(rt, invoke):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 2:
            return httpx.Response(401)
        if request.url.path.endswith('queryDetail'):
            return httpx.Response(200, json=DETAIL)
        return httpx.Response(200, json=resources([resource(json.loads(request.content)['dockerResourceTemplateName'])]))
    result = invoke(['detail', ID, '-o', 'json'], handler)
    assert result.exit_code == 0, result.output
    assert len(calls) == 5
    assert rt.auth.ensure_credentials.call_args.kwargs['force_refresh'] is True
    assert json.loads(result.stdout)['deploymentTemplate'] == DETAIL


def test_default_output_and_access_denied(rt, invoke):
    rt.config._data['profiles'][0]['output_format'] = 'json'
    assert json.loads(invoke(['list'], lambda r: httpx.Response(200, json=LIST)).stdout) == LIST
    handler = Mock()
    with patch('wiserec_cli.runtime.check_access', side_effect=BusinessError('denied')):
        assert invoke(['list'], handler).exit_code == 1
    handler.assert_not_called()


def test_selection_mismatch(rt, invoke):
    data = json.loads(rt.business.path.read_text())
    data['profiles']['prod']['selected']['businessId'] = 'wrong'
    rt.business.path.write_text(json.dumps(data))
    handler = Mock()
    assert invoke(['list'], handler).exit_code == 1
    handler.assert_not_called()


def test_no_business():
    client = Mock(business_id='')
    service = DeploymentTemplateService(client)
    for operation in [lambda: service.list_templates(), lambda: service.detail(ID)]:
        with pytest.raises(BusinessError):
            operation()
    client.request.assert_not_called()


@pytest.mark.parametrize('name', ['TEMPLATE_NAME', '中文模板', ''])
def test_name_filter(invoke, name):
    def handler(request):
        assert json.loads(request.content) == {**DEFAULT, 'deployTemplateName': name}
        assert request.headers['businessid'] == 'pps'
        return httpx.Response(200, json=LIST)
    result = invoke(['list', '--name', name, '-o', 'json'], handler)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == LIST


@pytest.mark.parametrize('raw,expected', [('httpGet', 'http'), ('tcpSocket', 'tcp'), (None, '-')])
def test_health_type_display(raw, expected):
    assert display('healthType', {'healthType': raw}) == expected


@pytest.mark.parametrize('raw,expected', [('online', '在线推理'), ('offline', '离线推理'),
                                         ('other', 'other'), (None, '-')])
def test_detail_inference_type_translation(raw, expected):
    detail = deepcopy(DETAIL)
    detail['result']['template']['inferenceType'] = raw
    payload = {'deploymentTemplate': detail, 'resourceTemplates': []}
    with patch('wiserec_cli.commands.deployment.console') as mocked:
        render_detail(payload, 'table')
    table = mocked.print.call_args_list[1].args[0]
    fields = {str(k): str(v) for k, v in zip(table.columns[0]._cells, table.columns[1]._cells)}
    assert fields['推理类型'] == expected
    assert detail['result']['template']['inferenceType'] == raw
    assert display('inferenceType', {'inferenceType': raw}) == (str(raw) if raw is not None else '-')


@pytest.mark.parametrize('raw,expected', [('docker', '容器'), ('vm', '虚拟机'),
                                         ('other', '虚拟机'), (None, '-'), ('', '-')])
def test_detail_resource_type_translation(raw, expected):
    detail = deepcopy(DETAIL)
    detail['result']['template']['deployTemplateType'] = raw
    with patch('wiserec_cli.commands.deployment.console') as mocked:
        render_detail({'deploymentTemplate': detail, 'resourceTemplates': []}, 'table')
    table = mocked.print.call_args_list[1].args[0]
    fields = {str(k): str(v) for k, v in zip(table.columns[0]._cells, table.columns[1]._cells)}
    assert fields['资源模板类型'] == expected
    assert detail['result']['template']['deployTemplateType'] == raw
    assert display('deployTemplateType', {'deployTemplateType': raw}) == (raw or '-')
