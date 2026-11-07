"""具体环境禁止 Jupyter 上传下载，保持其他入口不受影响。"""
import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.config import ConfigManager
from wiserec_cli.install_config import install_config
from wiserec_cli.command_policy import parse_policy, require_command
from wiserec_cli.errors import ConfigError, MlError
from cli_test_support import invoke_with_config

DENY = ['jupyter files upload', 'jupyter files download']


def configuration(tmp_path, platform='wiserec', rule=None):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'current': 'restricted', 'profiles': [
        {'name': 'restricted', 'platform_type': platform, 'api_endpoint': 'https://restricted.example',
         'command_policy': {'deny': [rule] if rule else ['ml ' + command for command in DENY]}},
        {'name': 'allowed', 'platform_type': platform, 'api_endpoint': 'https://allowed.example'},
    ]}))
    return path


@pytest.mark.parametrize('platform', ['wiserec', 'mlops'])
@pytest.mark.parametrize('rule', [None, 'ml jupyter', 'ml jupyter files'])
@pytest.mark.parametrize('command,args', [
    ('upload', ['missing-local-file', 'remote']), ('download', ['remote', 'local']),
])
def test_rejects_before_login_ping_or_jupyter(tmp_path, platform, rule, command, args):
    config = configuration(tmp_path, platform, rule)
    with patch('wiserec_cli.auth.AuthManager.ensure_credentials', side_effect=AssertionError('must not login')), \
         patch('wiserec_cli.cli.sys.stdin.isatty', return_value=True), \
         patch('wiserec_cli.cli.ping.auto_start', side_effect=AssertionError('must not ping')), \
         patch('wiserec_cli.commands.jupyter_files.operation', side_effect=AssertionError('must not connect')):
        result = invoke_with_config(CliRunner(), app, config, ['jupyter', 'files', command, *args])
    assert result.exit_code == 1
    assert 'restricted' in result.output and '禁止执行 ml jupyter files ' + command in result.output
    assert '请查看 command_policy' not in result.output
    assert not (tmp_path / 'local').exists()


def test_tree_filter_marker_and_environment_switch(tmp_path):
    config = configuration(tmp_path)
    runner = CliRunner()
    result = invoke_with_config(runner, app, config, ['tree'])
    assert result.exit_code == 0, result.output
    # 精确检查文件组，避免匹配数据集的同名命令。
    from rich.tree import Tree
    from wiserec_cli.commands.tree import _append_commands
    import typer
    group = typer.main.get_command(app).commands['jupyter'].commands['files']
    tree = Tree('files')
    _append_commands(tree, group, prefix='jupyter files', denied=DENY)
    assert all(not row.label.plain.startswith(('upload ', 'download ')) for row in tree.children)
    tree = Tree('files')
    _append_commands(tree, group, show_all=True, prefix='jupyter files', denied=DENY)
    for row in tree.children:
        if row.label.plain.startswith(('upload ', 'download ')):
            assert row.label.plain.endswith('[当前环境禁用]')
            assert row.label.spans[-1].style == 'red'
    result = invoke_with_config(runner, app, config, ['tree', '--all'])
    assert result.exit_code == 0 and '[当前环境禁用]' in result.output
    manager = ConfigManager(config)
    manager.use_profile('allowed')
    result = invoke_with_config(runner, app, config, ['tree', '--all'])
    assert result.exit_code == 0 and '[当前环境禁用]' not in result.output
    for command in DENY:
        require_command(manager.current_profile(), command)


def test_other_commands_remain_allowed_and_help_available(tmp_path):
    config = configuration(tmp_path, 'mlops')
    profile = ConfigManager(config).current_profile()
    for command in ['jupyter exec', 'jupyter notebook run', 'jupyter terminal open',
                    'jupyter files read', 'jupyter files write', 'dataset files upload',
                    'train history logs download']:
        require_command(profile, command)
    for command in DENY:
        with pytest.raises(MlError, match='禁止执行'):
            require_command(profile, command)
    result = invoke_with_config(CliRunner(), app, config, ['jupyter', 'files', 'upload', '--help'])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize('commands', [DENY, ['ml ' + command for command in DENY],
    ['ml jupyter files upload', 'jupyter files download'],
    [' ml  jupyter files upload ', 'ml\tjupyter files download']])
