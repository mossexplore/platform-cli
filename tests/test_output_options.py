"""所有支持 --output 的命令都必须支持相同含义的 -o。"""

import click
from typer.main import get_command

from wiserec_cli.cli import app


def test_every_output_option_has_short_alias():
    commands = [((), get_command(app))]
    output_commands = []
    while commands:
        path, command = commands.pop()
        for param in command.params:
            if isinstance(param, click.Option) and "--output" in param.opts:
                output_commands.append(" ".join(path))
                assert "-o" in param.opts, f"{' '.join(path)} 缺少 -o 别名"
        if isinstance(command, click.Group):
            commands.extend(((*path, name), child) for name, child in command.commands.items())

    assert output_commands
