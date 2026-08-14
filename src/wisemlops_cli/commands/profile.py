"""profile 管理命令。"""

from __future__ import annotations

import typer

from ..output import console, print_result
from .common import fail, runtime_from_context


profile_app = typer.Typer(no_args_is_help=True, help="管理环境 profile")


@profile_app.command("list")
def list_profiles(context: typer.Context) -> None:
    """列出全部 profile。"""
    try:
        runtime = runtime_from_context(context)
        print_result(
            [
                {
                    "current": "*" if item.name == runtime.config.current_name else "",
                    "name": item.name,
                    "api_endpoint": item.api_endpoint,
                    "output_format": item.output_format,
                }
                for item in runtime.config.profiles()
            ]
        )
    except Exception as exc:
        fail(exc)


@profile_app.command("show")
def show_profile(context: typer.Context) -> None:
    """显示当前 profile。"""
    try:
        profile = runtime_from_context(context).config.current_profile()
        print_result(
            {
                "name": profile.name,
                "api_endpoint": profile.api_endpoint,
                "base_url": profile.base_url,
                "output_format": profile.output_format,
            }
        )
    except Exception as exc:
        fail(exc)


@profile_app.command("use")
def use_profile(context: typer.Context, name: str = typer.Argument(...)) -> None:
    """切换当前 profile。"""
    try:
        profile = runtime_from_context(context).config.use_profile(name)
        console.print(f"当前 profile 已切换为: {profile.name}")
    except Exception as exc:
        fail(exc)
