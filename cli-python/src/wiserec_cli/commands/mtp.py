"""MTP 训练看板命令。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import typer

from ..output import console, print_result
from ..services.swanboard import SwanBoardService
from .common import fail, runtime_from_context


mtp_app = typer.Typer(no_args_is_help=True, help="MTP 管理")
swanboard_app = typer.Typer(no_args_is_help=True, help="训练看板管理")
project_app = typer.Typer(no_args_is_help=True, help="训练看板项目管理")
namespace_app = typer.Typer(no_args_is_help=True, help="训练看板项目空间管理")
project_experiment_app = typer.Typer(no_args_is_help=True, help="训练看板项目实验管理")
experiment_app = typer.Typer(no_args_is_help=True, help="训练看板实验数据查询")
feature_app = typer.Typer(no_args_is_help=True, help="训练看板实验特性")
environment_app = typer.Typer(no_args_is_help=True, help="训练看板实验环境")
config_app = typer.Typer(no_args_is_help=True, help="训练看板实验配置")

mtp_app.add_typer(swanboard_app, name="swanboard")
swanboard_app.add_typer(project_app, name="project")
swanboard_app.add_typer(experiment_app, name="experiment")
project_app.add_typer(namespace_app, name="namespace")
project_app.add_typer(project_experiment_app, name="experiment")
experiment_app.add_typer(feature_app, name="feature")
experiment_app.add_typer(environment_app, name="environment")
experiment_app.add_typer(config_app, name="config")


def _selected_output(runtime: Any, output: Optional[str]) -> str:
    return output or runtime.config.current_profile().output_format


def _items(result: Dict[str, Any], fields: List[tuple[str, str]]) -> List[Dict[str, Any]]:
    return [
        {title: item.get(field) or "-" for title, field in fields}
        for item in result["items"]
    ]


def _environment_item(value: Dict[str, Any]) -> Dict[str, str]:
    cpu = value.get("cpu")
    requirements = value.get("requirements")
    if isinstance(requirements, list):
        rendered_requirements = "\n".join(str(item) for item in requirements) or "-"
    else:
        rendered_requirements = str(requirements) if requirements else "-"
    return {
        "Python版本": str(value.get("python") or "-"),
        "系统硬件CPU": str(cpu.get("brand") or "-") if isinstance(cpu, dict) else "-",
        "系统硬件Memory": str(value.get("memory") or "-"),
        "Python库名称": rendered_requirements,
    }


def _metric_items(values: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    def number(value: Any) -> str:
        return f"{value:.4f}" if isinstance(value, (int, float)) and not isinstance(value, bool) else "-"

    return [
        {
            "指标名称": str(item.get("tagName") or "-"),
            "最大值": number(item.get("max")),
            "最小值": number(item.get("min")),
            "平均值": number(item.get("avg")),
        }
        for item in values
    ]


def _config_items(value: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "配置项": key,
            "值": item.get("value", "-") if isinstance(item, dict) else item,
        }
        for key, item in value.items()
    ]


@project_app.command("list")
def list_projects(
    context: typer.Context,
    page: int = typer.Option(1, "--page", min=1, help="开始页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, help="每页记录数"),
    team_id: str = typer.Option("", "--team-id", help="团队 ID 模糊查询"),
    creator: str = typer.Option("", "--creator", help="创建者模糊查询"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """分页查询训练看板项目。"""
    try:
        runtime = runtime_from_context(context)
        result = runtime.authenticated_call(
            lambda client: SwanBoardService(client).list_projects(page, page_size, team_id, creator)
        )
        selected = _selected_output(runtime, output)
        rendered = result if selected.lower() == "json" else _items(
            result,
            [
                ("项目id", "projectId"),
                ("项目名称", "name"),
                ("项目描述", "description"),
                ("创建者", "creator"),
                ("创建时间", "createTime"),
            ],
        )
        print_result(rendered, selected)
    except Exception as exc:
        fail(exc)


@namespace_app.command("list")
def list_namespaces(
    context: typer.Context,
    project_id: str = typer.Argument(..., help="训练看板 projectId"),
    team_id: str = typer.Option("", "--team-id", help="团队 ID 模糊查询"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """查询训练看板项目下的全部项目空间。"""
    try:
        runtime = runtime_from_context(context)
        result = runtime.authenticated_call(
            lambda client: SwanBoardService(client).list_namespaces(project_id, team_id)
        )
        selected = _selected_output(runtime, output)
        rendered = result if selected.lower() == "json" else _items(
            result,
            [
                ("项目空间id", "namespaceId"),
                ("实验id", "projectId"),
                ("实验名称", "namespaceName"),
                ("描述", "description"),
                ("创建时间", "createTime"),
            ],
        )
        print_result(rendered, selected)
    except Exception as exc:
        fail(exc)


@project_experiment_app.command("list")
def list_experiments(
    context: typer.Context,
    project_id: str = typer.Argument(..., help="训练看板 projectId"),
    namespace_id: str = typer.Argument(..., help="项目空间 namespaceId"),
    team_id: str = typer.Option("", "--team-id", help="团队 ID 模糊查询"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """查询项目空间下的全部实验。"""
    try:
        runtime = runtime_from_context(context)
        result = runtime.authenticated_call(
            lambda client: SwanBoardService(client).list_experiments(project_id, namespace_id, team_id)
        )
        selected = _selected_output(runtime, output)
        rendered = result if selected.lower() == "json" else _items(
            result,
            [("项目实验id", "experimentId"), ("实验名称", "name"), ("创建时间", "createTime")],
        )
        print_result(rendered, selected)
    except Exception as exc:
        fail(exc)


@feature_app.command("list")
def list_features(
    context: typer.Context,
    experiment_id: str = typer.Argument(..., help="实验 experimentId"),
    page: int = typer.Option(1, "--page", min=1, help="开始页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, help="每页记录数"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """查询实验特性。"""
    try:
        runtime = runtime_from_context(context)
        result = runtime.authenticated_call(
            lambda client: SwanBoardService(client).list_features(experiment_id, page, page_size)
        )
        selected = _selected_output(runtime, output)
        rendered = result if selected.lower() == "json" else _items(
            result, [("特征名", "featureName"), ("扩展参数", "featuresConfig")]
        )
        print_result(rendered, selected)
    except Exception as exc:
        fail(exc)


@environment_app.command("get")
def get_environment(
    context: typer.Context,
    experiment_id: str = typer.Argument(..., help="实验 experimentId"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """查询实验环境。"""
    try:
        runtime = runtime_from_context(context)
        result = runtime.authenticated_call(
            lambda client: SwanBoardService(client).get_environment(experiment_id)
        )
        selected = _selected_output(runtime, output)
        print_result(result if selected.lower() == "json" else [_environment_item(result)], selected)
    except Exception as exc:
        fail(exc)


@experiment_app.command("metrics")
def get_metrics(
    context: typer.Context,
    experiment_id: str = typer.Argument(..., help="实验 experimentId"),
    tags: List[str] = typer.Option(["loss", "accuracy"], "--tag", help="指标名称，可重复传入"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """查询实验指标统计，默认查询 loss 和 accuracy。"""
    try:
        runtime = runtime_from_context(context)
        result = runtime.authenticated_call(
            lambda client: [SwanBoardService(client).get_metric_stats(experiment_id, tag) for tag in tags]
        )
        selected = _selected_output(runtime, output)
        print_result(result if selected.lower() == "json" else _metric_items(result), selected)
    except Exception as exc:
        fail(exc)


@config_app.command("list")
def get_config(
    context: typer.Context,
    experiment_id: str = typer.Argument(..., help="实验 experimentId"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """查询实验配置。"""
    try:
        runtime = runtime_from_context(context)
        result = runtime.authenticated_call(
            lambda client: SwanBoardService(client).get_config(experiment_id)
        )
        selected = _selected_output(runtime, output)
        print_result(result if selected.lower() == "json" else _config_items(result), selected)
    except Exception as exc:
        fail(exc)


@experiment_app.command("inspect")
def inspect_experiment(
    context: typer.Context,
    experiment_id: str = typer.Argument(..., help="实验 experimentId"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
) -> None:
    """一次性查询实验的特性、环境、指标和配置。"""
    try:
        runtime = runtime_from_context(context)
        result = runtime.authenticated_call(
            lambda client: SwanBoardService(client).inspect_experiment(experiment_id)
        )
        selected = _selected_output(runtime, output)
        if selected.lower() == "json":
            print_result(result, selected)
            return
        for title, value in (
            ("实验特性", _items(result["features"], [("特征名", "featureName"), ("扩展参数", "featuresConfig")])),
            ("实验环境", [_environment_item(result["environment"])]),
            ("指标信息", _metric_items(result["metrics"])),
            ("实验配置", _config_items(result["config"])),
        ):
            console.print(f"[bold cyan]{title}[/bold cyan]")
            print_result(value, selected)
    except Exception as exc:
        fail(exc)