def test_full_and_legacy_paths_have_identical_policy(commands):
    assert parse_policy({'deny': commands}) == tuple(DENY)


@pytest.mark.parametrize('value', [None, [], {'allow': []}, {'deny': 'jupyter files upload'},
    {'deny': [None]}, {'deny': ['ml']}, {'deny': ['jupyter files *']},
    {'deny': ['ml env']}, {'deny': [DENY[0], DENY[0]]},
    {'deny': [DENY[0], 'ml ' + DENY[0]]},
    {'deny': ['ml jupyter files upload', ' ml  jupyter files upload ']}])
def test_invalid_policy_rejected(value):
    with pytest.raises(ConfigError):
        parse_policy(value)


@pytest.mark.parametrize('platform', ['wiserec', 'mlops'])
def test_reinstall_uses_packaged_profile_policy(tmp_path, platform):
    config = configuration(tmp_path, platform)
    template = json.dumps({'current': 'allowed', 'profiles': [
        {'name': 'allowed', 'api_endpoint': 'https://new.example'},
        {'name': 'restricted', 'api_endpoint': 'https://template.example'}]})
    with patch('wiserec_cli.install_config.packaged_config_text', return_value=template):
        install_config(config)
    profile = ConfigManager(config).current_profile()
    assert ConfigManager(config).current_name == 'restricted'
    assert profile.denied_commands == ()
    assert profile.platform_type == 'wiserec'
    assert profile.api_endpoint == 'https://template.example'


def test_runtime_rejects_without_authentication(tmp_path):
    from wiserec_cli.runtime import Runtime
    runtime = Runtime(config_path=configuration(tmp_path), credential_path=tmp_path / 'credentials.json',
                      business_path=tmp_path / 'business.json')
    runtime.invocation_command = 'ml jupyter files download'
    with patch.object(runtime.auth, 'ensure_credentials', side_effect=AssertionError('must not login')):
        with pytest.raises(MlError, match='禁止执行'):
            runtime.authenticated_call(lambda client: pytest.fail('must not request'))


@pytest.mark.parametrize('rule,blocked,allowed', [
    ('ml jupyter', ['jupyter', 'jupyter files upload', 'jupyter terminal open', 'jupyter exec'],
     ['jupyterx files upload', 'dataset files upload']),
    ('ml jupyter files', ['jupyter files', 'jupyter files upload', 'jupyter files download'],
     ['jupyter files-other upload', 'jupyter terminal open']),
    ('ml train', ['train list', 'train history logs download'], ['train-other list']),
])
def test_parent_rule_uses_command_boundaries(rule, blocked, allowed):
    from wiserec_cli.command_policy import is_denied
    rules = parse_policy({'deny': [rule]})
    assert all(is_denied(command, rules) for command in blocked)
    assert not any(is_denied(command, rules) for command in allowed)


def test_parent_policy_tree_hides_subtree_and_marks_all_descendants(tmp_path):
    from rich.tree import Tree
    from typer.main import get_command
    from wiserec_cli.commands.tree import _append_commands
    root = get_command(app)
    hidden = Tree('ml')
    _append_commands(hidden, root, denied=['jupyter'])
    assert not any(row.label.plain.startswith('jupyter ') for row in hidden.children)
    shown = Tree('ml')
    _append_commands(shown, root, show_all=True, denied=['jupyter'])
    jupyter = next(row for row in shown.children if row.label.plain.startswith('jupyter '))
    def marked(row):
        assert row.label.plain.endswith('[当前环境禁用]')
        assert row.label.spans[-1].style == 'red'
        for child in row.children:
            marked(child)
    marked(jupyter)
    config = configuration(tmp_path, rule='ml jupyter')
    for args in [['tree'], ['tree', '--all']]:
        result = invoke_with_config(CliRunner(), app, config, [*args])
        assert result.exit_code == 0, result.output
        assert ('[当前环境禁用]' in result.output) == ('--all' in args)
