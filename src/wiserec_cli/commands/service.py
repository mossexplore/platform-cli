"""服务列表、主机视图和部署视图命令。"""

from __future__ import annotations

import sys
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

import typer
from rich.table import Table
from rich.text import Text

from ..errors import BusinessError
from ..output import console, error_console, print_result
from ..services.service import ServiceCatalog
from .common import fail, runtime_from_context


service_app = typer.Typer(no_args_is_help=True, help="服务列表与部署视图查询")
host_app = typer.Typer(no_args_is_help=True, help="服务主机视图查询")
deployment_app = typer.Typer(no_args_is_help=True, help="服务部署视图查询")
logs_app = typer.Typer(no_args_is_help=True, help="主机日志文件列表与检索")
service_app.add_typer(host_app, name="host")
service_app.add_typer(deployment_app, name="deployment")
host_app.add_typer(logs_app, name="logs")

BEIJING = timezone(timedelta(hours=8), name="Asia/Shanghai")
LIST_COLUMNS = (
    ("服务 ID", "serviceId"), ("服务名称", "serviceName"),
    ("服务版本", "serviceVersion"), ("环境", "env"),
    ("状态", "status"), ("服务实例", "instance"),
    ("模型名称", "modelName"), ("归属者", "owner"),
)
HOST_COLUMNS = (
    ("部署 ID", "deployId"), ("集群", "clusterName"),
    ("pod名称", "nodeName"), ("podIP", "nodeHost"),
    ("主机IP", "hostIp"), ("规格", "spec"),
    ("状态", "health_status"), ("最大并发数", "execute_limit"),
    ("超时时间(ms)", "service_timeout"), ("CPU", "cpuUsage"),
    ("GPU", "gpuUsage"), ("内存", "memUsage"), ("NPU", "npuUsage"),
    ("创建时间", "create_time"), ("更新时间", "update_time"),
)
DEPLOYMENT_COLUMNS = (
    ("blockId", "blockId"), ("区域", "region"), ("站点", "domain"),
    ("集群名称", "clusterName"), ("镜像", "image"),
    ("规格", "resourceSpec"), ("推理框架", "framework"),
    ("yaml模板", "yamlId"), ("创建时间", "createTime"),
    ("更新时间", "updateTime"),
)
TIME_FIELDS = {"create_time", "update_time", "createTime", "updateTime"}
USAGE_FIELDS = {"cpuUsage", "gpuUsage", "memUsage", "npuUsage"}


def _text(value: Any) -> str:
    return "-" if value is None or value == "" else str(value)


def _time(value: Any) -> str:
    try:
        instant = datetime.fromtimestamp(float(Decimal(str(value))) / 1000, BEIJING)
    except (InvalidOperation, ValueError, OverflowError, OSError):
        try:
            instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if instant.tzinfo is None:
                raise ValueError("时间缺少时区")
            instant = instant.astimezone(BEIJING)
        except (ValueError, OverflowError):
            error_console.print(f"提示：时间无法解析，保留原值：{value}", markup=False)
            return str(value)
    return instant.strftime("%Y-%m-%d %H:%M:%S")


def _usage(value: Any) -> str:
    try:
        number = Decimal(str(value))
        if number == -1:
            return "-"
        if number >= 0 and number.is_finite():
            return f"{number * 100:.2f}%"
    except (InvalidOperation, ValueError):
        pass
    return str(value)


def _joined(item: dict[str, Any], fields: tuple[str, ...], separator: str) -> str:
    values = [str(item[field]) for field in fields
              if item.get(field) is not None and item.get(field) != ""]
    return separator.join(values) if values else "-"


def _resource_spec(item: dict[str, Any]) -> str:
    parts = []
    for field, unit in (("cpuLimit", "C"), ("memoryLimit", "G"),
                        ("gpuLimit", "GPU"), ("npuLimit", "NPU")):
        value = item.get(field)
        if value is None or value == "":
            continue
        try:
            if Decimal(str(value)) == 0:
                continue
        except InvalidOperation:
            pass
        parts.append(f"{value}{unit}")
    return "".join(parts) or "-"


