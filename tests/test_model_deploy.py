"""模型部署完整请求契约、确认流程和不重复提交保障。"""
import inspect
import json
from copy import deepcopy
from unittest.mock import Mock, patch
from uuid import UUID

import httpx
import pytest
from typer.testing import CliRunner

from test_webstudio import rt
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.business import Department, Tenant, Team
from wiserec_cli.models import Credentials
from wiserec_cli.services.model_deploy import PUBLISH_PATH

MODEL_ID = '4dc10845-cacb-4e6c-8e0d-8c6733cec9da'
TEMPLATE_ID = 'f6a91681-da0a-441d-a5e1-48c507d6aac4'
MODEL = {'code': 0, 'modelId': MODEL_ID, 'source': 'model-clone', 'sourceId': 'source',
    'sourceEnv': '', 'modelTag': 0, 'modelHistoryList': [], 'modelName': 'model-name',
    'modelVersion': 'model-version', 'pkgId': 'model-package', 'modelType': 'python',
    'pkgSize': 12158958, 'pkgLocation': 'model-bucket', 'businessId': 'pps', 'teamId': '',
    'storeType': 'OBS', 'tags': [{'tag': 'recommend'}], 'extra': 'retained-in-source'}
COMPONENT = {'comptPkgId': 'component', 'name': 'Common', 'version': 'component-version',
    'nspPkgId': 'component-object', 'nspPkgLocation': 'component-bucket', 'businessId': 'common',
    'comptPkgFileName': 'component.jar'}
TEMPLATE = {'deployTemplateId': TEMPLATE_ID, 'deployTemplateName': 'deploy-template',
    'deployTemplateType': 'docker', 'businessId': 'pps', 'dockerResourceTemplate': ['area-a', 'area-b'],
    'inferenceType': 'online', 'serviceTimeout': 3000, 'executeLimit': '100', 'env': 'target-env',
    'comptPkgInfoList': [COMPONENT], 'healthType': 'tcpSocket', 'healthPath': 'health-path',
    'terminationGracePeriodSeconds': '106', 'initialDelaySeconds': 0}
CONFIG = {'rtc.properties': {'secret': 'original-secret', 'enabled': False}}
FRAMEWORK = {'code': 0, 'data': {'name': 'framework', 'version': 'framework-version',
    'pkgStorageId': 'framework-object', 'pkgStorageLocation': 'framework-bucket', 'storageType': 'OBS'}}
TENANT = {'code': 0, 'data': {'tenantServiceEntityList': [{'serviceGroup': 'first-group'}, {'serviceGroup': 'second-group'}]}}
SUCCESS = {'result': {'code': 0, 'des': 'deploy success', 'serviceId': 'service-id'}}


def resource(name):
    return {'code': 0, 'dockerResourceTemplateName': name, 'quotaType': 'guaranteed',
            'containerSpec': 'spec.yaml', 'clusterName': name + '-cluster', 'appImageName': 'image',
            'imageTag': 'image-tag', 'cpu': '2', 'memory': '8G', 'gpu': '0', 'npu': '1',
            'replicas': 100, 'frameworkPkgId': 'framework-id', 'frameworkConfiguration': json.dumps(CONFIG),
            'hostLabels': [{'hostLabelKey': 'host', 'hostLabelValue': 'worker'}],
            'hostIpNames': [{'hostName': 'host.example', 'hostIp': '10.0.0.1'}],
            'envs': [{'envKey': 'KEY', 'envValue': 'VALUE'}], 'sfsLocation': '/sfs',
            'args': ['/start.sh'], 'customStartupCommand': 'sleep 30;'}


@pytest.fixture
def invoke(rt):
    options = {'mix_stderr': False} if 'mix_stderr' in inspect.signature(CliRunner).parameters else {}
    def run(args, handler, *, interactive=False, input=None):
        with patch('wiserec_cli.cli.Runtime', return_value=rt), \
             patch('wiserec_cli.commands.model_deploy.interactive_input', return_value=interactive), \
             patch('wiserec_cli.cli.ping.auto_start'), \
             patch('wiserec_cli.runtime.PlatformClient', side_effect=lambda *a, **kw:
                   PlatformClient(*a, transport=httpx.MockTransport(handler), **kw)):
            return CliRunner(**options).invoke(app, ['--config', str(rt.config.path), 'model', 'deploy',
                                                       MODEL_ID, '--template', TEMPLATE_ID, *args], input=input)
    return run


