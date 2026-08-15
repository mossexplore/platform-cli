"""ml 命令行入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .commands.auth import auth_app, login, logout
from .commands.common import fail
from .commands.env import env_app
from .commands.mep import mep_app
from .commands.user import user_app
from .runtime import Runtime


app = typer.Typer(
    name="ml",
    no_args_is_help=True,
    help="WiseMLOps平台命令行客户端",
)
app.command("login")(login)
app.command("logout")(logout)
app.add_typer(auth_app, name="auth")
app.add_typer(env_app, name="env")
app.add_typer(user_app, name="user")
app.add_typer(mep_app, name="mep")


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ml {__version__}")
        raise typer.Exit()


@app.callback()
def initialize(
    context: typer.Context,
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        envvar="ML_CONFIG",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="config.json 路径，也可使用 ML_CONFIG 环境变量",
    ),
    version: bool = typer.Option(
        False,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="显示版本",
    ),
) -> None:
    """初始化 CLI 运行时。"""
    del version
    try:
        context.obj = Runtime(config_path=config)
    except Exception as exc:
        fail(exc)


def run() -> None:
    app()


if __name__ == "__main__":
    run()
