"""两平台共用命令的完整性、树展示和入口门禁。"""
import json
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.adapters.registry import SHARED_COMMANDS, require_supported, supported


def leaves(command, path):
    if hasattr(command, 'commands'):
        for name, child in command.commands.items():
            yield from leaves(child, path + ' ' + name)
    elif not command.hidden:
        yield path


def test_all_existing_shared_commands_supported():
    root = typer.main.get_command(app)
    actual = {path for group in ('webstudio', 'jupyter', 'service', 'user', 'mep', 'model', 'resource', 'deployment', 'dataset')
              for path in leaves(root.commands[group], group)}
    actual.update(leaves(root.commands["train"].commands["history"], "train history"))
    actual.update(leaves(root.commands["train"].commands["instance"], "train instance"))
    actual.update(leaves(root.commands["auth"].commands["ping"], "auth ping"))
    assert actual == SHARED_COMMANDS
    for path in actual:
        require_supported('mlops', path)
        require_supported('wiserec', path)
    assert not supported('mlops', 'service future-operation')
    assert not supported('mlops', 'train start')
    assert not supported('mlops', 'algorithm list')


def config_file(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'current': 'old', 'profiles': [{'name': 'old',
                    'platform_type': 'mlops', 'api_endpoint': 'https://old.example'}]}))
    return path


def test_shared_tree(tmp_path):
    config = config_file(tmp_path)
    for options in ([], ['--all']):
        result = CliRunner().invoke(app, ['--config', str(config), 'tree', *options])
        assert result.exit_code == 0, result.output
        for group in ('webstudio', 'jupyter', 'service', 'user', 'mep', 'model', 'resource', 'deployment', 'dataset'):
            assert group in result.output
        if options:
            assert '  支持' not in result.output
            assert '[不支持]' in result.output
        else:
            assert '── algorithm' not in result.output


@pytest.mark.parametrize('args,module', [
    (['webstudio', 'list'], 'webstudio'),
    (['jupyter', 'doctor'], 'jupyter'),
    (['service', 'list'], 'service'),
    (['train', 'history', 'list', 'TASK_ID'], 'train'),
    (['train', 'instance', 'list', 'TASK_ID'], 'train'),
    (['train', 'history', 'logs', 'download', 'TASK_ID', 'JOB_ID'], 'train'),
])
def test_cli_reaches_shared_implementation(tmp_path, args, module):
    from wiserec_cli.commands.common import runtime_from_context
    seen = []
    def observe(context):
        runtime = runtime_from_context(context)
        assert runtime.config.current_profile().platform_type == 'mlops'
        seen.append(runtime.invocation_command)
        raise RuntimeError('shared-implementation-reached')
    with patch(f'wiserec_cli.commands.{module}.runtime_from_context', side_effect=observe):
        result = CliRunner().invoke(app, ['--config', str(config_file(tmp_path)), *args])
    path = [value for value in args if value not in ('TASK_ID', 'JOB_ID')]
    assert seen == ['ml ' + ' '.join(path)]
    assert 'shared-implementation-reached' in result.output
    assert '不支持' not in result.output


@pytest.mark.parametrize('kind', ['history', 'instance'])
def test_training_queries_use_shared_endpoint_and_current_business(tmp_path, kind):
    import httpx
    from types import SimpleNamespace
    from wiserec_cli.runtime import Runtime
    from wiserec_cli.client import PlatformClient
    from wiserec_cli.models import Profile, Credentials
    config = config_file(tmp_path)
    runtime = Runtime(config_path=config, credential_path=tmp_path / 'credentials.json',
                      business_path=tmp_path / 'business.json')
    calls = []
    def handler(request):
        body = json.loads(request.content)
        calls.append(request.url.path)
        assert request.url.host == 'old.example'
        assert request.headers['businessid'] == 'selected-business'
        if request.url.path.endswith('/queryList'):
            # 实例查询查找任务时必须复用 MLOps 列表，包含翻页。
            assert body['businessId'] == 'selected-business'
            if body['pageIndex'] == 1:
                items = [{'taskId': str(i)} for i in range(10)]
            else:
                assert body['pageIndex'] == 2
                items = [{'taskId': 'task', 'businessId': 'selected-business', 'taskType': 'train'}]
            return httpx.Response(200, json={'result': {'code': 0, 'count': 11, 'taskInfos': items}})
        assert body['taskId'] == 'task' and body['pageIndex'] == 1 and body['pageSize'] == 10
        if kind == 'history':
            assert request.url.path.endswith('/queryScheduleTaskList')
            assert body['sortOrder'] == 'descend'
        else:
            assert request.url.path.endswith('/queryJobInstanceByTaskId')
            assert body['businessId'] == 'selected-business'
            assert body['jobType'] == 'train' and body['sortOrder'] == 'ascend'
        return httpx.Response(200, json={'result': {'code': 0, 'count': 1,
                                                'jobs': [{'jobId': 'job', 'extra': 'preserved'}]}})
    with PlatformClient(Profile('old', 'https://old.example', platform_type='mlops'),
                        Credentials.create('old', 'a=b', 'csrf', 'user', 60), 1000, 0, True,
                        transport=httpx.MockTransport(handler),
                        business_selection=SimpleNamespace(business_id='selected-business')) as client:
        with patch('wiserec_cli.cli.Runtime', return_value=runtime), \
             patch.object(runtime, 'authenticated_call', side_effect=lambda operation: operation(client)):
            result = CliRunner().invoke(app, ['--config', str(config), 'train', kind,
                                             'list', 'task', '-o', 'json'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['items'] == [{'jobId': 'job', 'extra': 'preserved'}]
    assert len(calls) == (1 if kind == 'history' else 3)