@pytest.fixture
def backend():
    class Backend:
        def __init__(self):
            self.calls = []
            self.model, self.template = deepcopy(MODEL), deepcopy(TEMPLATE)
            self.resources = {name: resource(name) for name in TEMPLATE['dockerResourceTemplate']}
            self.framework, self.tenant, self.result = deepcopy(FRAMEWORK), deepcopy(TENANT), deepcopy(SUCCESS)
            self.publish_error = None
            self.header_business, self.tenant_id, self.host = 'pps', 'pps', 'console.example'
            self.matches = None
        def __call__(self, request):
            self.calls.append(request)
            assert request.url.host == self.host
            assert request.headers['businessid'] == self.header_business
            body = json.loads(request.content) if request.content else None
            path = request.url.path
            if path == '/ai/backend/mep/models/queryDetail':
                assert body == {'modelId': MODEL_ID}
                return httpx.Response(200, json={'result': self.model})
            if path == '/ai/backend/mep/scm/deploytemplate/queryDetail':
                assert body == {'deployTemplateId': TEMPLATE_ID}
                return httpx.Response(200, json={'result': {'code': 0, 'template': self.template}})
            if path == '/ai/backend/mep/resourcetemp/queryList':
                name = body['dockerResourceTemplateName']
                assert body == {'templateType': self.template['deployTemplateType'],
                    'businessId': self.template['businessId'], 'dockerResourceTemplateName': name}
                matches = [{'dockerId': name + '-id', 'dockerResourceTemplateName': name},
                           {'dockerId': 'fuzzy-id', 'dockerResourceTemplateName': name + '-fuzzy'}]
                if self.matches is not None:
                    matches = self.matches
                return httpx.Response(200, json={'result': {'code': 0, 'resourceTemplateInfoList': matches}})
            if path == '/ai/backend/mep/resourcetemp/queryDetail':
                return httpx.Response(200, json={'result': self.resources[body['dockerId'].removesuffix('-id')]})
            if path == '/ai/backend/mep/scm/frameworkPkg/queryFrameworkPkgDetail':
                assert body == {'frameworkPkgId': 'framework-id'}
                return httpx.Response(200, json={'result': self.framework})
            if path == '/ai/user/queryTenantDetail':
                assert request.method == 'GET' and request.url.params['businessId'] == self.tenant_id
                return httpx.Response(200, json={'result': self.tenant})
            assert path == PUBLISH_PATH and request.method == 'POST'
            if self.publish_error:
                return self.publish_error(request)
            return httpx.Response(200, json=self.result)
        @property
        def publishes(self):
            return [request for request in self.calls if request.url.path == PUBLISH_PATH]
    return Backend()


