"""命令公共辅助函数。"""

from __future__ import annotations

from typing import NoReturn

import typer

from .. import messages as msg
from ..access import command_name
from ..runtime import Runtime


def runtime_from_context(context: typer.Context) -> Runtime:
    runtime = context.find_root().obj
    if not isinstance(runtime, Runtime):
        fail("CLI 运行时尚未初始化")
    from ..history_recording import observe_runtime
    observe_runtime(runtime)
    runtime.invocation_command = command_name(context)
    runtime.full_command = context.meta.get("full_command", "")
    return runtime


def fail(error: object) -> NoReturn:
    msg.error(error)
    raise typer.Exit(code=1)
