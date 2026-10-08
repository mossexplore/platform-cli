"""模型查询请求契约、业务隔离、完整 JSON 与人工展示。"""
import inspect
import json
from copy import deepcopy
from io import StringIO
from unittest.mock import Mock, patch

import httpx
import pytest
from rich.console import Console
from rich.table import Table
from typer.testing import CliRunner

from test_webstudio import rt
from wiserec_cli import __version__
from wiserec_cli.business import Department, Tenant
from wiserec_cli.cli import app
from wiserec_cli.client import PlatformClient
from wiserec_cli.commands.model import display_value, render_list
from wiserec_cli.errors import ApiError, BusinessError
from wiserec_cli.models import Credentials
from wiserec_cli.services.model import ModelService

MODEL_ID = 'f9786da8-13d3-45a9-ae77-41aaf635701a'
MODEL = {'modelId': MODEL_ID, 'name': 'test_product', 'version': '16.0.11',
         'businessId': 'pps', 'type': 'workflow', 'createTime': '2025-11-26 21:16:04',
         'updateTime': '2026-09-08T06:54:36.000+00:00', 'owner': 'l00123456',
         'teamId': 'NLP', 'extension': {'retained': True}}
LIST = {'version': '1.0', 'meta': {'uuid': 'trace'},
        'result': {'count': 1, 'models': [MODEL], 'code': 0, 'des': 'success', 'extra': True}}
DETAIL = {'version': '1.0', 'meta': {'uuid': 'trace'}, 'result': {
    'modelId': MODEL_ID, 'sourceId': 'f16dd744-5f37-4323-9719-91b08461e2ec',
    'code': 0, 'businessId': 'pps', 'algorithm': 'BROWSER-NLP', 'modelTag': 0,
    'pkgSize': 3271903223, 'storeType': 'OBS', 'sfsId': 'sfs-mep-browser-az3',
    'pkgLocation': 'mep-modelpkgs-cn', 'source': 'wiseEye', 'sourceEnv': 'product',
    'contentMode': 'full', 'unlisted': {'keep': ['all', 'fields']}}}
DEFAULT_BODY = {'pageIndex': 1, 'pageSize': 10, 'sfsId': '', 'modelStatus': None,
                'sourceEnv': None, 'tags': [], 'modelUsage': 'cloud', 'modelName': '',
                'selectModel': '', 'businessId': 'pps', 'scene': '', 'subScene': '',
                'source': None, 'modelType': None, 'teamId': '', 'owner': None,
                'noticeTime': [], 'approvalStrategy': None}


@pytest.fixture
def invoke(rt):
    options = {'mix_stderr': False} if 'mix_stderr' in inspect.signature(CliRunner).parameters else {}
    def run(args, handler):
        with patch('wiserec_cli.cli.Runtime', return_value=rt), \
             patch('wiserec_cli.runtime.PlatformClient', side_effect=lambda *a, **kw:
                   PlatformClient(*a, transport=httpx.MockTransport(handler), **kw)):
            return CliRunner(**options).invoke(app, ['--config', str(rt.config.path), 'model', *args])
    return run


def test_list_default_request_and_complete_json(rt, invoke):
    def handler(request):
        assert request.method == 'POST'
        assert request.url.host == 'console.example'
        assert request.url.path == '/ai/backend/mep/models/queryList'
        assert request.headers['businessid'] == request.headers['ai-businessid'] == 'pps'
        assert request.headers['x-cli-version'] == __version__
        assert json.loads(request.content) == DEFAULT_BODY
        return httpx.Response(200, json=LIST)
    with patch('wiserec_cli.runtime.check_access') as access:
        result = invoke(['list', '-o', 'json'], handler)
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout) == LIST
    assert access.call_args.kwargs['command'] == 'ml model list'


def test_combined_filters_and_pagination(invoke):
    calls = []
    def handler(request):
        calls.append(request)
        assert json.loads(request.content) == {**DEFAULT_BODY, 'pageIndex': 2, 'pageSize': 20,
            'modelName': 'product', 'modelType': 'custom-type', 'owner': 'owner', 'teamId': 'team'}
        return httpx.Response(200, json=LIST)
    result = invoke(['list', '--page', '2', '--page-size', '20', '--name', 'product',
                     '--type', 'custom-type', '--owner', 'owner', '--team-id', 'team', '-o', 'json'], handler)
    assert result.exit_code == 0, result.output
    assert len(calls) == 1


