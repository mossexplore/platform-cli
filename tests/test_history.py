"""本地历史的命令生命周期、脱敏和文本持久化。"""

import inspect
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.history_store import HistoryStore
from wiserec_cli.history_recording import safe_command
from wiserec_cli.runtime import Runtime


@pytest.fixture
def config(tmp_path, monkeypatch):
    monkeypatch.setenv('ML_HISTORY', '1')
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'current': 'dev', 'access_control': {'enable': False},
        'profiles': [{'name': 'dev', 'api_endpoint': 'https://example.com'}]}))
    return path


def invoke(config, args, **kwargs):
    options = {"mix_stderr": False} if "mix_stderr" in inspect.signature(CliRunner).parameters else {}
    return CliRunner(**options).invoke(app, ['--config', str(config)] + args, **kwargs)


def record(index=0):
    return {'command': 'ml dataset list', 'time': '2026-10-09 12:00:00',
            'started_at': index, 'status': 'success', 'env': 'dev'}


def test_success_failure_parse_error_and_context(config):
    result = invoke(config, ['env', 'show'])
    assert result.exit_code == 0, result.output
    failed = invoke(config, ['not-a-command'])
    assert failed.exit_code == 2
    rows = HistoryStore(config).read()
    assert [row['exit_code'] for row in rows] == [0, 2]
    assert rows[0]['env'] == 'dev'
    assert rows[0]['config'] == str(config)
    assert rows[0]['duration_ms'] >= 0
    assert rows[1]['status'] == 'failed'


def test_history_without_valid_config_and_self_exclusion(config):
    store = HistoryStore(config)
    store.append(record())
    config.write_text('broken config')
    result = invoke(config, ['history', 'list', '-o', 'json'])
    assert result.exit_code == 0, result.output
    assert len(json.loads(result.stdout)) == 1
    assert len(store.read()) == 1
    assert invoke(config, ['history']).exit_code == 0


def test_opt_out_and_help(config, monkeypatch):
    for args in [['--no-history', 'env', 'show'], ['env', '--help'], ['--version'], ['tree']]:
        assert invoke(config, args).exit_code == 0
    monkeypatch.setenv('ML_HISTORY', '0')
    assert invoke(config, ['env', 'show']).exit_code == 0
    assert not (config.parent / 'history.jsonl').exists()


def test_filters_and_clear_without_sequence(config):
    store = HistoryStore(config)
    store.append(record(1))
    store.append({**record(2), 'env': 'test', 'status': 'failed'})
    result = invoke(config, ['history', 'list', '--env', 'test', '--status', 'failed', '-o', 'json'])
    rows = json.loads(result.stdout)
    assert len(rows) == 1 and rows[0]['env'] == 'test'
    assert all('id' not in row and '_key' not in row for row in rows)
    assert invoke(config, ['history', 'clear']).exit_code != 0
    assert len(store.read()) == 2
    assert invoke(config, ['history', 'clear', '--env', 'dev', '--yes']).exit_code == 0
    assert len(store.read()) == 1
    assert invoke(config, ['history', 'clear', '--yes']).exit_code == 0
    store.append(record(3))
    assert store.read()[0]['started_at'] == 3
    assert not (config.parent / 'history.seq').exists()


def test_before_is_exclusive_beijing(config):
    from datetime import datetime
    from wiserec_cli.models import BEIJING_TIMEZONE
    cutoff = datetime(2026, 10, 1, tzinfo=BEIJING_TIMEZONE).timestamp()
    store = HistoryStore(config)
    store.append(record(cutoff - 1))
    store.append(record(cutoff))
    assert invoke(config, ['history', 'clear', '--before', '2026-10-01 00:00:00', '--yes']).exit_code == 0
    assert [row['started_at'] for row in store.read()] == [cutoff]


def test_retention_and_damaged_tail(config):
    store = HistoryStore(config)
    records = [{**record(i), 'id': i + 1} for i in range(1000)]
    store.path.write_text(''.join(json.dumps(row) + '\n' for row in records) + '{broken')
    store.append(record(1001))
    rows = store.read()
    assert len(rows) == 1000
    assert rows[0]['started_at'] == 1 and rows[-1]['started_at'] == 1001
    assert all('id' not in row and '_key' not in row for row in rows)


def test_sensitive_commands_never_reach_disk(config):
    args = ['train', 'start', 'id', '--token=private-token', '--password', 'private-password']
    invoke(config, args)
    text = (config.parent / 'history.jsonl').read_text()
    assert 'private-token' not in text and 'private-password' not in text
    assert 'REDACTED' in text
    args = ['jupyter', 'exec', '--', 'python', '-c', 'very-private-script']
    invoke(config, args)
    assert 'very-private-script' not in (config.parent / 'history.jsonl').read_text()
    assert '\x1b' not in safe_command(['bad\x1b[31m'], ['bad\x1b[31m'])


