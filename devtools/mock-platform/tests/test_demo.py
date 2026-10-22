"""Installed entry-point tests: independent processes, actual SQLite and files."""
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
import pytest
from helpers import initialize
from wiserec_cli_mock.seeds import uid
from wiserec_cli_mock.storage import Store


@pytest.fixture
def workspace(tmp_path):
    root = initialize(tmp_path/'demo')
    invoke(root, 'login')
    return root


def invoke(root, *args, success=True):
    environment = dict(os.environ, WISEREC_DEMO_WORKSPACE=str(root), NO_COLOR='1')
    result = subprocess.run([sys.executable, '-m', 'wiserec_cli_mock.bootstrap', *map(str, args)],
                            env=environment, text=True, capture_output=True, timeout=90, cwd=root)
    if success:
        assert result.returncode == 0, result.stdout+'\n'+result.stderr
    else:
        assert result.returncode != 0
    return result


READ_COMMANDS = [
    ['context', '--json'], ['env', 'list'], ['env', 'show'], ['auth', 'status'],
    ['business', 'list'], ['business', 'show'], ['access', 'status'], ['user', 'info'],
    ['train', 'list', '--page', '2', '-o', 'json'],
    ['train', 'instance', 'list', uid('train')], ['train', 'history', 'list', uid('train')],
    ['algorithm', 'list'], ['dataset', 'list'], ['dataset', 'detail', uid('dataset')],
    ['dataset', 'files', 'list', uid('dataset')], ['model', 'list'], ['model', 'detail', uid('model')],
    ['model', 'source', uid('model')], ['resource', 'template', 'list'],
    ['resource', 'template', 'detail', uid('resource')], ['deployment', 'template', 'list'],
    ['deployment', 'template', 'detail', uid('deployment')], ['service', 'list'],
    ['service', 'host', 'list', uid('service')], ['service', 'deployment', 'list', uid('service')],
    ['featureset', 'wide', 'list'], ['featureset', 'model', 'list'],
    ['featureset', 'wide', 'config', uid('feature')], ['offline', 'experiment', 'list'],
    ['offline', 'experiment', 'trial', 'list', uid('project')], ['webstudio', 'list'],
    ['mtp', 'swanboard', 'project', 'list'],
    ['mtp', 'swanboard', 'project', 'namespace', 'list', uid('swanproject')],
    ['mtp', 'swanboard', 'project', 'experiment', 'list', uid('swanproject'), uid('namespace')],
    ['mtp', 'swanboard', 'experiment', 'inspect', uid('experiment')],
    ['auth', 'ping', 'start'], ['auth', 'ping', 'status'], ['auth', 'ping', 'stop'],
    ['history', 'list'], ['tree'],
]


@pytest.fixture(scope='module')
def shared_workspace(tmp_path_factory):
    root = initialize(tmp_path_factory.mktemp('cli-demo')/'workspace')
    invoke(root, 'login')
    return root


@pytest.mark.parametrize('command', READ_COMMANDS)
def test_read_commands(shared_workspace, command):
    invoke(shared_workspace, *command)


def test_stateful_train_and_scope(workspace):
    before = json.loads(invoke(workspace, 'train', 'history', 'list', uid('train'), '-o', 'json').stdout)
    invoke(workspace, 'train', 'start', uid('train'))
    after = json.loads(invoke(workspace, 'train', 'history', 'list', uid('train'), '-o', 'json').stdout)
    assert after['count'] == before['count'] + 1
    from wiserec_cli_mock.manage import advance
    advance(workspace, 60)
    result = json.loads(invoke(workspace, 'train', 'history', 'list', uid('train'), '-o', 'json').stdout)
    assert result['items'][0]['status'] == 'success'
    invoke(workspace, 'env', 'use', 'demo-test')
    invoke(workspace, 'login')
    other = json.loads(invoke(workspace, 'train', 'history', 'list', uid('train'), '-o', 'json').stdout)
    assert other['count'] == before['count']


def test_clone_update_and_delete(workspace):
    invoke(workspace, 'algorithm', 'clone', uid('algorithm'), '--name', 'cloned-algo', '--version', '2', '--yes')
    value = json.loads(invoke(workspace, 'algorithm', 'list', '--name', 'cloned-algo', '-o', 'json').stdout)
    assert value['total'] == 1
    invoke(workspace, 'train', 'clone', uid('train'), '--name', 'new-train', '--yes')
    result = json.loads(invoke(workspace, 'train', 'list', '--name', 'new-train', '-o', 'json').stdout)
    assert result['count'] == 1
    task = result['items'][0]['taskId']
    invoke(workspace, 'train', 'delete', task, '--yes')
    assert json.loads(invoke(workspace, 'train', 'list', '--name', 'new-train', '-o', 'json').stdout)['count'] == 0


def test_deployment_dry_run_and_publish(workspace):
    def count():
        return json.loads(invoke(workspace, 'service', 'list', '-o', 'json').stdout)['total']
    before = count()
    args = ['model', 'deploy', uid('model'), '--template', uid('deployment')]
    invoke(workspace, *args, '--dry-run', '-o', 'json')
    assert count() == before
    invoke(workspace, *args, '--yes', '-o', 'json')
    assert count() == before+1


