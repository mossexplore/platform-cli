"""MEP 命令。"""

from __future__ import annotations

from typing import Optional

import typer

from ..output import print_result
from ..services.mep import MepService
from .common import fail, runtime_from_context


mep_app = typer.Typer(no_args_is_help=True, help="MEP 管理")
config_app = typer.Typer(no_args_is_help=True, help="MEP 配置")
mep_app.add_typer(config_app, name="config")


@config_app.command("get")
def get_config(
    context: typer.Context,
    key: str = typer.Argument(
        "mep_service_access_type",
        help="配置项 key",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="输出格式: table 或 json",
    ),
) -> None:
    """查询一个 MEP 配置项。"""
    try:
        runtime = runtime_from_context(context)
        result = runtime.authenticated_call(
            lambda client: MepService(client).query_config(key)
        )
        selected = output or runtime.config.current_profile().output_format
        print_result(result, selected)
    except Exception as exc:
        fail(exc)
