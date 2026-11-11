"""Command-index generation fails closed when examples or CLI signatures drift."""
from pathlib import Path
import runpy

import click
import pytest
import typer

from wiserec_cli.cli import app

SCRIPT = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/sync_skill_index.py"))
render = SCRIPT["render"]


def command_tree():
    return click.Group(commands={
        "job": click.Group(commands={
            "list": click.Command("list", params=[click.Option(["--output", "-o"])]),
            "delete": click.Command("delete", params=[click.Option(["--yes"], is_flag=True)]),
        })
    })


TEMPLATE = """| 命令 | 用途 | 确认 | 副作用 |
| --- | --- | --- | --- |
| `ml job list -o json` | 查询 | {{confirm}} | |
| `ml job delete` | 删除 | {{confirm}} | 删除任务 |
"""


def test_generated_index_matches_current_cli():
    expected = render(typer.main.get_command(app), SCRIPT["TEMPLATE"].read_text(encoding="utf-8"))
    assert SCRIPT["OUTPUT"].read_text(encoding="utf-8") == expected


def test_confirmation_column_follows_cli_option():
    tree = command_tree()
    assert "| 删除 | 是 |" in render(tree, TEMPLATE)
    tree.commands["job"].commands["delete"].params.clear()
    assert "| 删除 | |" in render(tree, TEMPLATE)


def test_removed_example_option_is_rejected():
    tree = command_tree()
    tree.commands["job"].commands["list"].params.clear()
    with pytest.raises(ValueError, match="Unknown options"):
        render(tree, TEMPLATE)


def test_new_unindexed_command_is_rejected():
    tree = command_tree()
    tree.commands["job"].add_command(click.Command("start"))
    with pytest.raises(ValueError, match="Missing commands"):
        render(tree, TEMPLATE)


def test_shorthand_examples_are_checked():
    tree = command_tree()
    tree.commands["job"].commands["delete"].params.clear()
    template = "| `ml job list` / `delete` | 查询与删除 | {{confirm}} | 删除任务 |\n"
    assert "{{confirm}}" not in render(tree, template)
    with pytest.raises(ValueError, match="Unknown or incomplete command"):
        render(tree, template.replace("`delete`", "`missing`"))


def test_grouped_confirmation_mismatch_is_rejected():
    with pytest.raises(ValueError, match="different confirmation"):
        render(command_tree(), "| `ml job list` / `delete` | 混合 | {{confirm}} | |\n")
