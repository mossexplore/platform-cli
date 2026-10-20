"""真实消息渲染、终端颜色、参数解析与机器输出的兼容性。"""
import inspect
import io
import json
from unittest.mock import patch

import pytest
import typer
from rich.console import Console
from rich.progress import Progress
from typer.testing import CliRunner

from wiserec_cli import messages as msg
from wiserec_cli.cli import app
from wiserec_cli.commands.common import fail
from wiserec_cli.output import print_result


@pytest.fixture(autouse=True)
def isolated_messages(monkeypatch):
    monkeypatch.delenv('NO_COLOR', raising=False)
    monkeypatch.setenv('ML_HISTORY', '0')


@pytest.mark.parametrize('level,label,color', [
    ('info', '提示', 'cyan'), ('success', '成功', 'green'),
    ('warning', '警告', 'yellow'), ('error', '错误', 'red'),
])
def test_prefix_body_and_detail_colors(level, label, color):
    console = Console()
    text = msg.render('操作摘要\n补充说明', level)
    assert text.plain == f'[{label}] 操作摘要\n补充说明'
    assert text.get_style_at_offset(console, 1).color.name == color
    expected = color if level in {'warning', 'error'} else 'default'
    assert text.get_style_at_offset(console, 5).color.name == expected
    assert text.get_style_at_offset(console, text.plain.index('补充')).color.name == 'default'


@pytest.mark.parametrize('level', ['warning', 'error'])
def test_actions_commands_urls_and_ids_keep_default_color(level):
    console = Console()
    text = msg.render('请求失败 --page-size https://example.com 12345678-1234-1234-1234-123456789abc；请执行 ml auth ping start 重试', level)
    for token in ['--page-size', 'https://', '12345678', '请执行', 'ml auth']:
        assert text.get_style_at_offset(console, text.plain.index(token)).color.name == 'default'
    assert text.get_style_at_offset(console, text.plain.index('请求失败')).color.name in {'yellow', 'red'}


@pytest.mark.parametrize('prefix', ['警告：', '警告: ', '[警告] '])
def test_no_duplicate_prefix_and_untrusted_markup_is_literal(prefix):
    text = msg.render(prefix + '[bold]literal[/bold]\x1b[31m\x00', 'warning')
    assert text.plain == '[警告] [bold]literal[/bold]'


@pytest.mark.parametrize('terminal', [False, True])
@pytest.mark.parametrize('no_color', [False, True])
def test_actual_ansi_output_and_no_color(monkeypatch, terminal, no_color):
    if no_color:
        monkeypatch.setenv('NO_COLOR', '')
    stream = io.StringIO()
    console = Console(file=stream, force_terminal=terminal, color_system='standard')
    with patch.object(msg, 'error_console', console):
        for level in ['info', 'success', 'warning', 'error']:
            msg.emit('示例', level)
    output = stream.getvalue()
    assert ('\x1b[' in output) is (terminal and not no_color)
    for prefix in ['提示', '成功', '警告', '错误']:
        assert f'[{prefix}]' in output


def test_messages_do_not_pollute_json_or_change_failure_exit_code(capsys):
    msg.info('请等待')
    msg.success('完成')
    msg.warning('部分结果不可用')
    print_result({'items': ['[错误] 这是数据']}, 'json')
    with pytest.raises(typer.Exit) as exc:
        fail('请求失败')
    assert exc.value.exit_code == 1
    output = capsys.readouterr()
    assert json.loads(output.out) == {'items': ['[错误] 这是数据']}
    assert output.err.splitlines() == [
        '[提示] 请等待', '[成功] 完成', '[警告] 部分结果不可用', '[错误] 请求失败',
    ]


def runner():
    options = {'mix_stderr': False} if 'mix_stderr' in inspect.signature(CliRunner).parameters else {}
    return CliRunner(**options)


@pytest.mark.parametrize('args,expected', [
    (['--unknown'], '未知选项'), (['unknown'], '未知命令'),
    (['--config'], '需要参数值'),
])
def test_root_parser_errors_are_prefixed_and_chinese(args, expected):
    result = runner().invoke(app, args)
    assert result.exit_code == 2
    assert result.stdout == ''
    assert result.stderr.startswith('[错误] ')
    assert expected in result.stderr
    assert '请执行 ml --help 查看用法' in result.stderr
    assert '\x1b[' not in result.stderr


