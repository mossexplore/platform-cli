"""完整命令树的离线入口和动态注册行为。"""

from io import StringIO
from unittest.mock import patch

import click
from rich.console import Console
from rich.tree import Tree
from typer.testing import CliRunner

from wiserec_cli.cli import app
from wiserec_cli.commands.tree import _append_commands


def test_tree_works_without_runtime_or_login():
    with patch("wiserec_cli.cli.Runtime", side_effect=AssertionError("tree must be offline")):
        result = CliRunner().invoke(app, ["tree"])

    assert result.exit_code == 0, result.output
    assert "ml  WiseRec 命令行工具" in result.output
    assert "├── train" in result.output
    assert "── download" in result.output
    assert "── service" in result.output
    assert "── dataset" in result.output
    assert "── search" in result.output
    assert "── tree" in result.output


def test_tree_uses_newly_registered_commands_and_descriptions():
    root = click.Group("ml")
    nested = click.Group("sample", help="示例分组（补充说明）：")
    nested.add_command(click.Command("new-command", help="新注册的命令，中间标点保留。！？ "))
    root.add_command(nested)

    tree = Tree("ml")
    _append_commands(tree, root)
    stream = StringIO()
    Console(file=stream, color_system=None, width=100).print(tree)

    assert "sample  示例分组，补充说明\n" in stream.getvalue()
    assert "new-command  新注册的命令，中间标点保留\n" in stream.getvalue()