def test_active_environment_business_and_endpoint_are_used(rt, invoke):
    rt.config._data['profiles'].append({'name': 'dev', 'api_endpoint': 'https://dev.example/dashboard'})
    rt.config._data['current'] = 'dev'
    rt.auth.ensure_credentials.return_value = Credentials.create('dev', 'dev-cookie', 'csrf', 'current-user', 3600)
    rt.business.refresh('dev', 'current-user',
        [Department('d', 'D', (Tenant('dev-business', 'Dev', (), ()),))], browser_business_id='dev-business')
    def handler(request):
        assert request.url.host == 'dev.example'
        assert request.headers['businessid'] == 'dev-business'
        assert json.loads(request.content)['businessId'] == 'dev-business'
        return httpx.Response(200, json=LIST)
    assert invoke(['list', '-o', 'json'], handler).exit_code == 0


def test_detail_body_without_business_id_and_success_code(invoke):
    def handler(request):
        assert request.url.path == '/ai/backend/mep/models/queryDetail'
        assert request.headers['businessid'] == 'pps'
        assert json.loads(request.content) == {'modelId': MODEL_ID}
        return httpx.Response(200, json=DETAIL)
    result = invoke(['detail', MODEL_ID, '-o', 'json'], handler)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload == DETAIL
    assert type(payload['result']['pkgSize']) is int


def test_detail_labels_size_zero_and_safe_text(invoke):
    payload = deepcopy(DETAIL)
    payload['result']['algorithm'] = '[red]BROWSER-NLP[/red]'
    payload['result']['modelSize'] = 1  # 旧字段不能覆盖 pkgSize 的展示值
    result = invoke(['detail', MODEL_ID], lambda request: httpx.Response(200, json=payload))
    assert result.exit_code == 0, result.output
    for value in ('算法类型：[red]BROWSER-NLP[/red]', '版本标签：0', '模型大小：3.05 GB',
                  '存储方式：OBS', 'SFS标识：sfs-mep-browser-az3', '数据源：wiseEye',
                  '数据源标签：f16dd744-5f37-4323-9719-91b08461e2ec', '更新方式：full',
                  '模型来源环境：product'):
        assert value in result.stdout
    assert 'pkgLocation' not in result.stdout


@pytest.mark.parametrize('value,expected', [
    (0, '0 B'), (1023, '1023 B'), (1024, '1.00 KB'),
    (1536, '1.50 KB'), (1024**2, '1.00 MB'), (1024**3, '1.00 GB'),
    (1024**4, '1.00 TB'), (3271903223, '3.05 GB'),
    (None, '-'), ('', '-'), ('unknown', 'unknown'), (-1, '-1'),
])
def test_readable_model_size(value, expected):
    assert display_value('pkgSize', value) == expected


@pytest.mark.parametrize('value,expected', [
    ('2026-09-08T06:54:36.000+00:00', '2026-09-08 14:54:36'),
    ('2026-09-08T23:54:36.123-04:00', '2026-09-09 11:54:36'),
    ('2026-09-08T06:54:36Z', '2026-09-08 14:54:36'),
    ('2025-11-26 21:16:04', '2025-11-26 21:16:04'), (None, '-'),
])
def test_beijing_time(value, expected):
    assert display_value('updateTime', value) == expected


