"""用户命令。"""

from __future__ import annotations

from typing import Optional

import typer

from ..output import print_result
from ..services.user import UserService
from .common import fail, runtime_from_context


user_app = typer.Typer(no_args_is_help=True, help="用户信息")


@user_app.command("info")
def user_info(
    context: typer.Context,
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="输出格式: table 或 json",
    ),
) -> None:
    """查询当前登录用户信息。"""
    try:
        runtime = runtime_from_context(context)
        result = runtime.authenticated_call(lambda client: UserService(client).info())
        selected = output or runtime.config.current_profile().output_format
        print_result(result, selected)
    except Exception as exc:
        fail(exc)