def test_actual_artifacts_and_upload(workspace):
    archive = workspace/'exports/algo.zip'
    invoke(workspace, 'algorithm', 'download', uid('algorithm'), '--file', archive)
    with zipfile.ZipFile(archive) as z:
        assert 'train.py' in z.namelist()
    csv = workspace/'exports/features.csv'
    invoke(workspace, 'featureset', 'wide', 'export', uid('feature'), '--file', csv)
    assert 'u001,12' in csv.read_text()
    yaml = workspace/'exports/train.yaml'
    invoke(workspace, 'train', 'config', 'export', uid('train'), '--file', yaml)
    assert uid('train') in yaml.read_text()
    invoke(workspace, 'dataset', 'files', 'upload', uid('dataset'), workspace/'samples/clicks.csv')
    result = invoke(workspace, 'dataset', 'files', 'list', uid('dataset'), '-o', 'json')
    assert 'clicks.csv' in result.stdout


def test_fail_closed_and_production_unchanged(workspace, tmp_path):
    real = tmp_path/'production.json'
    original = '{"current":"prod","profiles":[{"name":"prod","api_endpoint":"https://example.com"}]}'
    real.write_text(original)
    invoke(workspace, '--config', real, 'train', 'list', success=False)
    assert real.read_text() == original
    assert not (tmp_path/'history.jsonl').exists()
    import httpx
    from wiserec_cli_mock.transport import Transport
    with httpx.Client(transport=Transport(workspace)) as client:
        with pytest.raises(httpx.ConnectError):
            client.get('https://example.com/ai/user/info')
        response = client.get('https://demo-dev.mock.invalid/unknown', headers={
            'businessid': json.loads((workspace/'client/business.json').read_text())['profiles']['demo-dev']['selected']['businessId']})
        assert response.status_code == 501
    (workspace/'state.sqlite3').write_bytes(b'corrupt database')
    invoke(workspace, 'context', success=False)
    production = subprocess.run([sys.executable, '-m', 'wiserec_cli.cli', '--version'], capture_output=True, text=True)
    assert production.returncode == 0 and '1.0.7.7' in production.stdout


@pytest.mark.parametrize('scenario', ['empty', 'large', 'partial-failure', 'malformed-response'])
def test_scenarios(tmp_path, scenario):
    root = initialize(tmp_path/'demo', scenario)
    invoke(root, 'login')
    success = scenario in {'empty', 'large'}
    result = invoke(root, 'train', 'list', '-o', 'json', success=success)
    if success:
        assert json.loads(result.stdout)['count'] == (0 if scenario == 'empty' else 105)
    if scenario == 'partial-failure':
        invoke(root, 'train', 'list')


def test_remaining_platform_workflows(workspace):
    from wiserec_cli_mock.seeds import business_ids
    invoke(workspace, 'business', 'refresh')
    invoke(workspace, 'mep', 'config', 'get', 'demo-key')
    invoke(workspace, 'model', 'source', uid('model'), '--train-task')
    invoke(workspace, 'featureset', 'model', 'config', uid('feature', 2))
    invoke(workspace, 'train', 'config', 'update', uid('train'), '--customize-config', '{"epochs": 20}')
    with Store(workspace).transaction() as db:
        detail = Store.get(db, business_ids('demo-dev')[1], 'train_detail', uid('train'))
        assert json.loads(detail['taskInfo']['parameter']['customizeConfig'])['epochs'] == 20
        assert detail['taskInfo']['algorithmId'] == uid('algorithm')
    invoke(workspace, 'train', 'start', uid('train'))
    invoke(workspace, 'train', 'cancel', uid('train'), '--yes')
    result = json.loads(invoke(workspace, 'train', 'history', 'list', uid('train'), '-o', 'json').stdout)
    assert all(j['status'] == 'cancelled' for j in result['items'])
    with Store(workspace).transaction() as db:
        assert Store.get(db, business_ids('demo-dev')[1], 'train', uid('train'))['jobStatus'] == 'cancelled'
    invoke(workspace, 'train', 'history', 'logs', 'download', uid('train'), uid('job'),
           '--file', workspace/'exports/logs.zip')
    invoke(workspace, 'offline', 'experiment', 'clone', uid('project'), '--name', 'offline-copy', '--yes')
    invoke(workspace, 'service', 'logs', uid('service'), '--pod', uid('service')+'-1',
           '--cluster-name', 'demo-cluster', '--type', 'run', '--file', 'application.log', '--no-input')
    for args in [('feature', 'list'), ('environment', 'get'), ('config', 'list'), ('metrics',)]:
        invoke(workspace, 'mtp', 'swanboard', 'experiment', *args, uid('experiment'))
    invoke(workspace, 'business', 'use', '--tenant', business_ids('demo-dev')[0], '--team', business_ids('demo-dev')[2])
    assert json.loads(invoke(workspace, 'train', 'list', '-o', 'json').stdout)['count'] == 25
    invoke(workspace, 'history', 'clear', '--yes')
    invoke(workspace, 'logout', '--all')
    invoke(workspace, 'auth', 'status', success=False)
