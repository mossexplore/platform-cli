"""部门、租户（服务）和团队上下文命令。"""

from __future__ import annotations

from dataclasses import replace
from typing import List, Optional, Sequence, Tuple, TypeVar

import typer

from ..business import BusinessSelection, Team
from ..errors import BusinessError
from ..output import console, print_result
from .common import fail, runtime_from_context


business_app = typer.Typer(no_args_is_help=True, help="管理部门、租户和团队")
T = TypeVar("T")


def _credentials_and_catalog(context: typer.Context):
    runtime = runtime_from_context(context)
    credentials = runtime.auth.status()
    catalog = runtime.business.catalog(
        runtime.config.current_name, credentials.username
    )
    return runtime, credentials, catalog


def _print_selection(selection: BusinessSelection) -> None:
    print_result(
        {
            "type": selection.type,
            "department": selection.department_name,
            "department_id": selection.department_id,
            "tenant": selection.tenant_name,
            "tenant_id": selection.tenant_id,
            "team": selection.team_name or "-",
            "team_id": selection.team_id or "-",
            "business_id": selection.effective_business_id,
        }
    )


def _choose(title: str, values: Sequence[Tuple[str, T]]) -> T:
    if not values:
        raise BusinessError(f"没有可选择的{title}")
    console.print(f"请选择{title}：")
    for index, (label, _) in enumerate(values, start=1):
        console.print(f"  {index}. {label}", markup=False)
    selected = typer.prompt("请输入序号", type=int)
    if selected < 1 or selected > len(values):
        raise BusinessError(f"{title}序号无效: {selected}")
    return values[selected - 1][1]


@business_app.command("list")
def list_businesses(context: typer.Context) -> None:
    """显示当前环境可见的部门、租户和团队目录。"""
    try:
        runtime, credentials, catalog = _credentials_and_catalog(context)
        selected = runtime.business.selection(
            runtime.config.current_name, credentials.username
        )
        for department in catalog:
            console.print(
                f"部门: {department.name} [{department.id}]", markup=False
            )
            for tenant in department.tenants:
                tenant_marker = (
                    " *当前"
                    if selected
                    and selected.type == "tenant"
                    and selected.department_id == department.id
                    and selected.tenant_id == tenant.id
                    else ""
                )
                console.print(
                    f"  租户: {tenant.name} [{tenant.id}]{tenant_marker}",
                    markup=False,
                )
                for team in tenant.teams:
                    team_marker = (
                        " *当前"
                        if selected
                        and selected.type == "team"
                        and selected.department_id == department.id
                        and selected.tenant_id == tenant.id
                        and selected.team_id == team.id
                        else ""
                    )
                    availability = (
                        "可选" if team.selectable else f"禁选: {team.status}"
                    )
                    console.print(
                        f"    团队: {team.name} [{team.id}] "
                        f"({availability}){team_marker}",
                        markup=False,
                    )
    except Exception as exc:
        fail(exc)


@business_app.command("show")
def show_business(context: typer.Context) -> None:
    """显示当前租户或团队上下文。"""
    try:
        runtime = runtime_from_context(context)
        credentials = runtime.auth.status()
        selection = runtime.business.require_selection(
            runtime.config.current_name, credentials.username
        )
        _print_selection(selection)
    except Exception as exc:
        fail(exc)


@business_app.command("use")
def use_business(
    context: typer.Context,
    tenant: Optional[str] = typer.Option(
        None, "--tenant", help="租户 ID（ai-businessList[].value）"
    ),
    team: Optional[str] = typer.Option(
        None, "--team", help="团队 ID 或 key"
    ),
    department: Optional[str] = typer.Option(
        None, "--department", help="部门 ID，用于消除重复租户 ID 歧义"
    ),
) -> None:
    """交互式或通过 ID 选择租户/团队。"""
    try:
        runtime, credentials, catalog = _credentials_and_catalog(context)
        selected_tenant = tenant
        selected_team = team or ""
        selected_department = department or ""

        if tenant is None:
            if team is not None or department is not None:
                raise BusinessError(
                    "不能仅选择部门或团队，请同时通过 --tenant 指定租户"
                )
            department_value = _choose(
                "部门",
                [(f"{item.name} [{item.id}]", item) for item in catalog],
            )
            tenant_value = _choose(
                "租户",
                [
                    (f"{item.name} [{item.id}]", item)
                    for item in department_value.tenants
                ],
            )
            scopes: List[Tuple[str, Optional[Team]]] = [
                (f"{tenant_value.name}（租户级）", None)
            ]
            scopes.extend(
                (
                    f"{item.name} [{item.id}] "
                    f"({'可选' if item.selectable else '禁选: ' + item.status})",
                    item,
                )
                for item in tenant_value.teams
            )
            team_value = _choose("操作范围", scopes)
            if team_value is not None and not team_value.selectable:
                raise BusinessError(
                    f"团队 {team_value.name!r} 当前状态为 "
                    f"{team_value.status!r}，不可选择"
                )
            selected_department = department_value.id
            selected_tenant = tenant_value.id
            selected_team = team_value.id if team_value else ""

        selection = runtime.business.select(
            profile=runtime.config.current_name,
            username=credentials.username,
            department_id=selected_department,
            tenant_id=str(selected_tenant),
            team_id=selected_team,
        )
        runtime.credentials.save(
            replace(
                credentials,
                business_id=selection.effective_business_id,
            )
        )
        console.print("当前业务上下文已切换：")
        _print_selection(selection)
    except Exception as exc:
        fail(exc)


@business_app.command("refresh")
def refresh_business(context: typer.Context) -> None:
    """打开 Edge 刷新当前环境的业务目录。"""
    try:
        runtime = runtime_from_context(context)
        previous_updated_at = runtime.business.updated_at(
            runtime.config.current_name
        )
        credentials = runtime.auth.login()
        runtime.business.catalog(
            runtime.config.current_name, credentials.username
        )
        if runtime.business.updated_at(
            runtime.config.current_name
        ) <= previous_updated_at:
            raise BusinessError(
                "未能从 Edge 刷新 ai-businessList，请检查登录页面缓存"
            )
        console.print("业务目录已刷新")
    except Exception as exc:
        fail(exc)
