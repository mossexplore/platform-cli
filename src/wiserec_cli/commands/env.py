"""运行环境管理命令。"""

from __future__ import annotations

import typer

from ..access import AccessDeniedError, access_enabled, check_access
from ..client_metadata import VersionPolicyError
from ..errors import MlError
from ..output import console, print_result
from .common import fail, runtime_from_context


env_app = typer.Typer(no_args_is_help=True, help="管理运行环境")


def _access_status(runtime, profile, settings):
    if not access_enabled(settings):
        return "校验已关闭"
    if not settings.get("url"):
        return "地址未配置"
    try:
        credentials = runtime.credentials.load(profile.name)
    except MlError:
        return "登录信息异常"
    if credentials is None:
        return "未登录"
    if credentials.is_expired():
        return "登录已过期"
    if not credentials.username:
        return "登录信息异常"
    try:
        if not runtime.business.has_profile(profile.name):
            return "未选择业务"
        selection = runtime.business.selection(profile.name, credentials.username)
        if selection is None:
            return "未选择业务"
        if runtime.business.selected_business_id(profile.name, credentials.username) != selection.business_id:
            return "业务信息异常"
    except MlError:
        return "业务信息异常"
    try:
        check_access(settings, profile, credentials, selection,
                     command="ml env list", full_command="ml env list")
    except AccessDeniedError as exc:
        return {
            "GRANT_EXPIRED": "授权已过期",
            "ENVIRONMENT_DISABLED": "环境未启用",
            "ENVIRONMENT_MISMATCH": "地址不匹配",
            "USER_DISABLED": "账号未启用",
            "NOT_GRANTED": "未开通",
        }.get(exc.reason, "未通过")
    except VersionPolicyError:
        return "CLI版本受限"
    except MlError:
        return "查询失败"
    return "已开通"


@env_app.command("list")
def list_environments(context: typer.Context) -> None:
    """列出全部环境。"""
    try:
        runtime = runtime_from_context(context)
        settings = runtime.config.access_control
        print_result(
            [
                {
                    "current": (
                        "*" if item.name == runtime.config.current_name else ""
                    ),
                    "name": item.name,
                    "api_endpoint": item.api_endpoint,
                    "access_status": _access_status(runtime, item, settings),
                    "output_format": item.output_format,
                    "verify_ssl": runtime.config.verify_ssl_for(item),
                }
                for item in runtime.config.profiles()
            ], wrap_columns=("api_endpoint",)
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