def display_value(field: str, item: dict[str, Any]) -> str:
    if field == "image":
        return _joined(item, ("imageName", "imageVersion"), " ")
    if field == "framework":
        return _joined(item, ("wiseEyeName", "wiseEyeVersion"), "@")
    if field == "resourceSpec":
        return _resource_spec(item)
    value = item.get(field)
    if value is None or value == "":
        return "-"
    if field in TIME_FIELDS:
        return _time(value)
    if field in USAGE_FIELDS:
        return _usage(value)
    if field == "status":
        return {"0": "正常", "1": "异常"}.get(str(value), str(value))
    if field == "health_status":
        return "正常" if str(value) == "0" else "异常"
    return _text(value)


def render_page(view: str, result: dict[str, Any], output: str) -> None:
    if output == "json":
        print_result(result, output)
        return
    columns = {"list": LIST_COLUMNS, "host": HOST_COLUMNS,
               "deployment": DEPLOYMENT_COLUMNS}[view]
    table = Table(show_header=True, header_style="bold cyan")
    for index, (title, _) in enumerate(columns):
        if index == 0:
            table.add_column(title, width=36, min_width=36, max_width=36,
                             no_wrap=True, overflow="ignore")
        else:
            table.add_column(title, min_width=1, overflow="fold")
    for item in result["items"]:
        table.add_row(*(Text(display_value(field, item)) for _, field in columns))
    console.print(table)
    if not result["items"]:
        console.print({"list": "暂无服务记录", "host": "暂无服务主机记录",
                       "deployment": "暂无服务部署记录"}[view])
    total = result.get("total")
    if total is None:
        console.print(f"第 {result['pageIndex']} 页 · 本页 {len(result['items'])} 条")
    else:
        console.print(f"第 {result['pageIndex']} 页 · 每页 {result['pageSize']} 条 · 共 {total} 条")
    if view != "list":
        console.print("详情视图仅显示第 1 页 10 条")
        console.print("时间：Asia/Shanghai (UTC+08:00)")


def _selected_output(runtime: Any, output: Optional[str]) -> str:
    selected = (output or runtime.config.current_profile().output_format).lower()
    if selected not in {"table", "json"}:
        raise ValueError("output 仅支持 table 或 json")
    return selected


def _selected_business(runtime: Any, client: Any) -> None:
    profile = runtime.config.current_profile()
    selected = runtime.business.selected_business_id(profile.name, client.username)
    if selected != client.business_id:
        raise BusinessError("当前环境 selected.businessId 与业务目录不一致，请运行 ml business refresh")


def _service_id(value: str) -> str:
    service_id = value.strip()
    if not service_id:
        raise ValueError("服务 ID 不能为空")
    return service_id


def _required_text(value: str, label: str) -> str:
    if not value.strip():
        raise ValueError(f"{label}不能为空")
    return value.strip()


