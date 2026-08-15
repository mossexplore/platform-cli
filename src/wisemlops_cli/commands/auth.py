"""登录、退出及认证状态命令。"""

from __future__ import annotations

from datetime import datetime

import typer

from ..output import console, print_result
from .common import fail, runtime_from_context


auth_app = typer.Typer(no_args_is_help=True, help="查看认证状态")


def login(
    context: typer.Context,
    show_secrets: bool = typer.Option(
        False,
        "--show-secrets",
        help="登录成功后显示完整 Cookie 和 CSRF Token",
    ),
) -> None:
    """打开 Edge 登录并刷新当前环境的本地认证信息。"""
    try:
        runtime_from_context(context).auth.login(show_secrets=show_secrets)
    except Exception as exc:
        fail(exc)


def logout(
    context: typer.Context,
    all_profiles: bool = typer.Option(
        False,
        "--all",
        help="清除所有环境的本地认证信息",
    ),
    forget_browser: bool = typer.Option(
        False,
        "--forget-browser",
        help="同时清除专用 Edge Profile，之后登录可能需要重新输入验证码",
    ),
) -> None:
    """清除当前环境的本地认证信息。"""
    try:
        runtime = runtime_from_context(context)
        runtime.auth.logout(
            all_profiles=all_profiles,
            forget_browser=forget_browser,
        )
        target = "所有环境" if all_profiles else runtime.config.current_name
        console.print(f"已清除 {target} 的本地认证信息")
        if forget_browser:
            console.print(f"已清除 {target} 的专用 Edge Profile")
    except Exception as exc:
        fail(exc)


@auth_app.command("status")
def status(context: typer.Context) -> None:
    """显示当前环境的认证有效期，不显示敏感值。"""
    try:
        credentials = runtime_from_context(context).auth.status()
        print_result(
            {
                "profile": credentials.profile,
                "username": credentials.username,
                "status": "expired" if credentials.is_expired() else "valid",
                "remaining_seconds": credentials.remaining_seconds(),
                "acquired_at": datetime.fromtimestamp(
                    credentials.acquired_at
                ).isoformat(timespec="seconds"),
                "expires_at": datetime.fromtimestamp(
                    credentials.expires_at
                ).isoformat(timespec="seconds"),
            }
        )
    except Exception as exc:
        fail(exc)