def test_list_preserves_id_and_wraps_long_fields_in_narrow_console():
    payload = deepcopy(LIST)
    payload['result']['models'][0]['name'] = 'very-long-model-name-' * 8
    stream = StringIO()
    console = Console(file=stream, color_system=None, width=80)
    with patch('wiserec_cli.commands.model.console', console):
        render_list(payload, 1, 10, 'table')
    text = stream.getvalue()
    assert MODEL_ID in text
    assert '第 1 页' in text
    with patch('wiserec_cli.commands.model.console') as mocked:
        render_list(payload, 1, 10, 'table')
    table = mocked.print.call_args_list[0].args[0]
    assert isinstance(table, Table)
    assert table.columns[0].width == table.columns[0].min_width == table.columns[0].max_width == 36
    assert table.columns[0].no_wrap and table.columns[0].overflow == 'ignore'
    assert all(column.overflow == 'fold' for column in table.columns[1:])
    assert payload['result']['models'][0]['updateTime'] == LIST['result']['models'][0]['updateTime']


def test_list_table_missing_fields_and_empty_page(invoke):
    response = {'result': {'count': 1, 'models': [{'modelId': MODEL_ID}]}}
    result = invoke(['list'], lambda request: httpx.Response(200, json=response))
    assert result.exit_code == 0 and MODEL_ID in result.stdout
    assert '-' in result.stdout
    result = invoke(['list', '--page', '3'], lambda request: httpx.Response(200, json={'result': {'count': 0, 'models': []}}))
    assert result.exit_code == 0
    assert '暂无模型' in result.stdout and '第 3 页' in result.stdout


@pytest.mark.parametrize('payload', [
    {}, {'result': None}, {'result': {'code': 9, 'des': 'denied'}},
    {'result': {'count': True, 'models': []}}, {'result': {'count': -1, 'models': []}},
    {'result': {'count': 1, 'models': {}}}, {'result': {'count': 1, 'models': [None]}},
])
def test_invalid_list_response_is_an_error(invoke, payload):
    result = invoke(['list', '-o', 'json'], lambda request: httpx.Response(200, json=payload))
    assert result.exit_code == 1
    assert '错误' in result.stderr
    assert not result.stdout


@pytest.mark.parametrize('payload', [{}, {'result': []}, {'result': {'code': 2}}, {'result': {'code': False}}])
def test_invalid_detail_response_is_an_error(invoke, payload):
    result = invoke(['detail', MODEL_ID], lambda request: httpx.Response(200, json=payload))
    assert result.exit_code == 1


@pytest.mark.parametrize('args', [['list', '--page', '0'], ['list', '--page-size', '0'],
                                  ['list', '-o', 'yaml'], ['detail', '   '],
                                  ['list', '--model-usage', 'edge'], ['list', '--business-id', 'other']])
def test_bad_arguments_do_not_send_requests(invoke, args):
    handler = Mock(side_effect=AssertionError('must not send'))
    result = invoke(args, handler)
    assert result.exit_code != 0
    handler.assert_not_called()


def test_default_output_follows_environment_configuration(rt, invoke):
    rt.config._data['profiles'][0]['output_format'] = 'json'
    result = invoke(['list'], lambda request: httpx.Response(200, json=LIST))
    assert json.loads(result.stdout) == LIST


def test_business_selection_mismatch_stops_request(rt, invoke):
    data = json.loads(rt.business.path.read_text())
    data['profiles']['prod']['selected']['businessId'] = 'wrong'
    rt.business.path.write_text(json.dumps(data))
    handler = Mock()
    result = invoke(['list'], handler)
    assert result.exit_code == 1
    handler.assert_not_called()


def test_permissions_denied_before_platform_request(invoke):
    handler = Mock()
    with patch('wiserec_cli.runtime.check_access', side_effect=BusinessError('denied')):
        result = invoke(['list'], handler)
    assert result.exit_code == 1
    handler.assert_not_called()


def test_no_selected_business_for_either_service_operation():
    client = Mock(business_id='')
    for operation in (lambda: ModelService(client).list_models(), lambda: ModelService(client).detail(MODEL_ID)):
        with pytest.raises(BusinessError):
            operation()
    client.request.assert_not_called()


@pytest.mark.parametrize('status', [500, 403])
def test_http_failures_are_not_successful_empty_pages(invoke, status):
    result = invoke(['list'], lambda request: httpx.Response(status, text='unavailable'))
    assert result.exit_code == 1
    assert '暂无模型' not in result.stdout