def test_full_publish_contract(invoke, backend):
    result = invoke(['--yes', '-o', 'json'], backend)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == SUCCESS
    assert len(backend.publishes) == 1
    payload = json.loads(backend.publishes[0].content)
    assert payload['version'] == '1.0.0'
    UUID(payload['meta']['uuid'])
    assert payload['data']['modelInfo'] == {
        'modelSource': 'model-clone', 'modelSourceId': 'source', 'modelSourceEnv': '', 'modelTag': 0,
        'modelId': MODEL_ID, 'modelPkgLocationReplicas': [], 'modelName': 'model-name',
        'modelVersion': 'model-version', 'modelPkgId': 'model-package', 'modelType': 'python',
        'modelSize': 12158958, 'modelPkgLocation': 'model-bucket', 'businessId': 'pps',
        'teamId': '', 'storeType': 'OBS', 'tags': [{'tag': 'recommend'}]}
    assert payload['data']['serviceInfo'] == {'inferenceType': 'online', 'serviceId': None,
        'serviceName': 'model-name', 'serviceVersion': 'model-version', 'serviceTimeout': 3000,
        'executeLimit': '100', 'updateMode': '1', 'env': 'target-env'}
    assert payload['data']['comptPkgs'] == [{'comptPkgId': 'component', 'comptPkgName': 'Common',
        'comptPkgVersion': 'component-version', 'nspPkgId': 'component-object',
        'nspPkgLocation': 'component-bucket', 'businessId': 'common', 'comptPkgFileName': 'component.jar'}]
    assert payload['data']['extendConfiguration'] == {'healthCheckTypeInContainer': 'Default',
        'healthPort': '18090', 'alarmWiseEyeScope': 'first-group', 'healthCheckTimeout': '5',
        'startTimeout': '120', 'initialDelaySeconds': '0', 'periodSeconds': '10', 'failureThreshold': '3',
        'healthPath': 'health-path', 'healthType': 'tcpSocket', 'terminationGracePeriodSeconds': 106}
    assert payload['data']['serviceDocument'] == {'description': '', 'requestContent': '', 'responseContent': ''}
    assert payload['eFlowInfo'] == {'actionType': 'service_publish', 'modelInfoList': [
        {'modelName': 'model-name', 'modelVersion': 'model-version'}]}
    assert len(payload['data']['serviceBlocks']) == 2
    for name, block in zip(['area-a', 'area-b'], payload['data']['serviceBlocks']):
        assert block == {'quotaType': 'guaranteed', 'sfsReplicas': [], 'blockName': '', 'description': None,
            'resourceDockerId': name + '-id', 'templateId': 'spec.yaml', 'clusterName': name + '-cluster',
            'imageName': 'image', 'imageVersion': 'image-tag', 'swrInstanceId': None,
            'resourceRequire': {'cpu': '2', 'memory': '8', 'gpu': '0', 'npu': '1', 'replicas': '1'},
            'inferFramework': {'inferFrameId': 'framework-id', 'inferFrameObjectId': 'framework-object',
                'inferFrameBucketId': 'framework-bucket', 'inferFrameStoreType': 'OBS', 'configuration': CONFIG},
            'volumes': [], 'hostLabels': backend.resources[name]['hostLabels'],
            'hostIpNames': backend.resources[name]['hostIpNames'], 'envs': backend.resources[name]['envs'],
            'sfsLocation': '/sfs', 'args': ['/start.sh'], 'customStartupCommand': 'sleep 30;', 'elasticConfig': None}
    assert len([r for r in backend.calls if 'queryFrameworkPkgDetail' in r.url.path]) == 1
    assert '1、基本信息' in result.stderr


@pytest.mark.parametrize('mode,expected', [('default', 'Default'), ('response-code', 'RespCodeMatch'),
                                          ('response-code-and-data', 'RespCodeAndDataMatch')])
def test_options_and_documents(invoke, backend, tmp_path, mode, expected):
    request, response = tmp_path/'request.json', tmp_path/'response.txt'
    request.write_text('{"中文": true}\n', encoding='utf-8')
    response.write_text('raw response\n', encoding='utf-8')
    result = invoke(['--dry-run', '-o', 'json', '--qps', '123', '--update-mode', 'in-place',
        '--health-check-mode', mode, '--health-port', '8080', '--description', '描述',
        '--request-file', str(request), '--response-file', str(response)], backend)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert not backend.publishes
    assert payload['data']['serviceInfo']['updateMode'] == '0'
    assert payload['data']['serviceInfo']['requestLimit'] == 123
    assert payload['data']['extendConfiguration']['healthCheckTypeInContainer'] == expected
    assert payload['data']['extendConfiguration']['healthPort'] == '8080'
    assert payload['data']['serviceDocument'] == {'description': '描述', 'requestContent': '{"中文": true}\n',
                                                'responseContent': 'raw response\n'}
    assert payload['data']['serviceBlocks'][0]['inferFramework']['configuration'] == CONFIG


def test_default_health_values(invoke, backend):
    backend.template.update(healthType='', healthPath=None, healthCheckTimeout='',
                            startTimeOut=None, terminationGracePeriodSeconds='')
    result = invoke(['--dry-run', '-o', 'json'], backend)
    assert result.exit_code == 0, result.output
    health = json.loads(result.stdout)['data']['extendConfiguration']
    assert health['healthType'] == 'httpGet' and health['healthPath'] == 'health'
    assert health['healthCheckTimeout'] == '5' and health['startTimeout'] == '120'
    assert type(health['terminationGracePeriodSeconds']) is int and health['terminationGracePeriodSeconds'] == 10


