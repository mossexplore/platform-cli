"""命令公共辅助函数。"""

from __future__ import annotations

from typing import NoReturn

import typer

from ..errors import WoError
from ..output import error_console
from ..runtime import Runtime


def runtime_from_context(context: typer.Context) -> Runtime:
    runtime = context.find_root().obj
    if not isinstance(runtime, Runtime):
        fail("CLI 运行时尚未初始化")
    return runtime


def fail(error: object) -> NoReturn:
    message = str(error)
    if isinstance(error, WoError):
        error_console.print(f"[red]错误:[/red] {message}")
    else:
        error_console.print(f"[red]错误:[/red] {message}")
    raise typer.Exit(code=1)
