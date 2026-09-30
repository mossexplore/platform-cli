"""登录、退出及认证状态命令。"""

from __future__ import annotations

from datetime import datetime
from math import ceil
import time

import typer

from ..output import console, print_result
from ..models import BEIJING_TIMEZONE
from ..errors import BusinessError
from .. import ping
from .common import fail, runtime_from_context


auth_app = typer.Typer(no_args_is_help=True, help="查看认证状态")
ping_app = typer.Typer(no_args_is_help=True, help="管理终端会话自动保活")
auth_app.add_typer(ping_app, name="ping")


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
        runtime = runtime_from_context(context)
        runtime.auth.login(show_secrets=show_secrets)
        if runtime.config.auto_ping:
            console.print(ping.auto_start(runtime, after_login=True))
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
        ping.stop(runtime, all_profiles=all_profiles)
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


@ping_app.command("start")
def ping_start(context: typer.Context) -> None:
    """为当前终端启动自动保活。"""
    try:
        console.print(ping.start(runtime_from_context(context)))
    except Exception as exc:
        fail(exc)


@ping_app.command("stop")
def ping_stop(context: typer.Context) -> None:
    """停止当前环境的自动保活。"""
    try:
        ping.stop(runtime_from_context(context))
        console.print("当前环境的自动保活已停止")
    except Exception as exc:
        fail(exc)


@ping_app.command("status")
def ping_status(context: typer.Context) -> None:
    """只读查看自动保活状态。"""
    try:
        print_result(ping.status(runtime_from_context(context)))
    except Exception as exc:
        fail(exc)


@auth_app.command("status")
def status(context: typer.Context) -> None:
    """显示当前环境的认证有效期，不显示敏感值。"""
    try:
        runtime = runtime_from_context(context)
        credentials = runtime.auth.status()
        try:
            business_id = runtime.business.selected_business_id(
                credentials.profile, credentials.username
            )
        except BusinessError:
            business_id = "-"
        now = time.time()
        print_result(
            {
                "profile": credentials.profile,
                "username": credentials.username,
                "cn_name": credentials.cn_name,
                "department": credentials.department,
                "businessId": business_id,
                "status": "expired" if credentials.is_expired(now=now) else "valid",
                "remaining_minutes": max(0, ceil((credentials.expires_at - now) / 60)),
                "acquired_at": datetime.fromtimestamp(
                    credentials.acquired_at, BEIJING_TIMEZONE
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "expires_at": datetime.fromtimestamp(
                    credentials.expires_at, BEIJING_TIMEZONE
                ).strftime("%Y-%m-%d %H:%M:%S"),
                "timezone": "Asia/Shanghai",
            }
        )
    except Exception as exc:
        fail(exc)