def test_authentication_refresh_keeps_json_clean(rt, invoke):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(401) if len(calls) == 1 else httpx.Response(200, json=LIST)
    result = invoke(['list', '-o', 'json'], handler)
    assert result.exit_code == 0
    assert json.loads(result.stdout) == LIST
    assert len(calls) == 2
    assert rt.auth.ensure_credentials.call_args.kwargs['force_refresh'] is True


SOURCE = {'version': '1.0', 'meta': {'uuid': 'trace'}, 'result': {
    'code': 0, 'modelName': '[red]output[/red]', 'modelVersion': 'original',
    'modelTag': 'wrong', 'sensitive': 1, 'businessId': 'browser', 'status': 1,
    'createTime': '2026-09-20T06:30:14.000Z', 'description': 'description',
    'source': 'wisemlops', 'bucketName': 'bucket', 'extra': {'kept': True}}}


@pytest.mark.parametrize('output', ['table', 'json'])
def test_source_request_chain_and_output(rt, invoke, output):
    rt.config._data['profiles'].append({'name': 'dev', 'api_endpoint': 'https://dev.example/dashboard'})
    rt.config._data['current'] = 'dev'
    rt.auth.ensure_credentials.return_value = Credentials.create('dev', 'cookie', 'csrf', 'current-user', 3600)
    rt.business.refresh('dev', 'current-user',
        [Department('d', 'D', (Tenant('dev-business', 'Dev', (), ()),))], browser_business_id='dev-business')
    calls = []
    def handler(request):
        calls.append(request.url.path)
        assert request.method == 'POST'
        assert request.url.host == 'dev.example'
        assert request.headers['businessid'] == 'dev-business'
        if len(calls) == 1:
            assert request.url.path == '/ai/backend/mep/models/queryDetail'
            assert json.loads(request.content) == {'modelId': MODEL_ID}
            return httpx.Response(200, json=DETAIL)
        assert request.url.path == '/ai/backend/mtp/offlinemodel/version/queryDetail'
        assert json.loads(request.content) == {'versionId': DETAIL['result']['sourceId']}
        return httpx.Response(200, json=SOURCE)
    result = invoke(['source', MODEL_ID, '-o', output], handler)
    assert result.exit_code == 0, result.output
    assert len(calls) == 2
    if output == 'json':
        assert json.loads(result.stdout) == SOURCE
    else:
        for text in ('输出名称：[red]output[/red]', '模型版本：original', '敏感：是',
                     '业务编码：browser', '状态：已发布', '创建时间：2026-09-20 14:30:14',
                     '描述：description', '来源：wisemlops', '存储桶：bucket'):
            assert text in result.stdout
        assert 'wrong' not in result.stdout


@pytest.mark.parametrize('code', [None, False, '0', 1])
@pytest.mark.parametrize('stage', ['detail', 'source'])
def test_source_rejects_invalid_success_code(invoke, code, stage):
    calls = []
    def handler(request):
        calls.append(request)
        payload = deepcopy(DETAIL if len(calls) == 1 else SOURCE)
        if stage == 'detail' or len(calls) == 2:
            if code is None:
                payload['result'].pop('code')
            else:
                payload['result']['code'] = code
        return httpx.Response(200, json=payload)
    result = invoke(['source', MODEL_ID, '-o', 'json'], handler)
    assert result.exit_code == 1
    assert not result.stdout
    assert len(calls) == (1 if stage == 'detail' else 2)


@pytest.mark.parametrize('source_id', [None, '', ' ', 123])
def test_source_requires_valid_source_id(invoke, source_id):
    payload = deepcopy(DETAIL)
    payload['result']['sourceId'] = source_id
    handler = Mock(return_value=httpx.Response(200, json=payload))
    result = invoke(['source', MODEL_ID], handler)
    assert result.exit_code == 1
    assert 'sourceId' in result.stderr
    assert handler.call_count == 1


def test_source_missing_display_fields_and_negative_flags(invoke):
    payloads = iter([DETAIL, {'result': {'code': 0, 'sensitive': 2, 'status': 0}}])
    result = invoke(['source', MODEL_ID], lambda r: httpx.Response(200, json=next(payloads)))
    assert result.exit_code == 0
    for text in ('输出名称：-', '模型版本：-', '敏感：否', '状态：未发布'):
        assert text in result.stdout


