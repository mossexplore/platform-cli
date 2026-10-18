"""Production entry remains independent of optional execution hosts."""
import json
import os
import subprocess
import sys
from pathlib import Path
from typer.testing import CliRunner
from wiserec_cli.cli import app


def test_context_offline_and_redacted(tmp_path):
    config = tmp_path/'config.json'
    config.write_text(json.dumps({'current': 'test', 'profiles': [{'name': 'test',
        'api_endpoint': 'https://user:secret@example.com/dashboard?token=private#hidden'}]}))
    result = CliRunner().invoke(app, ['--config', str(config), 'context', '--json'])
    assert result.exit_code == 0, result.output
    value = json.loads(result.stdout)
    assert value['运行模式'] == '真实平台'
    assert value['平台地址'] == 'https://example.com/dashboard'
    assert not any(word in result.stdout for word in ('secret', 'private', 'hidden'))


def test_production_ignores_demo_environment(tmp_path):
    config = tmp_path/'config.json'
    config.write_text(json.dumps({'current': 'prod', 'profiles': [{'name': 'prod', 'api_endpoint': 'https://example.com'}]}))
    script = "from wiserec_cli.cli import app; import sys; assert not any(k.startswith('wiserec_cli_mock') for k in sys.modules); app()"
    result = subprocess.run([sys.executable, '-c', script, '--config', str(config), 'context', '--json'],
        capture_output=True, text=True, env=dict(os.environ, WISEREC_DEMO_WORKSPACE='/missing/demo'))
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['运行模式'] == '真实平台'


def test_package_gate_rejects_nested_mock(tmp_path):
    import runpy
    import zipfile
    import io
    checker = runpy.run_path(str(Path(__file__).resolve().parents[1]/'scripts/releasing/check-cli-package.py'))['check']
    wheel = io.BytesIO()
    with zipfile.ZipFile(wheel, 'w') as z:
        z.writestr('wiserec_cli_mock/__init__.py', '')
    archive = tmp_path/'release.zip'
    with zipfile.ZipFile(archive, 'w') as z:
        z.writestr('packages/innocent.whl', wheel.getvalue())
    import pytest
    with pytest.raises(ValueError, match='非正式内容'):
        checker(archive)
