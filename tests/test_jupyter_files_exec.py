import base64
import json
import sys
from unittest.mock import Mock, patch

import httpx
import pytest
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.jupyter.connection import Connection, JupyterClient, JupyterError
from wiserec_cli.jupyter import files
from wiserec_cli.jupyter.exec_worker import run_process
from wiserec_cli.jupyter.execution import execute, MIME


def test_file_roundtrip_headers_overwrite_and_paths(tmp_path):
    saved = {}
    def respond(request):
        assert request.headers['businessid'] == 'selected-business'
        assert request.headers['Authorization'] == 'token test-token'
        assert request.url.path.startswith('/prefix/api/contents/')
        path = request.url.path.split('/contents/')[1]
        if request.method == 'GET':
            return httpx.Response(200, json=saved[path]) if path in saved else httpx.Response(404)
        if request.method == 'PUT':
            saved[path] = json.loads(request.content)
            saved[path]['path'] = path
            return httpx.Response(201, json=saved[path])
        raise AssertionError(request.method)
    with JupyterClient(Connection('http://localhost/prefix/', 'test-token', 'selected-business'),
                       transport=httpx.MockTransport(respond)) as client:
        data = b'\x00\xff\x01\n'
        files.save(client, '中文 a.bin', data)
        with pytest.raises(JupyterError, match='overwrite'):
            files.save(client, '中文 a.bin', b'other')
        local = tmp_path / 'file.bin'
        files.download(client, '中文 a.bin', local)
        assert local.read_bytes() == data
        with pytest.raises(FileExistsError):
            files.download(client, '中文 a.bin', local)
        files.save(client, '中文 a.bin', b'new', overwrite=True)
        assert base64.b64decode(saved['中文 a.bin']['content']) == b'new'
        for path in ('', '../escape', '/absolute', 'a/../b'):
            with pytest.raises(JupyterError):
                files.save(client, path, b'x')


@pytest.mark.parametrize('status', [403, 500])
def test_absent_does_not_treat_other_errors_as_missing(status):
    seen = []
    def respond(request):
        seen.append(request.method)
        return httpx.Response(status)
    with JupyterClient(Connection('http://localhost/', 't', 'b'), transport=httpx.MockTransport(respond)) as client:
        with pytest.raises(JupyterError):
            files.save(client, 'file', b'x')
    assert seen == ['GET']


def test_directories_copy_move_delete_guards():
    client = Mock()
    client.contents.side_effect = lambda path: 'api/contents/' + path
    client.request.return_value = {'type': 'directory', 'content': [{'name': 'child'}]}
    with pytest.raises(JupyterError, match='空目录'):
        files.delete(client, 'dir')
    with pytest.raises(JupyterError, match='单文件'):
        files.copy(client, 'dir', 'other')
    with pytest.raises(JupyterError, match='目标已存在'):
        files.move(client, 'source', 'dir')
    assert all(call.args[0] == 'GET' for call in client.request.call_args_list)


@pytest.fixture
def cli_client(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'current': 'dev', 'access_control': {'enable': False},
                                 'profiles': [{'name': 'dev', 'api_endpoint': 'http://localhost/'}]}))
    client = Mock()
    client.contents.side_effect = lambda path: 'api/contents/' + path
    client.connection = Connection('http://localhost/', 't', 'business', studio_id='studio')
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    with patch('wiserec_cli.commands.jupyter.client_for', return_value=client):
        yield ['--config', str(config), 'jupyter'], client


def test_write_stdin_and_json_envelope(cli_client):
    args, client = cli_client
    with patch('wiserec_cli.commands.jupyter_files.files.save', return_value={'path': 'a.py'}) as save:
        result = CliRunner().invoke(app, args + ['files', 'write', 'a.py', '--stdin', '-o', 'json'], input='print(1)')
    assert result.exit_code == 0, result.output
    assert save.call_args.args[2] == b'print(1)'
    envelope = json.loads(result.stdout)
    assert envelope['business_id'] == 'business'
    assert envelope['studio_id'] == 'studio'


