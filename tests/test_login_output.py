"""Login output stays concise without hiding actionable failures or secrets opt-in."""
import io
import sys
import types
from unittest.mock import Mock, patch

import pytest
from rich.console import Console

from wiserec_cli.auth import BrowserAuthenticator
from wiserec_cli.credentials import CredentialStore
from wiserec_cli.errors import AuthenticationError
from wiserec_cli.models import Credentials, Profile
from wiserec_cli.login_output import LoginProgress
from test_auth import FakePersistentContext, FakePlaywright, FakePlaywrightManager


def run_login(tmp_path, *, alias='镜像环境', show_secrets=False, failure=False):
    output = io.StringIO()
    console = Console(file=output, width=110, force_terminal=False)
    context = FakePersistentContext()
    playwright = FakePlaywright(context)
    module = types.ModuleType('playwright.sync_api')
    module.sync_playwright = lambda: FakePlaywrightManager(playwright)
    business = Mock()
    business.require_selection.return_value.business_id = 'selected-business'
    auth = BrowserAuthenticator(CredentialStore(tmp_path/'credentials.json'), business)
    credentials = Credentials.create('mirror', 'secret-cookie', 'secret-csrf', 'l00123456', 600)
    auth._wait_for_credentials = Mock(side_effect=[None, None] if failure else [None, credentials])
    with patch.dict(sys.modules, {'playwright.sync_api': module}), \
         patch('wiserec_cli.login_output.console', console), \
         patch('wiserec_cli.auth.console', console), \
         patch('wiserec_cli.output.console', console), \
         patch('wiserec_cli.auth._wait_for_edge') as wait, \
         patch('builtins.print', side_effect=lambda *args: output.write(' '.join(map(str,args))+'\n')):
        try:
            auth.login(Profile(name='mirror', alias=alias, api_endpoint='https://example.com/dashboard'),
                       1000, 600, tmp_path/'browser', 'msedge', 100, 1000,
                       show_secrets=show_secrets)
        except AuthenticationError:
            if not failure and alias.strip():
                raise
    return output.getvalue(), playwright, wait


def test_success_uses_alias_and_five_fields_without_technical_logs(tmp_path):
    text, browser, _ = run_login(tmp_path)
    assert '正在登录【镜像环境】' in text and '登录成功，用户信息如下：' in text
    assert all(key in text for key in ('环境', '账号', '中文名', '部门', 'businessId'))
    assert 'selected-business' in text and '未获取' in text
    assert browser.context.closed
    for hidden in ('mirror', 'Edge Profile', 'ai-businessList', '持久 Edge', 'secret-cookie', 'secret-csrf', '\x1b['):
        assert hidden not in text


def test_secrets_remain_explicit_opt_in(tmp_path):
    text, _, _ = run_login(tmp_path, show_secrets=True)
    assert 'cookie: secret-cookie' in text and 'csrftoken: secret-csrf' in text


@pytest.mark.parametrize('alias', ['', '  '])
def test_missing_alias_does_not_launch_browser(tmp_path, alias):
    with pytest.raises(AuthenticationError, match='alias'):
        LoginProgress(alias)
    _, browser, _ = run_login(tmp_path, alias=alias)
    assert browser.launch_arguments is None


def test_login_timeout_never_prints_success_table(tmp_path):
    text, _, wait = run_login(tmp_path, failure=True)
    assert '等待登录超时' in text
    assert '登录成功' not in text and 'businessId' not in text
    wait.assert_called_once()


def test_spinner_updates_and_stops_on_failure():
    console = Mock(is_terminal=True, is_dumb_terminal=False)
    status = console.status.return_value
    with patch('wiserec_cli.login_output.console', console):
        with pytest.raises(RuntimeError):
            with LoginProgress('镜像环境') as progress:
                progress.update('等待浏览器完成登录…')
                raise RuntimeError('failed')
    status.start.assert_called_once()
    status.update.assert_called_once_with('等待浏览器完成登录…')
    status.stop.assert_called_once()


@pytest.mark.parametrize('message,visible', [
    ('自动保活已启动（环境 mirror，间隔 10 分钟）', False),
    ('当前不是交互式终端，未启动自动保活', False),
    ('警告：自动保活启动失败：网络不可用', True),
    ('尚未选择业务，选择后将启动自动保活', True),
])
def test_login_only_keeps_actionable_ping_messages(message, visible):
    from wiserec_cli.commands.auth import login
    runtime = Mock()
    runtime.config.auto_ping = True
    console = Mock()
    with patch('wiserec_cli.commands.auth.runtime_from_context', return_value=runtime), \
         patch('wiserec_cli.commands.auth.show_access_guidance', return_value=True), \
         patch('wiserec_cli.commands.auth.ping.auto_start', return_value=message), \
         patch('wiserec_cli.commands.auth.console', console):
        login(None, False)
    assert console.print.called is visible


@pytest.mark.parametrize('previous', [None, '0', '1'])
@pytest.mark.parametrize('failure', [False, True])
def test_node_warning_setting_restored_even_on_failure(monkeypatch, previous, failure):
    import os
    from wiserec_cli.login_output import quiet_node_warnings
    if previous is None:
        monkeypatch.delenv('NODE_NO_WARNINGS', raising=False)
    else:
        monkeypatch.setenv('NODE_NO_WARNINGS', previous)
    monkeypatch.setenv('NODE_TLS_REJECT_UNAUTHORIZED', '0')
    try:
        with quiet_node_warnings():
            assert os.environ['NODE_NO_WARNINGS'] == '1'
            assert os.environ['NODE_TLS_REJECT_UNAUTHORIZED'] == '0'
            if failure:
                raise RuntimeError('login failed')
    except RuntimeError:
        assert failure
    assert os.environ.get('NODE_NO_WARNINGS') == previous
    assert os.environ['NODE_TLS_REJECT_UNAUTHORIZED'] == '0'


def test_real_node_hides_warnings_but_keeps_errors(monkeypatch):
    import subprocess
    from playwright._impl._driver import compute_driver_executable
    from wiserec_cli.login_output import quiet_node_warnings
    node, _ = compute_driver_executable()
    monkeypatch.delenv('NODE_NO_WARNINGS', raising=False)
    script = "process.emitWarning('login driver warning'); console.error('login failed'); process.exitCode = 1"
    baseline = subprocess.run([node, '-e', script], capture_output=True, text=True)
    assert 'Warning: login driver warning' in baseline.stderr
    with quiet_node_warnings():
        result = subprocess.run([node, '-e', script], capture_output=True, text=True)
    assert 'Warning' not in result.stderr
    assert 'login failed' in result.stderr and result.returncode == 1
