"""从已注册命令生成完整的 CLI 命令树。"""

from __future__ import annotations

import click
import typer
from rich.console import Console
from rich.text import Text
from rich.tree import Tree


def _is_group(command: click.Command) -> bool:
    return isinstance(command, (click.Group, typer.core.TyperGroup))


def _summary(command: click.Command) -> str:
    return command.get_short_help_str(limit=1000).split("；", 1)[0].strip()


def _append_commands(parent: Tree, group: click.Group) -> None:
    for name, command in group.commands.items():
        if command.hidden:
            continue
        label = Text()
        label.append(name, style="bold cyan" if _is_group(command) else "cyan")
        summary = _summary(command)
        if summary:
            label.append(f"  {summary}", style="dim")
        branch = parent.add(label)
        if _is_group(command):
            _append_commands(branch, command)


def show_tree(context: typer.Context) -> None:
    """显示当前安装版本的完整命令树。"""
    root = context.find_root().command
    if not _is_group(root):
        raise typer.Exit(code=1)
    tree = Tree(Text("ml  WiseRec 命令行工具", style="bold"))
    _append_commands(tree, root)
    Console().print(tree)
