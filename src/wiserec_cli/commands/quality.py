"""质量监控报告命令。"""

import sys
from contextlib import redirect_stdout
from typing import Optional

import typer

from ..errors import BusinessError
from ..services.quality import QualityService, normalize_type
from .common import fail, runtime_from_context
from .quality_display import render_page

quality_app = typer.Typer(no_args_is_help=True, help="质量监控报告")
feature_app = typer.Typer(no_args_is_help=True, help="特征列表")
wide_app = typer.Typer(no_args_is_help=True, help="宽表特征集")
quality_app.add_typer(feature_app, name="feature")
quality_app.add_typer(wide_app, name="wide-featureset")
TYPE_HELP = "连续/CONTINUOUS、离散/DISCRETE、有序/ORDINAL、分类/CATEGORICAL、序列/SEQUENCE、长序列/LONG_SEQUENCE、向量/VECTOR"


def selected_service(runtime, client):
    selected = runtime.business.selected_business_id(
        runtime.config.current_profile().name, client.username,
    )
    if selected != client.business_id:
        raise BusinessError("当前环境 selected.businessId 与业务目录不一致，请运行 ml business refresh")
    return QualityService(client)


def run_list(context, output, operation, wide=False):
    runtime = runtime_from_context(context)
    selected = (output or runtime.config.current_profile().output_format).lower()
    if selected not in {"table", "json"}:
        raise ValueError("output 仅支持 table 或 json")
    with redirect_stdout(sys.stderr):
        result = runtime.authenticated_call(
            lambda client: operation(selected_service(runtime, client))
        )
    render_page(result, selected, wide)


@feature_app.command("list")
def list_features(
    context: typer.Context,
    name: str = typer.Option("", "--name", help="特征名称"),
    table_name: str = typer.Option("", "--table-name", help="特征表名"),
    feature_value_type: Optional[str] = typer.Option(None, "--feature-value-type", help=TYPE_HELP),
    indicator_type: Optional[str] = typer.Option(None, "--indicator-type", help=TYPE_HELP),
    page: int = typer.Option(1, "--page", min=1, help="开始页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, max=100, help="每页条数，最多 100"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
):
    """分页查询当前业务下的特征质量信息"""
    try:
        feature_value_type = normalize_type(feature_value_type)
        indicator_type = normalize_type(indicator_type)
        run_list(context, output, lambda service: service.list_features(
            page, page_size, name, table_name, feature_value_type, indicator_type,
        ))
    except Exception as exc:
        fail(exc)


@wide_app.command("list")
def list_wide_featuresets(
    context: typer.Context,
    name: str = typer.Option("", "--name", help="特征集名称"),
    page: int = typer.Option(1, "--page", min=1, help="开始页码"),
    page_size: int = typer.Option(10, "--page-size", min=1, max=100, help="每页条数，最多 100"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
):
    """分页查询当前业务下的宽表特征集质量信息"""
    try:
        run_list(context, output, lambda service: service.list_wide_featuresets(
            page, page_size, name,
        ), wide=True)
    except Exception as exc:
        fail(exc)
