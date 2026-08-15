"""运行环境管理命令。"""

from __future__ import annotations

import typer

from ..output import console, print_result
from .common import fail, runtime_from_context


env_app = typer.Typer(no_args_is_help=True, help="管理运行环境")


@env_app.command("list")
def list_environments(context: typer.Context) -> None:
    """列出全部环境。"""
    try:
        runtime = runtime_from_context(context)
        print_result(
            [
                {
                    "current": (
                        "*" if item.name == runtime.config.current_name else ""
                    ),
                    "name": item.name,
                    "api_endpoint": item.api_endpoint,
                    "output_format": item.output_format,
                    "verify_ssl": runtime.config.verify_ssl_for(item),
                }
                for item in runtime.config.profiles()
            ]
        )
    except Exception as exc:
        fail(exc)


@env_app.command("show")
def show_environment(context: typer.Context) -> None:
    """显示当前环境。"""
    try:
        runtime = runtime_from_context(context)
        profile = runtime.config.current_profile()
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
        profile = runtime_from_context(context).config.use_profile(name)
        console.print(f"当前环境已切换为: {profile.name}")
    except Exception as exc:
        fail(exc)