def test_dry_run_table(invoke, backend):
    result = invoke(['--dry-run'], backend)
    assert result.exit_code == 0, result.output
    assert all(s in result.stdout for s in ['1、基本信息', '2、部署区域', '3、扩展参数', '4、服务文档',
                                          '未提交部署', '2.1、area-a-cluster', '2.2、area-b-cluster', '停用'])
    assert not backend.publishes


def test_noninteractive_requires_yes(invoke, backend):
    result = invoke([], backend)
    assert result.exit_code == 1 and '--yes' in result.stderr
    assert not backend.calls


@pytest.mark.parametrize('answer,expected', [('n\n', 0), ('y\n', 1)])
def test_interactive_confirm(invoke, backend, answer, expected):
    result = invoke([], backend, interactive=True, input=answer)
    assert result.exit_code == 0, result.output
    assert len(backend.publishes) == expected
    assert ('部署成功' in result.stdout) if expected else ('已取消部署' in result.stderr)


@pytest.mark.parametrize('args', [['--update-mode', 'bad'], ['--health-check-mode', 'bad'],
    ['--qps', '0'], ['--health-port', '65536'], ['--template', ' '], ['-o', 'yaml']])
def test_invalid_options_do_not_query(invoke, backend, args):
    assert invoke(['--dry-run', *args], backend).exit_code != 0
    assert not backend.calls


@pytest.mark.parametrize('raw', ['', None, '{}', '{bad', '[]', 'null'])
def test_invalid_framework_config_prevents_publish(invoke, backend, raw):
    backend.resources['area-a']['frameworkConfiguration'] = raw
    result = invoke(['--yes'], backend)
    assert result.exit_code == 1 and not backend.publishes
    assert 'frameworkConfiguration' in result.stderr


@pytest.mark.parametrize('field,value', [('serviceTimeout', None), ('executeLimit', ''),
    ('serviceTimeout', 0), ('periodSeconds', 0), ('terminationGracePeriodSeconds', '1.5')])
def test_missing_or_invalid_service_fields(invoke, backend, field, value):
    backend.template[field] = value
    assert invoke(['--yes'], backend).exit_code == 1
    assert not backend.publishes


@pytest.mark.parametrize('matches', [[], [{'dockerId': 'one', 'dockerResourceTemplateName': 'area-a'},
                                        {'dockerId': 'two', 'dockerResourceTemplateName': 'area-a'}]])
def test_missing_or_ambiguous_resources(invoke, backend, matches):
    backend.matches = matches
    assert invoke(['--yes'], backend).exit_code == 1
    assert not backend.publishes


def test_empty_associations(invoke, backend):
    backend.template['dockerResourceTemplate'] = []
    assert invoke(['--yes'], backend).exit_code == 1 and not backend.publishes


@pytest.mark.parametrize('tenant', [{'code': 0, 'data': {'tenantServiceEntityList': []}},
    {'code': 0, 'data': {'tenantServiceEntityList': [{'serviceGroup': ''}]}}, {'code': 9}])
def test_invalid_tenant(invoke, backend, tenant):
    backend.tenant = tenant
    assert invoke(['--yes'], backend).exit_code == 1 and not backend.publishes


def test_nonzero_result_is_failure_even_when_description_says_success(invoke, backend):
    backend.result = {'result': {'code': 7, 'des': 'deploy success and failed', 'serviceId': 'partial'}}
    result = invoke(['--yes', '-o', 'json'], backend)
    assert result.exit_code == 1
    assert json.loads(result.stdout) == backend.result
    assert 'code=7' in result.stderr
    assert len(backend.publishes) == 1


@pytest.mark.parametrize('result', [{}, {'result': {'code': '0'}}, {'result': {'code': False}}])
def test_malformed_publish_response_is_not_success(invoke, backend, result):
    backend.result = result
    output = invoke(['--yes'], backend)
    assert output.exit_code == 1 and '未确认' in output.stderr
    assert len(backend.publishes) == 1


