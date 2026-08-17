"""离线业务命令。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

import typer

from ..output import console, print_result
from ..services.experiment import ExperimentService
from .common import fail, runtime_from_context


offline_app = typer.Typer(no_args_is_help=True, help="离线业务管理")
experiment_app = typer.Typer(no_args_is_help=True, help="离线实验管理")
offline_app.add_typer(experiment_app, name="experiment")

TABLE_COLUMNS = (
    ("projectId", "projectId"),
    ("实验名称", "projectName"),
    ("描述", "description"),
    ("创建者", "createUser"),
    ("修改者", "updateUser"),
    ("创建时间", "createTime"),
    ("更新时间", "updateTime"),
    ("运行配置模板", "configName"),
)


def _table_items(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {title: item.get(field) or "-" for title, field in TABLE_COLUMNS}
        for item in result["items"]
    ]


def _clone_result(
    response: Dict[str, Any],
    source_project_id: str,
    project_name: str,
    request_uuid: str,
) -> Dict[str, Any]:
    result = response["result"]
    data = result.get("data")
    new_project_id = data.get("projectId", "") if isinstance(data, dict) else ""
    return {
        "sourceProjectId": source_project_id,
        "projectId": new_project_id or "-",
        "projectName": project_name,
        "uuid": request_uuid,
        "message": result.get("des") or "ok",
    }


@experiment_app.command("list")
def list_experiments(
    context: typer.Context,
    page: int = typer.Option(
        1,
        "--page",
        min=1,
        help="开始页码",
    ),
    page_size: int = typer.Option(
        10,
        "--page-size",
        min=1,
        help="每页记录数",
    ),
    project_name: Optional[str] = typer.Option(
        None,
        "--name",
        "--project-name",
        help="按实验名称模糊查询",
    ),
    description: Optional[str] = typer.Option(
        None,
        "--description",
        help="按描述模糊查询",
    ),
    create_user: Optional[str] = typer.Option(
        None,
        "--create-user",
        help="按创建者模糊查询",
    ),
    update_user: Optional[str] = typer.Option(
        None,
        "--update-user",
        help="按修改者模糊查询",
    ),
    team_id: Optional[str] = typer.Option(
        None,
        "--team-id",
        help="按团队 ID 模糊查询",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="输出格式: table 或 json",
    ),
) -> None:
    """分页查询离线实验。"""
    try:
        runtime = runtime_from_context(context)
        result = runtime.authenticated_call(
            lambda client: ExperimentService(client).list_projects(
                page_index=page,
                page_size=page_size,
                project_name=project_name,
                description=description,
                create_user=create_user,
                update_user=update_user,
                team_id=team_id,
            )
        )
        selected = output or runtime.config.current_profile().output_format
        rendered = result if selected.lower() == "json" else _table_items(result)
        print_result(rendered, selected)
    except Exception as exc:
        fail(exc)


@experiment_app.command("clone")
def clone_experiment(
    context: typer.Context,
    project_id: str = typer.Argument(..., help="源实验 projectId"),
    project_name: str = typer.Option(
        ...,
        "--name",
        help="克隆后的实验名称",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="跳过克隆确认",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="仅展示创建请求，不执行克隆",
    ),
    output: Optional[str] = typer.Option(
        None,
        "--output",
        "-o",
        help="输出格式: table 或 json",
    ),
) -> None:
    """查询源实验详情并同步克隆，仅修改实验名称。"""
    try:
        runtime = runtime_from_context(context)
        request_uuid = str(uuid4())
        confirmed = yes

        def clone(client):
            nonlocal confirmed
            service = ExperimentService(client)
            detail = service.get_project(project_id)
            request_body = service.build_clone_request(
                detail,
                project_name,
                request_uuid,
            )
            if dry_run:
                return {"dryRun": True, "request": request_body}

            if not confirmed:
                console.print(f"源实验名称：{detail.get('projectName') or '-'}")
                console.print(f"新实验名称：{request_body['data']['projectName']}")
                console.print(f"运行配置模板：{detail.get('configName') or '-'}")
                console.print(f"businessId：{detail.get('businessId') or '-'}")
                console.print(f"团队 ID：{detail.get('teamId') or '-'}")
                if not typer.confirm("确认克隆？", default=False):
                    return None
                confirmed = True

            response = service.create_project(request_body)
            return _clone_result(
                response,
                project_id,
                request_body["data"]["projectName"],
                request_uuid,
            )

        result = runtime.authenticated_call(clone)
        if result is None:
            console.print("已取消克隆")
            return
        selected = output or runtime.config.current_profile().output_format
        print_result(result, selected)
    except Exception as exc:
        fail(exc)