def test_read_lines_and_invalid_range(cli_client):
    args, client = cli_client
    client.request.return_value = {'content': 'one\ntwo\nthree\n'}
    result = CliRunner().invoke(app, args + ['files', 'read', 'a', '--start-line', '2', '--end-line', '2', '-o', 'json'])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)['result']['content'] == 'two\n'
    result = CliRunner().invoke(app, args + ['files', 'read', 'a', '--start-line', '3', '--end-line', '2', '-o', 'json'])
    assert result.exit_code == 1
    assert json.loads(result.stdout)['status'] == 'FAILED'


def test_exec_argument_boundaries_and_exit(cli_client):
    args, client = cli_client
    with patch('wiserec_cli.commands.jupyter_exec.execute', return_value={'status': 'FAILED', 'exit_code': 7}) as run:
        result = CliRunner().invoke(app, args + ['exec', '-o', 'json', '--', 'python', '-c', 'print("x y")'])
    assert result.exit_code == 7, result.output
    assert run.call_args.args[1] == ['python', '-c', 'print("x y")']
    assert json.loads(result.stdout)['result']['exit_code'] == 7


def test_worker_separates_streams_and_preserves_literal_args():
    code = 'import sys; print(sys.argv[1]); print("err", file=sys.stderr); sys.exit(7)'
    result = run_process([sys.executable, '-c', code, '$(echo secret); a b'], 5, 1024)
    assert result['exit_code'] == 7
    assert result['stdout'] == '$(echo secret); a b\n'
    assert result['stderr'] == 'err\n'


def test_worker_timeout_and_bounded_output():
    result = run_process([sys.executable, '-u', '-c', 'import time; print("start"); time.sleep(30)'], .1, 1024)
    assert result['status'] == 'TIMED_OUT'
    assert result['termination'] == 'process_group_killed'
    result = run_process([sys.executable, '-c', 'import sys; sys.stdout.write("x"*200000); sys.stderr.write("y"*200000)'], 5, 100)
    assert result['status'] == 'SUCCEEDED'
    assert result['stdout'] == 'x' * 100
    assert result['stderr'] == 'y' * 100
    assert result['truncated']


def msg(kind, content):
    return {'header': {'msg_type': kind}, 'content': content}


@pytest.mark.parametrize('lost', [False, True])
def test_execution_result_and_cleanup(lost):
    client = Mock()
    client.contents.side_effect = lambda path: 'api/contents/' + path
    client.connection.kernel = 'python3'
    client.request.side_effect = [{'type': 'directory'}, {'id': 'owned'}, None]
    channel = Mock()
    channel.ready.return_value = {'language_info': {'name': 'python'}}
    if lost:
        channel.messages.side_effect = JupyterError('连接中断')
    else:
        channel.messages.return_value = iter([
            msg('display_data', {'data': {MIME: {'status': 'SUCCEEDED', 'exit_code': 0, 'stdout': 'ok', 'stderr': ''}}}),
            msg('execute_reply', {'status': 'ok'}), msg('status', {'execution_state': 'idle'})])
    with patch('wiserec_cli.jupyter.execution.KernelChannel', return_value=channel):
        result = execute(client, ['echo', 'ok'])
    assert result['status'] == ('LOST' if lost else 'SUCCEEDED')
    assert result['remote_state'] == ('unknown' if lost else 'finished')
    client.request.assert_any_call('DELETE', 'api/kernels/owned')
    assert channel.send.call_count == 1


def test_agent_commands_suppress_connection_token_diagnostics(tmp_path):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'current': 'dev', 'access_control': {'enable': False},
                                 'profiles': [{'name': 'dev', 'api_endpoint': 'http://localhost/'}]}))
    client = Mock()
    client.connection = Connection('http://localhost/', 'secret-token', 'b')
    client.__enter__ = Mock(return_value=client)
    client.__exit__ = Mock(return_value=False)
    client.contents.return_value = 'api/contents/a'
    client.request.return_value = {'type': 'file'}
    def factory(context, studio_id, report):
        report('https://host/lab?token=secret-token')
        return client
    with patch('wiserec_cli.commands.jupyter.client_for', side_effect=factory):
        result = CliRunner().invoke(app, ['--config', str(config), 'jupyter', 'files', 'stat', 'a', '-o', 'json'])
    assert result.exit_code == 0
    assert 'secret-token' not in result.output
