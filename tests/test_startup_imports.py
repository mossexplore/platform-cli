"""在独立进程中验证启动及非 Notebook 功能不加载 Notebook 校验依赖。"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("arguments", [
    ["--version"], ["--help"], ["tree"], ["env", "show"],
    ["jupyter", "--help"], ["jupyter", "notebook", "run", "--help"],
    ["jupyter", "exec", "--help"],
])
def test_cli_without_notebook_dependencies(tmp_path, arguments):
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"current": "dev", "access_control": {"enable": False},
        "profiles": [{"name": "dev", "api_endpoint": "https://example.com"}]}))
    script = '''
import importlib.abc
import sys

class BlockNotebookDependencies(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"nbformat", "jsonschema"}:
            raise AssertionError("Unexpected startup dependency: " + fullname)

sys.meta_path.insert(0, BlockNotebookDependencies())
from wiserec_cli.cli import run
run()
'''
    result = subprocess.run([sys.executable, "-c", script, "--config", str(config),
                             *arguments], capture_output=True, text=True,
                            env=dict(os.environ, ML_HISTORY="0", NO_COLOR="1",
                                     PYTHONPATH=str(Path(__file__).resolve().parents[1] / "src")),
                            timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr


def test_protocol_and_notebook_imports_do_not_load_nbformat():
    script = '''
import sys
from wiserec_cli.jupyter.protocol import decode_message
from wiserec_cli.jupyter import notebook, execution
assert decode_message('{"content": {}}') == {"content": {}}
assert "nbformat" not in sys.modules
assert "jsonschema" not in sys.modules
'''
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                            env=dict(os.environ, PYTHONPATH=str(
                                Path(__file__).resolve().parents[1] / "src")), timeout=15)
    assert result.returncode == 0, result.stdout + result.stderr
