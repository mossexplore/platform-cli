import json
import shlex
from unittest.mock import patch
from typer.testing import CliRunner
from wiserec_cli.cli import app
from wiserec_cli.runtime import Runtime
from wiserec_cli.invocation import format_invocation, MAX_COMMAND_LENGTH


def test_full_invocation_keeps_root_options_and_argument_values(tmp_path):
    config = tmp_path / 'config with spaces.json'
    config.write_text(json.dumps({'current': 'dev', 'profiles': [
        {'name': 'dev', 'api_endpoint': 'https://platform.example.com'}]}))
    captured = []
    def capture(runtime, operation):
        captured.append(runtime.full_command)
        return 'job-id'
    with patch.object(Runtime, 'authenticated_call', capture):
        for task in ['task with spaces', 'second-task']:
            result = CliRunner().invoke(app, ['--config', str(config), 'train', 'start', task])
            assert result.exit_code == 0, result.output
    assert shlex.split(captured[0]) == ['ml', '--config', str(config), 'train', 'start', 'task with spaces']
    assert 'second-task' in captured[1] and 'task with spaces' not in captured[1]


def test_sensitive_options_and_url_credentials_are_hidden():
    result = format_invocation(['train', 'start', 'task-id', '--password', 'private-password',
        '--token=private-token', '--header', 'Authorization: Bearer private-header',
        '--json', '{"password":"private-json"}', 'secret=private-setting',
        'https://user:private-url@example.com', 'https://example.com?token=private-query'])
    assert 'private-' not in result
    assert 'task-id' in result and 'REDACTED' in result


def test_long_command_is_explicitly_truncated():
    result = format_invocation(['train', 'start', 'x' * 9000])
    assert len(result) == MAX_COMMAND_LENGTH
    assert result.endswith('[已截断]')
