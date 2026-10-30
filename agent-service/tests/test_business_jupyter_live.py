"""Opt-in disposable localhost server; never run this against a user's studio."""
import json
import os
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4
from urllib.parse import urlsplit
import nbformat
import pytest
from wiserec_cli.jupyter.connection import from_runtime
from wiserec_cli.runtime import Runtime
from app.artifacts import Artifacts
from app.jupyter_tools import dispatch
from conftest import BUSINESS

CONFIG = os.environ.get('ML_JUPYTER_TEST_CONFIG')
pytestmark = pytest.mark.skipif(not CONFIG, reason='需要隔离的本机 Jupyter 测试服务')


@pytest.fixture
def live(settings, monkeypatch):
    connection = from_runtime(Runtime(config_path=Path(CONFIG)))
    assert urlsplit(connection.url).hostname in ('127.0.0.1', 'localhost')
    monkeypatch.setattr('app.jupyter_tools.connection', lambda *_: connection)
    checks = []
    c = SimpleNamespace(agent_artifacts=Artifacts(settings, 's', BUSINESS), agent_transport=None,
        agent_guard=lambda: checks.append('permission'), agent_check=lambda: checks.append('session'))
    def invoke(tool_name, **a): return dispatch(c, tool_name, {'studio_id': 'test', **a})
    return c, invoke, checks


def test_real_contents_upload_download_move_copy_delete_and_execution(live):
    c, invoke, checks = live
    root = 'agent-test-' + uuid4().hex
    invoke('jupyter_files_mkdir', path=root)
    upload = c.agent_artifacts.put('data.bin', b'\x00\xffhello')
    invoke('jupyter_files_upload', path=root + '/data.bin', artifact_id=upload['artifact_id'], overwrite=False)
    downloaded = invoke('jupyter_files_download', path=root + '/data.bin')
    assert c.agent_artifacts.path(downloaded['artifact_id']).read_bytes() == b'\x00\xffhello'
    invoke('jupyter_files_write', path=root + '/a.txt', content='你好', overwrite=False)
    assert invoke('jupyter_files_read', path=root + '/a.txt')['content'] == '你好'
    invoke('jupyter_files_move', path=root + '/a.txt', destination=root + '/b.txt')
    copied = invoke('jupyter_files_copy', path=root + '/b.txt', destination=root)
    assert invoke('jupyter_files_stat', path=copied['path'])['type'] == 'file'
    result = invoke('jupyter_exec', argv=['python', '-c', 'print(6*7)'], cwd=root, timeout=15)
    assert result['status'] == 'SUCCEEDED', result
    assert result['exit_code'] == 0 and '42' in result['stdout'] and not result['cleanup_errors']
    for entry in invoke('jupyter_files_list', path=root)['content']:
        invoke('jupyter_files_delete', path=entry['path'])
    invoke('jupyter_files_delete', path=root)
    assert checks.count('permission') > 15


def test_real_notebook_execution_returns_downloadable_output(live):
    c, invoke, _ = live
    book = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell('print("AGENT_NOTEBOOK_OK")')])
    source = c.agent_artifacts.put('input.ipynb', nbformat.writes(book).encode())
    result = invoke('jupyter_notebook_run', artifact_id=source['artifact_id'], cwd='', timeout=15)
    assert result['status'] == 'SUCCEEDED', result
    output = nbformat.read(c.agent_artifacts.path(result['artifact']['artifact_id']), as_version=4)
    assert 'AGENT_NOTEBOOK_OK' in output.cells[0].outputs[0].text
    assert not result['cleanup_errors']
    # The CLI intentionally retains remote notebook results; remove this test's files.
    directory = result['remote_directory']
    for entry in invoke('jupyter_files_list', path=directory)['content']:
        invoke('jupyter_files_delete', path=entry['path'])
    invoke('jupyter_files_delete', path=directory)


def test_real_terminal_create_attach_read_and_close(live):
    _, invoke, _ = live
    created = invoke('jupyter_terminal_create')
    try:
        result = invoke('jupyter_terminal_attach', name=created['name'], input="printf 'AGENT_%s\\n' 'TERMINAL_OK'\n")
        assert 'AGENT_TERMINAL_OK' in ''.join(result['output'])
        assert any(x['name'] == created['name'] for x in invoke('jupyter_terminal_list'))
    finally:
        invoke('jupyter_terminal_stop', name=created['name'])
    assert not any(x['name'] == created['name'] for x in invoke('jupyter_terminal_list'))
