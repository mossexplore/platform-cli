"""运行环境管理命令。"""

from __future__ import annotations

import typer
from .. import ping

from ..env_access import environment_statuses
from ..access_guidance import show_access_guidance
from ..output import console, print_result
from .common import fail, runtime_from_context


env_app = typer.Typer(no_args_is_help=True, help="管理运行环境")


@env_app.command("list")
def list_environments(context: typer.Context) -> None:
    """列出全部环境。"""
    try:
        runtime = runtime_from_context(context)
        statuses = environment_statuses(runtime)
        print_result(
            [
                {
                    "当前在用环境": (
                        "*" if item.name == runtime.config.current_name else ""
                    ),
                    "环境标识": item.alias or item.name,
                    "管理台地址": item.api_endpoint,
                    "状态": statuses[item.name],
                }
                for item in runtime.config.profiles()
            ], wrap_columns=("管理台地址",)
        )
    except Exception as exc:
        fail(exc)


@env_app.command("show")
def show_environment(context: typer.Context) -> None:
    """显示当前环境。"""
    try:
        runtime = runtime_from_context(context)
        profile = runtime.config.current_profile()
        show_access_guidance(runtime)
        print_result(
            {
                "name": profile.name,
                "api_endpoint": profile.api_endpoint,
                "base_url": profile.base_url,
                "output_format": profile.output_format,
                "verify_ssl": runtime.config.verify_ssl,
            }
        )
    except Exception as exc:
        fail(exc)


@env_app.command("use")
def use_environment(context: typer.Context, name: str = typer.Argument(...)) -> None:
    """切换当前环境。"""
    try:
        runtime = runtime_from_context(context)
        previous = runtime.config.current_name
        profile = runtime.config.use_profile(name)
        if previous != name:
            ping.detach(runtime, previous)
        console.print(f"当前环境已切换为: {profile.name}")
        has_access = show_access_guidance(runtime)
        if has_access and runtime.config.auto_ping:
            console.print(ping.auto_start(runtime))
    except Exception as exc:
        fail(exc)