def test_history_io_failure_preserves_command_result(config):
    with patch.object(HistoryStore, 'append', side_effect=OSError('disk full')):
        result = invoke(config, ['env', 'show'])
    assert result.exit_code == 0, result.output
    assert '无法保存' in result.stderr


def append_worker(args):
    config, index = args
    HistoryStore(Path(config)).append(record(index))


def test_multiple_processes_preserve_records(config):
    with ProcessPoolExecutor(max_workers=3) as pool:
        list(pool.map(append_worker, [(str(config), i) for i in range(15)]))
    rows = HistoryStore(config).read()
    assert len(rows) == 15
    assert sorted(row['started_at'] for row in rows) == list(range(15))


def test_interrupt_is_recorded(config):
    with patch.object(Runtime, 'authenticated_call', side_effect=KeyboardInterrupt):
        result = invoke(config, ['train', 'start', 'id'])
    assert result.exit_code != 0
    row = HistoryStore(config).read()[0]
    assert row['status'] == 'interrupted' and row['exit_code'] == 130


def test_environment_switch_remembers_before_and_after(config):
    data = json.loads(config.read_text())
    data['profiles'].append({'name': 'test', 'api_endpoint': 'https://test.example.com'})
    config.write_text(json.dumps(data))
    with patch('wiserec_cli.commands.env.ping.detach'), patch('wiserec_cli.commands.env.ping.auto_start'):
        result = invoke(config, ['env', 'use', 'test'])
    assert result.exit_code == 0, result.output
    row = HistoryStore(config).read()[0]
    assert row['env'] == 'dev' and row['env_after'] == 'test'


def test_clear_preserves_records_added_during_confirmation(config):
    store = HistoryStore(config)
    store.append(record(1))
    def confirm(count):
        assert count == 1
        store.append(record(2))
        return True
    assert store.remove(lambda row: True, confirm) == 1
    assert [row['started_at'] for row in store.read()] == [2]


def test_config_environment_variable_and_history_json(config, monkeypatch):
    monkeypatch.setenv('ML_CONFIG', str(config))
    assert CliRunner().invoke(app, ['env', 'show']).exit_code == 0
    result = CliRunner().invoke(app, ['history', 'list', '-o', 'json'])
    rows = json.loads(result.stdout)
    assert len(rows) == 1 and rows[0]['env'] == 'dev'


def test_history_warning_does_not_pollute_json_stdout(config):
    from wiserec_cli.services.dataset import DatasetService
    from test_runtime import RuntimeBusinessContextTest
    fixture = RuntimeBusinessContextTest()
    fixture.setUp()
    try:
        fixture.store.select('dev', 'jack', tenant_id='mep')
        with patch('wiserec_cli.cli.Runtime', return_value=fixture.runtime), patch.object(
            DatasetService, 'list_datasets', return_value={'items': [], 'total': 0}), patch.object(
            HistoryStore, 'append', side_effect=OSError('disk full')):
            result = invoke(config, ['dataset', 'list', '-o', 'json'])
        assert result.exit_code == 0, result.output
        assert json.loads(result.stdout) == {'items': [], 'total': 0}
    finally:
        fixture.tearDown()


def test_history_location_default_and_explicit(tmp_path, monkeypatch):
    from wiserec_cli.history_recording import config_location
    monkeypatch.chdir(tmp_path)
    with patch('wiserec_cli.history_recording.user_config_dir', return_value=tmp_path / 'user'):
        assert config_location() == tmp_path / 'user' / 'config.json'
        (tmp_path / 'config.json').touch()
        assert config_location() == tmp_path / 'config.json'
        assert config_location('other.json') == tmp_path / 'other.json'


def test_list_keeps_literal_markup_in_command(config):
    HistoryStore(config).append({**record(), 'command': 'ml dataset list --name "[/red]"'})
    result = invoke(config, ['history', 'list'])
    assert result.exit_code == 0, result.output
    assert '[/red]' in result.stdout


def test_interactive_pages_and_snapshot(config):
    from wiserec_cli.commands import history as command
    store = HistoryStore(config)
    for index in range(45):
        store.append(record(index))
    pages = []
    answers = iter(['n', 'p', 'n', 'n', 'q'])
    first = True
    def prompt(*args, **kwargs):
        nonlocal first
        if first:
            store.append(record(100))
            first = False
        return next(answers)
    with patch.object(command, 'can_browse', return_value=True), patch.object(
        command, 'render_rows', side_effect=lambda rows: pages.append([row['started_at'] for row in rows])), patch(
        'wiserec_cli.commands.history.click.prompt', side_effect=prompt):
        result = invoke(config, ['history'])
    assert result.exit_code == 0, result.output
    assert [len(page) for page in pages] == [20, 20, 20, 20, 5]
    assert pages[0] == pages[2] and pages[1] == pages[3]
    assert all(100 not in page for page in pages)
    assert '第 3 / 3 页' in result.stdout and '共 45 条记录' in result.stdout