@pytest.mark.parametrize('failure', ['timeout', '401', '500'])
def test_publish_is_never_automatically_replayed(invoke, backend, rt, failure):
    def error(request):
        if failure == 'timeout':
            raise httpx.ReadTimeout('timeout', request=request)
        return httpx.Response(int(failure))
    backend.publish_error = error
    result = invoke(['--yes'], backend)
    assert result.exit_code == 1 and '结果未确认' in result.stderr
    assert len(backend.publishes) == 1
    assert not any(call.kwargs.get('force_refresh') for call in rt.auth.ensure_credentials.call_args_list)


def test_read_only_authentication_can_refresh(invoke, backend, rt):
    seen = []
    def handler(request):
        seen.append(request)
        if len(seen) == 1:
            return httpx.Response(401)
        return backend(request)
    result = invoke(['--dry-run', '-o', 'json'], handler)
    assert result.exit_code == 0, result.output
    assert rt.auth.ensure_credentials.call_args.kwargs['force_refresh'] is True
    assert not backend.publishes


def test_real_tenant_distinct_from_team_and_active_profile(invoke, backend, rt):
    rt.config._data['profiles'].append({'name': 'dev', 'api_endpoint': 'https://dev.example/dashboard'})
    rt.config._data['current'] = 'dev'
    rt.auth.ensure_credentials.return_value = Credentials.create('dev', 'cookie', 'csrf', 'current-user', 3600)
    rt.business.refresh('dev', 'current-user', [Department('d', 'D', (Tenant('real-tenant', 'Tenant', (),
        (Team('team-id', 'team-key', 'Team', 'available', 'team-business'),)),))])
    rt.business.select('dev', 'current-user', 'real-tenant', 'team-id')
    backend.header_business, backend.tenant_id, backend.host = 'team-business', 'real-tenant', 'dev.example'
    result = invoke(['--dry-run', '-o', 'json'], backend)
    assert result.exit_code == 0, result.output


def test_context_change_after_confirmation_blocks_publish(invoke, backend, rt):
    def confirm(*args, **kwargs):
        rt.config._data['profiles'][0]['api_endpoint'] = 'https://changed.example'
        return True
    with patch('wiserec_cli.commands.model_deploy.typer.confirm', side_effect=confirm):
        result = invoke([], backend, interactive=True)
    assert result.exit_code == 1 and '上下文已变化' in result.stderr
    assert not backend.publishes


def test_missing_document_and_access_denied(invoke, backend):
    assert invoke(['--yes', '--request-file', '/nonexistent/request.json'], backend).exit_code != 0
    assert not backend.calls
    from wiserec_cli.errors import BusinessError
    with patch('wiserec_cli.runtime.check_access', side_effect=BusinessError('denied')):
        assert invoke(['--yes'], backend).exit_code == 1
    assert not backend.calls


@pytest.mark.parametrize('field', ['modelName', 'modelVersion', 'pkgId', 'modelHistoryList'])
def test_missing_model_field_prevents_publish(invoke, backend, field):
    backend.model.pop(field)
    result = invoke(['--yes'], backend)
    assert result.exit_code == 1 and not backend.publishes


@pytest.mark.parametrize('field', ['pkgStorageId', 'pkgStorageLocation', 'storageType'])
def test_missing_framework_storage_prevents_publish(invoke, backend, field):
    backend.framework['data'].pop(field)
    assert invoke(['--yes'], backend).exit_code == 1
    assert not backend.publishes


@pytest.mark.parametrize('memory', ['8M', 'badG', '0G', '-1G', 'NaNG'])
def test_invalid_memory_prevents_publish(invoke, backend, memory):
    backend.resources['area-a']['memory'] = memory
    assert invoke(['--yes'], backend).exit_code == 1
    assert not backend.publishes


def test_exact_resource_detail_name_required(invoke, backend):
    backend.resources['area-a']['dockerResourceTemplateName'] = 'wrong-name'
    result = invoke(['--yes'], backend)
    assert result.exit_code == 1 and '名称不一致' in result.stderr
    assert not backend.publishes


