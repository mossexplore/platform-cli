"""服务测试命令与多节点结果展示。"""

from __future__ import annotations

import json
import sys
from contextlib import redirect_stdout
from typing import Optional

import typer
from rich.table import Table
from rich.text import Text

from .. import messages as msg
from ..output import console, print_result
from ..services.service_mock import ServiceMock, normalize_response, parse_sample, validate_request_sample
from .common import fail, runtime_from_context


def _mock_value(node, field):
    value = node.get(field)
    if field == "mockResponse":
        try:
            value = json.dumps(parse_sample(node["mockResponseRaw"]),
                               ensure_ascii=False, indent=2, allow_nan=False)
        except (ValueError, RecursionError):
            value = node.get("mockResponseRaw")
    return Text("-" if value is None or value == "" else str(value))


def render_mock(payload, output, *, vertical=False):
    if output == "json":
        print_result(payload, output)
        return
    columns = (
        ("主机名称", "hostName"), ("机器规格", "scope"), ("站点", "domain"),
        ("结果码", "retCode"), ("结果报文", "mockResponse"), ("耗时(ms)", "cost"),
    )
    if vertical:
        fields = tuple(column for column in columns if column[1] != "mockResponse")
        fields += (("结果报文", "mockResponse"),)
        for node in payload["result"]["nodeList"]:
            table = Table(show_header=True, header_style="bold cyan", show_lines=True)
            table.add_column("字段", no_wrap=True)
            table.add_column("值", min_width=1, overflow="fold", ratio=1)
            for title, field in fields:
                table.add_row(Text(title), _mock_value(node, field))
            console.print(table)
        return
    table = Table(show_header=True, header_style="bold cyan", show_lines=True)
    for title, field in columns:
        table.add_column(title, min_width=1, overflow="fold",
                         ratio=4 if field == "mockResponse" else 1)
    for node in payload["result"]["nodeList"]:
        table.add_row(*(_mock_value(node, field) for _, field in columns))
    console.print(table)


def _run_mock(context, service_id, transmission_tag, output, pod_ip=None, request_sample=None):
    from .service import _selected_business, _selected_output, _service_id

    try:
        service_id = _service_id(service_id)
        runtime = runtime_from_context(context)
        selected = _selected_output(runtime, output)

        def query(client):
            _selected_business(runtime, client)
            return ServiceMock(client).run(
                service_id, transmission_tag=transmission_tag, pod_ip=pod_ip,
                request_sample=request_sample,
            )

        # 测试调用不具备幂等保证，认证失败也不自动重放整个流程。
        with redirect_stdout(sys.stderr):
            if pod_ip is not None:
                msg.detail(f"目标主机 Pod IP：{pod_ip}")
            payload = runtime.authenticated_call(query, retry_auth=False)
        normalized, issues = normalize_response(payload)
        render_mock(normalized, selected, vertical=pod_ip is not None)
    except Exception as exc:
        fail(exc)
    if issues:
        for issue in issues:
            msg.error(issue)
        raise typer.Exit(code=1)


def _request_sample(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    try:
        return validate_request_sample(value)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc


def service_mock(
    context: typer.Context,
    service_id: str = typer.Argument(..., help="服务 ID"),
    transmission_tag: int = typer.Option(
        0, "--transmission-tag", min=0, max=1,
        help="0 不调用透传接口，1 调用透传接口",
    ),
    request_sample: Optional[str] = typer.Option(
        None, "--request-sample", callback=_request_sample,
        help="样例报文，必须为标准 JSON；默认使用服务文档样例",
    ),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="table 或 json"),
) -> None:
    """使用样例报文测试服务响应"""
    _run_mock(context, service_id, transmission_tag, output, request_sample=request_sample)


def _pod_ip(value: str) -> str:
    if not value.strip():
        raise typer.BadParameter("Pod IP 不能为空")
    return value.strip()


def host_mock(
    context: typer.Context,
    service_id: str = typer.Argument(..., help="服务 ID"),
    pod_ip: str = typer.Option(
        ..., "--pod-ip", callback=_pod_ip, help="用于查询主机视图的 Pod IP",
    ),
    transmission_tag: int = typer.Option(
        0, "--transmission-tag", min=0, max=1,
        help="0 不调用透传接口，1 调用透传接口",
    ),
    request_sample: Optional[str] = typer.Option(
        None, "--request-sample", callback=_request_sample,
        help="样例报文，必须为标准 JSON；默认使用服务文档样例",
    ),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="table 或 json"),
) -> None:
    """使用样例报文测试指定主机"""
    _run_mock(context, service_id, transmission_tag, output, pod_ip, request_sample)