def test_detail_requires_code(invoke):
    payload = deepcopy(DETAIL)
    del payload['result']['code']
    result = invoke(['detail', MODEL_ID], lambda r: httpx.Response(200, json=payload))
    assert result.exit_code == 1


TRAIN_TASK = {'version': '1.0', 'meta': {'uuid': 'task-trace'}, 'result': {
    'code': 0, 'des': 'success', 'extra': True, 'jobHistoryDetail': {
        'taskName': '[red]task[/red]', 'businessId': 'browser', 'jobType': 'train',
        'image': 'image:tag', 'imageSpecificInfo': '7C50G1GPU', 'maxHistoryNum': 0,
        'extra': {'retained': True}}}}


@pytest.mark.parametrize('output', ['table', 'json'])
def test_train_task_chain_and_independent_output(invoke, output):
    calls = []
    payloads = [DETAIL, {**SOURCE, 'result': {**SOURCE['result'], 'jobId': 'job-id'}}, TRAIN_TASK]
    paths = ['/ai/backend/mep/models/queryDetail',
             '/ai/backend/mtp/offlinemodel/version/queryDetail',
             '/ai/backend/mtp/traintask/queryModelTaskDetail']
    bodies = [{'modelId': MODEL_ID}, {'versionId': DETAIL['result']['sourceId']}, {'jobId': 'job-id'}]
    def handler(request):
        index = len(calls)
        calls.append(request)
        assert request.method == 'POST'
        assert request.url.host == 'console.example'
        assert request.headers['businessid'] == 'pps'
        assert request.url.path == paths[index]
        assert json.loads(request.content) == bodies[index]
        return httpx.Response(200, json=payloads[index])
    result = invoke(['source', MODEL_ID, '--train-task', '-o', output], handler)
    assert result.exit_code == 0, result.output
    assert len(calls) == 3
    if output == 'json':
        assert json.loads(result.stdout) == TRAIN_TASK
    else:
        for text in ('任务名称：[red]task[/red]', '业务编码：browser', '任务类型：train',
                     '镜像：image:tag', '资源规格：7C50G1GPU', '历史记录数目：0'):
            assert text in result.stdout
        assert '模型版本' not in result.stdout


@pytest.mark.parametrize('job_id', [None, '', ' ', 123])
def test_train_task_missing_job_id_stops_third_request(invoke, job_id):
    payloads = iter([DETAIL, {'result': {'code': 0, 'jobId': job_id}}])
    handler = Mock(side_effect=lambda r: httpx.Response(200, json=next(payloads)))
    result = invoke(['source', MODEL_ID, '--train-task', '-o', 'json'], handler)
    assert result.exit_code == 1
    assert 'jobId' in result.stderr
    assert not result.stdout
    assert handler.call_count == 2


@pytest.mark.parametrize('payload', [
    {}, {'result': {'jobHistoryDetail': {}}}, {'result': {'code': False}},
    {'result': {'code': '0'}}, {'result': {'code': 2}},
    {'result': {'code': 0}}, {'result': {'code': 0, 'jobHistoryDetail': []}},
])
def test_train_task_invalid_response_has_no_success_output(invoke, payload):
    payloads = iter([DETAIL, {'result': {'code': 0, 'jobId': 'job-id'}}, payload])
    result = invoke(['source', MODEL_ID, '--train-task', '-o', 'json'],
                    lambda r: httpx.Response(200, json=next(payloads)))
    assert result.exit_code == 1
    assert not result.stdout


def test_train_task_missing_display_fields(invoke):
    payloads = iter([DETAIL, {'result': {'code': 0, 'jobId': 'job-id'}},
                     {'result': {'code': 0, 'jobHistoryDetail': {}}}])
    result = invoke(['source', MODEL_ID, '--train-task'],
                    lambda r: httpx.Response(200, json=next(payloads)))
    assert result.exit_code == 0
    assert '任务名称：-' in result.stdout
    assert '历史记录数目：-' in result.stdout
