"""两平台共用命令的完整性、树展示和入口门禁。"""
import json
from unittest.mock import patch

import pytest
import typer
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.adapters.registry import SHARED_COMMANDS, require_supported, supported
from cli_test_support import invoke_with_config


def leaves(command, path):
    if hasattr(command, 'commands'):
        for name, child in command.commands.items():
            yield from leaves(child, path + ' ' + name)
    elif not command.hidden:
        yield path


def test_all_existing_shared_commands_supported():
    root = typer.main.get_command(app)
    actual = {path for group in ('webstudio', 'jupyter', 'service', 'user', 'mep', 'model', 'resource',
                                'deployment', 'dataset', 'feature-task')
              for path in leaves(root.commands[group], group)}
    train = root.commands['train']
    for group in ('history', 'instance', 'config'):
        actual.update(leaves(train.commands[group], f'train {group}'))
    for name in ('start', 'cancel', 'delete', 'clone', 'detail'):
        assert name in train.commands
        actual.add(f'train {name}')
    actual.update(leaves(root.commands["auth"].commands["ping"], "auth ping"))
    assert actual == SHARED_COMMANDS
    for path in actual:
        require_supported('mlops', path)
        require_supported('wiserec', path)
    assert not supported('mlops', 'service future-operation')
    assert not supported('mlops', 'train future-operation')
    assert not supported('mlops', 'feature-task future-operation')


def config_file(tmp_path):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'current': 'old', 'profiles': [{'name': 'old',
                    'platform_type': 'mlops', 'api_endpoint': 'https://old.example'}]}))
    return path


def test_shared_tree(tmp_path):
    config = config_file(tmp_path)
    for options in ([], ['--all']):
        result = invoke_with_config(CliRunner(), app, config, ['tree', *options])
        assert result.exit_code == 0, result.output
        for group in ('webstudio', 'jupyter', 'service', 'user', 'mep', 'model', 'resource', 'deployment', 'dataset'):
            assert group in result.output
        for description in ('软删除当前业务下的训练任务', '导出并下载训练任务的 YAML 配置',
                            '立即执行指定训练任务',
                            '分页查询当前业务下的特征任务', '查询和搜索训练日志'):
            line = next(line for line in result.output.splitlines() if description in line)
            assert '[不支持]' not in line
        if options:
            assert '  支持' not in result.output
            assert '[不支持]' in result.output
            assert '── algorithm' in result.output
            for description in ('分页查询当前业务的算法仓', '获取下载地址并保存算法仓文件',
                                '按指定名称和版本克隆算法仓'):
                line = next(line for line in result.output.splitlines() if description in line)
                assert line.rstrip().endswith('[不支持]')
        else:
            assert '── algorithm' not in result.output


@pytest.mark.parametrize('args', [
    ['list'],
    ['download', 'ALGORITHM_ID'],
    ['clone', 'ALGORITHM_ID', '--name', 'copy', '--version', 'VERSION', '--yes'],
])
def test_algorithm_is_rejected_in_mlops_before_login_or_execution(tmp_path, args):
    assert supported('wiserec', f'algorithm {args[0]}')
    with patch('wiserec_cli.auth.AuthManager.ensure_credentials') as login, \
         patch('wiserec_cli.cli.ping.auto_start') as auto_ping, \
         patch('wiserec_cli.commands.algorithm.runtime_from_context') as algorithm_runtime:
        result = invoke_with_config(CliRunner(), app, config_file(tmp_path), ['algorithm', *args])

    assert result.exit_code == 1
    assert f'管理台 mlops 不支持命令 ml algorithm {args[0]}' in result.output
    login.assert_not_called()
    auto_ping.assert_not_called()
    algorithm_runtime.assert_not_called()