def test_access_command_and_default_output(invoke, backend, rt):
    rt.config._data['profiles'][0]['output_format'] = 'json'
    with patch('wiserec_cli.runtime.check_access') as access:
        result = invoke(['--dry-run'], backend)
    assert result.exit_code == 0
    assert json.loads(result.stdout)['data']['serviceInfo']['serviceName'] == 'model-name'
    assert access.call_args.kwargs['command'] == 'ml model deploy'


def test_invalid_utf8_document_prevents_query(invoke, backend, tmp_path):
    path = tmp_path/'invalid.txt'
    path.write_bytes(b'\xff')
    assert invoke(['--yes', '--request-file', str(path)], backend).exit_code == 1
    assert not backend.calls


def test_original_source_values_not_changed(invoke, backend):
    before = deepcopy((backend.model, backend.template, backend.resources, backend.framework))
    assert invoke(['--dry-run'], backend).exit_code == 0
    assert before == (backend.model, backend.template, backend.resources, backend.framework)


def test_preview_structure_values_and_no_table_numbering(invoke, backend):
    from wiserec_cli.commands.deploy_preview import preview
    payload = json.loads(invoke(['--dry-run', '-o', 'json'], backend).stdout)
    before = deepcopy(payload)
    with patch('wiserec_cli.commands.deploy_preview.console') as mocked:
        preview(payload, backend.template, ('prod', 'url', 'user', 'pps', 'pps'), TEMPLATE_ID,
                None, None, {'framework-id': 'framework@framework-version'})
    headings = [str(c.args[0]) for c in mocked.print.call_args_list if c.kwargs.get('style')]
    assert all(c.kwargs['style'] == 'bold cyan' for c in mocked.print.call_args_list if c.kwargs.get('style'))
    assert all(title in headings for title in ['1、基本信息', '2、部署区域', '3、扩展参数', '4、服务文档',
        '2.1.1、基本信息', '2.1.2、推理框架', '2.1.2.1、rtc.properties', '2.1.3、弹性伸缩',
        '2.1.4、扩展信息', '2.2.1、基本信息', '2.2.4.5、自定义启动命令'])
    tables = [c.args[0] for c in mocked.print.call_args_list if hasattr(c.args[0], 'columns')]
    assert all(col.header != '编号' for table in tables for col in table.columns)
    basic = {str(k): str(v) for k, v in zip(tables[0].columns[0]._cells, tables[0].columns[1]._cells)}
    assert basic['单服务实例最大QPS（超过了会触发流控）'] == '-'
    assert basic['部署方式'] == '容器部署'
    assert list(basic) == ['模型名称', '模型版本', '部署方式', '更新模式', '环境', '推理类型',
        '单服务实例最大QPS（超过了会触发流控）', '单服务实例最大能承受并发数（超过了会触发流控）',
        '服务调用方最大容忍超时时间（ms）', '自定义组件包', '公共组件包（平台提供）']
    assert '2.1、area-a-cluster' in headings and '2.2、area-b-cluster' in headings
    region = {str(k): str(v) for k, v in zip(tables[1].columns[0]._cells, tables[1].columns[1]._cells)}
    assert region['实例数'] == '1'
    assert region['名称'] == region['描述'] == '未填写'
    assert region['默认资源规格'] == '2C8G1NPU'
    cells = [str(cell) for table in tables for col in table.columns for cell in col._cells]
    assert 'framework@framework-version' in cells and 'original-secret' in cells
    assert 'KEY' in cells and 'VALUE' in cells and 'host.example' in cells and '/start.sh' in cells
    assert payload == before
    assert 'requestLimit' not in payload['data']['serviceInfo']


def test_preview_displays_complete_documents(invoke, backend, tmp_path):
    request, response = tmp_path/'request.txt', tmp_path/'response.txt'
    request.write_text('request line one\nrequest line two\n', encoding='utf-8')
    response.write_text('response line one\nresponse line two\n', encoding='utf-8')
    result = invoke(['--dry-run', '--request-file', str(request), '--response-file', str(response),
                     '--description', '[red]literal description[/red]', '--qps', '125'], backend)
    assert result.exit_code == 0, result.output
    for value in ['request line one\nrequest line two', 'response line one\nresponse line two',
                  '[red]literal description[/red]', '125', 'original-secret', 'sleep 30;']:
        assert value in result.stdout
    assert not backend.publishes
