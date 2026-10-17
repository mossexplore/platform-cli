"""从真实进程入口验证用户输入错误不会进入 Typer/Python 堆栈展示。"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('arguments,message,help_command', [
    (['not-a-command'], '未知命令', 'ml'),
    (['train', 'not-a-command'], '未知命令', 'ml train'),
    (['dataset', 'files', 'not-a-command'], '未知命令', 'ml dataset files'),
    (['--bad-option'], '未知选项', 'ml'),
    (['train', 'list', '--bad-option'], '未知选项', 'ml train list'),
    (['env', 'use'], '缺少参数', 'ml env use'),
    (['env', 'use', 'dev', 'extra'], '多余参数', 'ml env use'),
    (['train', 'list', '--page', 'abc'], '不是有效整数', 'ml train list'),
    (['train', 'list', '--page', '0'], '不在允许范围内', 'ml train list'),
    (['train', 'list', '--page'], '需要参数值', 'ml'),
    (['jupyter', 'notebook', 'run', '/missing-notebook.ipynb'], '不存在', 'ml jupyter notebook run'),
])
def test_bad_input_in_real_process(tmp_path, arguments, message, help_command):
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'current': 'dev', 'access_control': {'enable': False},
        'profiles': [{'name': 'dev', 'api_endpoint': 'https://example.com'}]}))
    source = Path(__file__).resolve().parents[1] / 'src'
    environment = dict(os.environ, ML_HISTORY='0', NO_COLOR='1', PYTHONPATH=str(source))
    result = subprocess.run([sys.executable, '-m', 'wiserec_cli.cli', '--config', str(config),
                             *arguments], capture_output=True, text=True, env=environment, timeout=15)
    assert result.returncode == 2, result.stderr
    assert result.stdout == ''
    assert result.stderr.startswith('[错误] ')
    assert message in result.stderr
    assert f'请执行 {help_command} --help 查看用法' in result.stderr
    for unexpected in ['Traceback', 'During handling', 'File "', '╭', '[提示]', 'range.']:
        assert unexpected not in result.stderr


def test_internal_exception_in_real_entrypoint_is_concise():
    source = Path(__file__).resolve().parents[1] / 'src'
    script = '''from unittest.mock import patch
from wiserec_cli.cli import run
with patch('wiserec_cli.cli.app', side_effect=TypeError('参数解析失败')):
    run()
'''
    result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True,
                            env=dict(os.environ, PYTHONPATH=str(source), NO_COLOR='1'), timeout=15)
    assert result.returncode == 1
    assert result.stdout == ''
    assert result.stderr == '[错误] 命令执行失败：参数解析失败\n'