@pytest.mark.parametrize('args,module', [
    (['webstudio', 'list'], 'webstudio'),
    (['jupyter', 'doctor'], 'jupyter'),
    (['service', 'list'], 'service'),
    (['train', 'history', 'list', 'TASK_ID'], 'train'),
    (['train', 'history', 'detail', 'TASK_ID', 'JOB_ID'], 'train_history_detail'),
    (['train', 'instance', 'list', 'TASK_ID'], 'train'),
    (['train', 'instance', 'logs', 'download', 'TASK_ID', 'JOB_ID'], 'train_logs'),
    (['train', 'history', 'logs', 'download', 'TASK_ID', 'JOB_ID'], 'train'),
    (['train', 'cancel', 'TASK_ID'], 'train'),
    (['train', 'start', 'TASK_ID'], 'train'),
    (['train', 'delete', 'TASK_ID'], 'train'),
    (['train', 'clone', 'TASK_ID', '--name', 'copy'], 'train'),
    (['train', 'detail', 'TASK_ID'], 'train'),
    (['train', 'config', 'export', 'TASK_ID'], 'train'),
    (['train', 'config', 'update', 'TASK_ID', '--customize-config', 'value'], 'train'),
    (['feature-task', 'detail', 'TASK_ID'], 'feature_task'),
    (['feature-task', 'list'], 'feature_task'),
    (['feature-task', 'execution', 'list', 'TASK_ID'], 'feature_execution'),
    (['feature-task', 'execution', 'logs', 'search', 'JOB_ID'], 'feature_execution'),
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
        result = invoke_with_config(CliRunner(), app, config_file(tmp_path), [*args])
    argument_index = next((i for i, value in enumerate(args)
                           if value in ('TASK_ID', 'JOB_ID')), len(args))
    path = args[:argument_index]
    assert seen == ['ml ' + ' '.join(path)]
    assert 'shared-implementation-reached' in result.output
    assert '不支持' not in result.output


@pytest.mark.parametrize('command', ['train delete', 'train start'])
def test_new_mlops_writes_use_current_environment_and_business(tmp_path, command):
    from functools import partial

    import httpx

    from wiserec_cli.business import Department, Tenant
    from wiserec_cli.client import PlatformClient
    from wiserec_cli.models import Credentials
    from wiserec_cli.runtime import Runtime

    config = config_file(tmp_path)
    runtime = Runtime(config_path=config, credential_path=tmp_path / 'credentials.json',
                      business_path=tmp_path / 'business.json')
    credentials = Credentials.create('old', 'a=b', 'csrf', 'user', 60)
    runtime.credentials.save(credentials)
    for profile, business in [('other', 'other-business'), ('old', 'selected-business')]:
        catalog = (Department('department', 'Department', (Tenant(business, business, (), ()),)),)
        runtime.business.refresh(profile, 'user', catalog, browser_business_id=business)

    requests = []

    def handler(request):
        assert request.url.host == 'old.example'
        assert request.headers['businessid'] == 'selected-business'
        body = json.loads(request.content)
        requests.append((request.url.path, body))
        if request.url.path.endswith('/queryList'):
            return httpx.Response(200, json={'result': {'code': 0, 'count': 1,
                'taskInfos': [{'taskId': 'task', 'taskName': 'Task', 'teamId': 'team'}]}})
        return httpx.Response(200, json={'result': {'code': 0, 'des': 'success',
                                                     'data': {'jobId': 'job'}}})

    if command == 'train delete':
        args = ['train', 'delete', 'task']
        expected = [
            '/ai/backend/mtp/traintask/queryList', '/ai/backend/modelDev/modelTrain/v2/delete',
        ]
    else:
        args = ['train', 'start', 'task']
        expected = ['/ai/backend/modelDev/modelTrain/startScheduleTask']

    with patch('wiserec_cli.cli.Runtime', return_value=runtime), \
         patch('wiserec_cli.runtime.check_access') as check_access, \
         patch('wiserec_cli.runtime.PlatformClient',
               partial(PlatformClient, transport=httpx.MockTransport(handler))):
        result = invoke_with_config(CliRunner(), app, config, args, input='y\n')

    assert result.exit_code == 0, result.output
    if command != 'train start':
        assert '确认' in result.output
    assert [path for path, _ in requests] == expected
    assert check_access.call_count == len(expected)
    for call in check_access.call_args_list:
        assert call.args[1].name == 'old'
        assert call.args[3].business_id == 'selected-business'
        assert call.kwargs['command'] == 'ml ' + ' '.join(args[:2])
    if command == 'train delete':
        assert requests[0][1]['businessId'] == 'selected-business'
        assert requests[-1][1] == {'taskId': 'task', 'teamId': 'team', 'target': 'Task', 'softDeleteFlag': True}
    else:
        assert requests[0][1]['data'] == {'taskId': 'task'}
        assert 'jobId：job' in result.output


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
            assert body['sortOrder'] == 'ascend'
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
            result = invoke_with_config(CliRunner(), app, config, ['train', kind,
                                             'list', 'task', '-o', 'json'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['items'] == [{'jobId': 'job', 'extra': 'preserved'}]
    assert len(calls) == (1 if kind == 'history' else 3)
