import json
from uuid import UUID
from unittest.mock import patch
import httpx
import pytest
from typer.testing import CliRunner
from wisemlops_cli.cli import app
from wisemlops_cli.client import PlatformClient
from wisemlops_cli.errors import MlError
import test_runtime


@pytest.fixture
def runtime():
    fixture = test_runtime.RuntimeBusinessContextTest()
    fixture.setUp()
    fixture.store.select('dev', 'jack', tenant_id='mep')
    yield fixture.runtime
    fixture.tearDown()


def invoke(runtime, handler, task='task-id'):
    def client(**kwargs):
        return PlatformClient(**kwargs, transport=httpx.MockTransport(handler))
    with patch('wisemlops_cli.commands.train.runtime_from_context', return_value=runtime), \
         patch('wisemlops_cli.runtime.PlatformClient', side_effect=client):
        return CliRunner().invoke(app, ['--config', str(runtime.config.path), 'train', 'start', task])


def test_exact_request_and_output(runtime):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={'version': '1.0', 'result': {
            'code': 0, 'des': 'success', 'data': {'des': 'add job success', 'jobId': 'job-123'}}})
    first = invoke(runtime, handler)
    second = invoke(runtime, handler)
    assert first.exit_code == second.exit_code == 0
    assert first.stdout.strip() == '训练任务执行成功，jobId：job-123'
    assert len(requests) == 2
    uuids = []
    for request in requests:
        assert request.method == 'POST'
        assert str(request.url) == 'https://dev.example.com/ai/backend/modelDev/modelTrain/startScheduleTask'
        assert request.headers['businessid'] == 'mep'
        assert request.headers['cookie'] == 'session=abc'
        body = json.loads(request.content)
        uuids.append(body['meta']['uuid'])
        assert UUID(uuids[-1]).version == 4
        assert body == {'version': '1.0', 'meta': {'uuid': uuids[-1]}, 'data': {'taskId': 'task-id'}}
    assert uuids[0] != uuids[1]


@pytest.mark.parametrize('result', [
    {'code': 1, 'des': 'not allowed'}, {'code': 0, 'des': 'failed'},
    {'code': '0', 'des': 'success'}, {'code': False, 'des': 'success'},
])
def test_business_failure_reports_code_and_des(runtime, result):
    response = invoke(runtime, lambda req: httpx.Response(200, json={'result': result}))
    assert response.exit_code != 0
    assert f"code={result['code']}" in response.output
    assert f"des={result['des']}" in response.output
    assert '训练任务执行成功' not in response.output


@pytest.mark.parametrize('data', [None, {}, {'jobId': ''}, {'jobId': 123}, {'jobId': ' '}])
def test_success_with_missing_job_id(runtime, data):
    response = invoke(runtime, lambda req: httpx.Response(200, json={'result': {'code': 0, 'des': 'success', 'data': data}}))
    assert response.exit_code == 0
    assert '训练任务执行成功，但接口未返回有效 jobId' in response.output


@pytest.mark.parametrize('status', [401, 403, 302, 500, 504])
def test_submission_http_failure_never_replays(runtime, status):
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(status, text='error')
    with patch.object(runtime.auth, 'ensure_credentials', wraps=runtime.auth.ensure_credentials) as auth:
        response = invoke(runtime, handler)
    assert response.exit_code != 0
    assert len(requests) == 1
    assert auth.call_count == 1
    assert '未自动重试' in response.output


def test_timeout_does_not_replay(runtime):
    requests = []
    def handler(req):
        requests.append(req)
        raise httpx.ReadTimeout('timeout', request=req)
    response = invoke(runtime, handler)
    assert response.exit_code != 0
    assert len(requests) == 1
    assert '请先查询执行记录确认' in response.output


def test_access_denied_prevents_start(runtime):
    requests = []
    with patch('wisemlops_cli.runtime.check_access', side_effect=MlError('没有权限')):
        response = invoke(runtime, lambda req: requests.append(req))
    assert response.exit_code != 0
    assert not requests


def test_empty_task_id_prevents_request(runtime):
    requests = []
    response = invoke(runtime, lambda req: requests.append(req), ' ')
    assert response.exit_code != 0
    assert 'taskId 不能为空' in response.output
    assert not requests