@pytest.mark.parametrize('args,expected', [
    (['env', 'use'], '缺少参数'),
    (['train', 'list', '--page', 'abc'], '不是有效整数'),
    (['train', 'list', '--page', '0'], '不在允许范围内'),
])
def test_nested_parser_errors(tmp_path, args, expected):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'current': 'dev', 'access_control': {'enable': False},
        'profiles': [{'name': 'dev', 'api_endpoint': 'https://example.com'}]}))
    result = runner().invoke(app, ['--config', str(config), *args])
    assert result.exit_code == 2
    assert result.stdout == ''
    assert result.stderr.startswith('[错误] ')
    assert expected in result.stderr
    assert '请执行 ml ' in result.stderr


def test_help_version_and_command_tree_remain_data():
    for args in [['--help'], ['--version'], ['tree']]:
        result = runner().invoke(app, args)
        assert result.exit_code == 0
        assert result.stdout
        assert result.stderr == ''


@pytest.mark.parametrize('answer,expected', [('y\n', True), ('n\n', False), ('\n', False), ('bad\ny\n', True)])
def test_confirmation_is_plain_and_invalid_answer_is_error(answer, expected):
    application = typer.Typer()

    @application.command()
    def execute():
        typer.echo(json.dumps({'confirmed': msg.confirm('确认执行？')}))

    result = runner().invoke(application, [], input=answer)
    assert result.exit_code == 0
    assert json.loads(result.stdout) == {'confirmed': expected}
    assert '确认执行？ [y/N]' in result.stderr
    assert ('[错误] 请输入 y 或 n' in result.stderr) is answer.startswith('bad')
    assert 'Error:' not in result.stderr


def test_progress_uses_shared_message_rendering():
    progress = Progress()
    progress.add_task('下载日志', total=1)
    assert msg.MessageColumn().render(progress.tasks[0]).plain == '下载日志'


def test_result_text_is_plain_stdout_and_context_is_plain_stderr(capsys):
    from wiserec_cli.output import print_text
    print_text('第 1 页 · 每页 10 条 · 共 0 条')
    print_text('暂无数据集记录')
    msg.detail('Pod：example · 文件：app.log')
    output = capsys.readouterr()
    assert output.out == '第 1 页 · 每页 10 条 · 共 0 条\n暂无数据集记录\n'
    assert output.err == 'Pod：example · 文件：app.log\n'


def test_broken_framework_error_formatter_falls_back_without_traceback(capsys):
    import click
    from wiserec_cli.command_errors import show_usage_error
    exc = click.UsageError("No such command 'invalid'.")
    with patch.object(exc, 'format_message', side_effect=TypeError('formatter failed')):
        show_usage_error(exc)
    output = capsys.readouterr()
    assert not output.out
    assert output.err == "[错误] 未知命令 'invalid'.\n请执行 ml --help 查看用法\n"


@pytest.mark.parametrize('exception,code', [
    (RuntimeError('运行时初始化失败'), 1),
    (ValueError('参数不正确'), 1),
])
def test_cli_entrypoint_contains_unexpected_exceptions(exception, code, capsys):
    from wiserec_cli.cli import run
    with patch('wiserec_cli.cli.app', side_effect=exception), pytest.raises(SystemExit) as exited:
        run()
    assert exited.value.code == code
    output = capsys.readouterr()
    assert not output.out
    assert output.err.startswith('[错误] 命令执行失败：')
    assert 'Traceback' not in output.err


@pytest.mark.parametrize('message,prefix', [
    ('警告：自动保活启动失败', '[警告]'),
    ('无法识别当前终端窗口，未启动自动保活', '[警告]'),
    ('尚未选择业务，选择后将启动自动保活', '尚未选择业务'),
])
def test_ping_status_severity(message, prefix, capsys):
    msg.ping_status(message)
    output = capsys.readouterr()
    assert not output.out
    assert output.err.startswith(prefix)


def test_ping_success_is_silent(capsys):
    msg.ping_status("")
    output = capsys.readouterr()
    assert output.out == output.err == ""