@service_app.command("list")
def list_services(
    context: typer.Context,
    page: int = typer.Option(1, "--page", min=1, help="页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, help="每页条数"),
    name: Optional[str] = typer.Option(None, "--name", "--service-name", help="服务名称条件"),
    model_name: Optional[str] = typer.Option(None, "--model-name", help="模型名称条件"),
    model_version: Optional[str] = typer.Option(None, "--model-version", help="模型版本条件"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="table 或 json"),
) -> None:
    """分页查询当前业务的服务。"""
    try:
        filters = (name, model_name, model_version)
        if any(value is not None and not value.strip() for value in filters):
            raise ValueError("筛选条件不能为空白")
        runtime = runtime_from_context(context)
        selected = _selected_output(runtime, output)

        def query(client):
            _selected_business(runtime, client)
            return ServiceCatalog(client).list_services(
                page, page_size, *(value.strip() if value is not None else None for value in filters)
            )

        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(query)
        render_page("list", result, selected)
    except Exception as exc:
        fail(exc)


@host_app.command("list")
def list_hosts(
    context: typer.Context,
    service_id: str = typer.Argument(..., help="服务 ID"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="table 或 json"),
) -> None:
    """查询指定服务的主机视图。"""
    try:
        service_id = _service_id(service_id)
        runtime = runtime_from_context(context)
        selected = _selected_output(runtime, output)

        def query(client):
            _selected_business(runtime, client)
            return ServiceCatalog(client).list_hosts(service_id)

        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(query)
        render_page("host", result, selected)
    except Exception as exc:
        fail(exc)


@deployment_app.command("list")
def list_deployments(
    context: typer.Context,
    service_id: str = typer.Argument(..., help="服务 ID"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="table 或 json"),
) -> None:
    """查询指定服务的部署视图。"""
    try:
        service_id = _service_id(service_id)
        runtime = runtime_from_context(context)
        selected = _selected_output(runtime, output)

        def query(client):
            _selected_business(runtime, client)
            return ServiceCatalog(client).list_deployments(service_id)

        with redirect_stdout(sys.stderr):
            result = runtime.authenticated_call(query)
        render_page("deployment", result, selected)
    except Exception as exc:
        fail(exc)


@logs_app.command("list")
def list_log_files(
    context: typer.Context,
    pod_name: str = typer.Argument(..., help="Pod 名称"),
    cluster_name: str = typer.Option(..., "--cluster", help="集群名称"),
    log_type: str = typer.Option(..., "--type", help="日志类型"),
) -> None:
    """查看指定 Pod 的日志文件列表。"""
    try:
        pod_name = _required_text(pod_name, "Pod 名称")
        cluster_name = _required_text(cluster_name, "集群名称")
        log_type = _required_text(log_type, "日志类型")
        runtime = runtime_from_context(context)

        def query(client):
            _selected_business(runtime, client)
            return ServiceCatalog(client).list_pod_log_files(
                pod_name, cluster_name, log_type,
            )

        with redirect_stdout(sys.stderr):
            files = runtime.authenticated_call(query)
        table = Table(show_header=True, header_style="bold cyan")
        for title in ("日志文件大小", "修改时间", "日志文件名称"):
            table.add_column(title, overflow="fold")
        for item in files:
            table.add_row(*(Text(_text(item.get(field))) for field in
                            ("fileSize", "updateTime", "fileName")))
        console.print(table)
        if not files:
            console.print("暂无日志文件")
    except Exception as exc:
        fail(exc)


@logs_app.command("search")
def search_logs(
    context: typer.Context,
    pod_name: str = typer.Argument(..., help="Pod 名称"),
    cluster_name: str = typer.Option(..., "--cluster", help="集群名称"),
    log_type: str = typer.Option(..., "--type", help="日志类型"),
    file_name: str = typer.Option(..., "--file", help="日志文件名称"),
    keywords: Optional[list[str]] = typer.Option(None, "--keyword", help="检索关键词，可重复"),
    line: int = typer.Option(200, "--line", min=1, help="检索行数"),
    search_order: str = typer.Option("tail", "--search-order", help="检索顺序"),
    grep_scope: str = typer.Option("C", "--grep-scope", help="关键词范围"),
    grep_line: int = typer.Option(0, "--grep-line", min=0, help="关键词上下文行数"),
) -> None:
    """检索指定日志文件并输出正文。"""
    try:
        pod_name = _required_text(pod_name, "Pod 名称")
        cluster_name = _required_text(cluster_name, "集群名称")
        log_type = _required_text(log_type, "日志类型")
        file_name = _required_text(file_name, "日志文件名称")
        search_order = _required_text(search_order, "检索顺序")
        grep_scope = _required_text(grep_scope, "关键词范围")
        if keywords and any(not keyword.strip() for keyword in keywords):
            raise ValueError("检索关键词不能为空白")
        runtime = runtime_from_context(context)

        def query(client):
            _selected_business(runtime, client)
            return ServiceCatalog(client).search_pod_log(
                pod_name, cluster_name, log_type, file_name,
                keywords or [], line, search_order, grep_scope, grep_line,
            )

        with redirect_stdout(sys.stderr):
            content = runtime.authenticated_call(query)
        typer.echo(content)
    except Exception as exc:
        fail(exc)


# 独立模块负责引导流程，旧命令继续使用相同的接口服务。
from .service_logs import service_logs

service_app.command("logs")(service_logs)