def test_interactive_boundaries_invalid_and_case_insensitive(config):
    from wiserec_cli.commands import history as command
    HistoryStore(config).append(record())
    with patch.object(command, 'can_browse', return_value=True), patch.object(
        command.click, 'prompt', side_effect=['p', 'n', 'bad', '', ' Q ']):
        result = invoke(config, ['history'])
    assert result.exit_code == 0, result.output
    assert '已经是第一页' in result.stdout
    assert '已经是最后一页' in result.stdout
    assert '请输入 n、p 或 q' in result.stdout


@pytest.mark.parametrize('error', [KeyboardInterrupt, EOFError])
def test_interactive_interrupt_and_eof_exit_cleanly(config, error):
    from wiserec_cli.commands import history as command
    HistoryStore(config).append(record())
    with patch.object(command, 'can_browse', return_value=True), patch.object(
        command.click, 'prompt', side_effect=error):
        result = invoke(config, ['history'])
    assert result.exit_code == 0, result.output
    assert len(HistoryStore(config).read()) == 1


def test_empty_interactive_history_does_not_prompt(config):
    from wiserec_cli.commands import history as command
    with patch.object(command, 'can_browse', return_value=True), patch.object(command.click, 'prompt') as prompt:
        result = invoke(config, ['history'])
    assert result.exit_code == 0, result.output
    assert '暂无匹配' in result.stdout
    prompt.assert_not_called()


def test_json_and_noninteractive_are_one_shot(config):
    from wiserec_cli.commands import history as command
    store = HistoryStore(config)
    for index in range(25):
        store.append(record(index))
    with patch.object(command, 'can_browse', return_value=True), patch.object(command.click, 'prompt') as prompt:
        result = invoke(config, ['history', 'list', '-o', 'json'])
    assert len(json.loads(result.stdout)) == 20
    prompt.assert_not_called()
    pages = []
    with patch.object(command, 'can_browse', return_value=False), patch.object(command.click, 'prompt') as prompt, patch.object(
        command, 'render_rows', side_effect=lambda rows: pages.append(rows)):
        result = invoke(config, ['history'])
    assert result.exit_code == 0
    assert len(pages) == 1 and len(pages[0]) == 20
    prompt.assert_not_called()


def test_interactive_filter_and_explicit_limit(config):
    from wiserec_cli.commands import history as command
    store = HistoryStore(config)
    for index in range(30):
        store.append({**record(index), 'env': 'dev' if index % 2 else 'test'})
    pages = []
    with patch.object(command, 'can_browse', return_value=True), patch.object(command.click, 'prompt', return_value='q'), patch.object(
        command, 'render_rows', side_effect=lambda rows: pages.append(rows)):
        result = invoke(config, ['history', 'list', '--env', 'dev', '--limit', '10'])
    assert result.exit_code == 0, result.output
    assert len(pages[0]) == 10 and all(row['env'] == 'dev' for row in pages[0])
    assert '共 10 条记录' in result.stdout


def test_redirected_stdout_disables_browsing():
    from types import SimpleNamespace
    from unittest.mock import Mock
    from wiserec_cli.commands import history as command
    with patch.object(command, 'sys', SimpleNamespace(
        stdin=Mock(isatty=lambda: True), stdout=Mock(isatty=lambda: False))):
        assert not command.can_browse()


@pytest.mark.parametrize('name', ['show', 'delete'])
def test_single_record_commands_are_removed(config, name):
    result = invoke(config, ['history', name, '1'])
    assert result.exit_code == 2
    result = invoke(config, ['history', '--help'])
    assert name not in result.stdout


def test_legacy_numbered_records_hide_ids_and_ignore_sequence_file(config):
    store = HistoryStore(config)
    store.path.write_text(json.dumps({**record(), 'id': 128}) + '\n')
    (config.parent / 'history.seq').write_text('not a sequence')
    table = invoke(config, ['history'])
    assert table.exit_code == 0, table.output
    assert '序号' not in table.stdout and '128' not in table.stdout
    rows = json.loads(invoke(config, ['history', 'list', '-o', 'json']).stdout)
    assert rows == [record()]
    store.append(record(1))
    assert len(store.read()) == 2
    assert all('id' not in row for row in map(json.loads, store.path.read_text().splitlines()))
    assert (config.parent / 'history.seq').read_text() == 'not a sequence'


def test_clear_does_not_remove_identical_replacement_record(config):
    store = HistoryStore(config)
    store.append(record(1))
    def confirm(count):
        store.remove(lambda row: True, lambda count: True)
        store.append(record(1))
        return True
    assert store.remove(lambda row: True, confirm) == 0
    assert store.read() == [record(1)]
