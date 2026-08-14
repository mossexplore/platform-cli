"""wo 命令行入口。"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .commands.auth import auth_app, login, logout
from .commands.common import fail
from .commands.mep import mep_app
from .commands.profile import profile_app
from .commands.user import user_app
from .runtime import Runtime


app = typer.Typer(
    name="wo",
    no_args_is_help=True,
    help="CloudTest 平台命令行客户端",
)
app.command("login")(login)
app.command("logout")(logout)
app.add_typer(auth_app, name="auth")
app.add_typer(profile_app, name="profile")
app.add_typer(user_app, name="user")
app.add_typer(mep_app, name="mep")


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"wo {__version__}")
        raise typer.Exit()


@app.callback()
def initialize(
    context: typer.Context,
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        envvar="WO_CONFIG",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="config.json 路径，也可使用 WO_CONFIG 环境变量",
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
