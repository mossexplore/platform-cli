"""具体环境禁止 Jupyter 上传下载，保持其他入口不受影响。"""
import json
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.config import ConfigManager, _sync_packaged_config
from wiserec_cli.command_policy import parse_policy, require_command
from wiserec_cli.errors import ConfigError, MlError

DENY = ['jupyter files upload', 'jupyter files download']


def configuration(tmp_path, platform='wiserec'):
    path = tmp_path / 'config.json'
    path.write_text(json.dumps({'current': 'restricted', 'profiles': [
        {'name': 'restricted', 'platform_type': platform, 'api_endpoint': 'https://restricted.example',
         'command_policy': {'deny': DENY}},
        {'name': 'allowed', 'platform_type': platform, 'api_endpoint': 'https://allowed.example'},
    ]}))
    return path


@pytest.mark.parametrize('platform', ['wiserec', 'mlops'])
@pytest.mark.parametrize('command,args', [
    ('upload', ['missing-local-file', 'remote']), ('download', ['remote', 'local']),
])
def test_rejects_before_login_ping_or_jupyter(tmp_path, platform, command, args):
    config = configuration(tmp_path, platform)
    with patch('wiserec_cli.auth.AuthManager.ensure_credentials', side_effect=AssertionError('must not login')), \
         patch('wiserec_cli.cli.sys.stdin.isatty', return_value=True), \
         patch('wiserec_cli.cli.ping.auto_start', side_effect=AssertionError('must not ping')), \
         patch('wiserec_cli.commands.jupyter_files.operation', side_effect=AssertionError('must not connect')):
        result = CliRunner().invoke(app, ['--config', str(config), 'jupyter', 'files', command, *args])
    assert result.exit_code == 1
    assert 'restricted' in result.output and '禁止执行 ml jupyter files ' + command in result.output
    assert not (tmp_path / 'local').exists()


def test_tree_filter_marker_and_environment_switch(tmp_path):
    config = configuration(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ['--config', str(config), 'tree'])
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
    result = runner.invoke(app, ['--config', str(config), 'tree', '--all'])
    assert result.exit_code == 0 and '[当前环境禁用]' in result.output
    manager = ConfigManager(config)
    manager.use_profile('allowed')
    result = runner.invoke(app, ['--config', str(config), 'tree', '--all'])
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
    result = CliRunner().invoke(app, ['--config', str(config), 'jupyter', 'files', 'upload', '--help'])
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize('value', [None, [], {'allow': []}, {'deny': 'jupyter files upload'},
    {'deny': [None]}, {'deny': ['ml jupyter files upload']}, {'deny': ['jupyter files *']},
    {'deny': ['jupyter exec']}, {'deny': [DENY[0], DENY[0]]}])
def test_invalid_policy_rejected(value):
    with pytest.raises(ConfigError):
        parse_policy(value)


@pytest.mark.parametrize('platform', ['wiserec', 'mlops'])
def test_reinstall_preserves_profile_policy(tmp_path, platform):
    config = configuration(tmp_path, platform)
    template = json.dumps({'current': 'allowed', 'profiles': [
        {'name': 'allowed', 'api_endpoint': 'https://new.example'},
        {'name': 'restricted', 'api_endpoint': 'https://template.example'}]})
    with patch('wiserec_cli.config._packaged_config_text', return_value=template):
        _sync_packaged_config(config, force=True)
    profile = ConfigManager(config).current_profile()
    assert profile.denied_commands == tuple(DENY)
    assert profile.platform_type == platform
    assert profile.api_endpoint == 'https://restricted.example'


def test_runtime_rejects_without_authentication(tmp_path):
    from wiserec_cli.runtime import Runtime
    runtime = Runtime(config_path=configuration(tmp_path), credential_path=tmp_path / 'credentials.json',
                      business_path=tmp_path / 'business.json')
    runtime.invocation_command = 'ml jupyter files download'
    with patch.object(runtime.auth, 'ensure_credentials', side_effect=AssertionError('must not login')):
        with pytest.raises(MlError, match='禁止执行'):
            runtime.authenticated_call(lambda client: pytest.fail('must not request'))
