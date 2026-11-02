"""宽表特征集装配查询命令与表格展示。"""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

import typer
from rich.table import Table
from rich.text import Text

from .. import messages as msg
from ..output import console, print_result, print_text
from ..services.quality import QualityService
from .common import fail

ASSEMBLY_COLUMNS = (
    ("样本定义ID", "definitionId"), ("样本定义名称", "definitionName"),
    ("装配输出表名", "outputTable"), ("装配最新周期", "latestCycle"),
    ("正负样本比例", "latestRatio"),
)
FEATURE_COLUMNS = (
    ("特征ID", "featureId"), ("特征名", "featureName"),
    ("特征类型", "featureType"), ("特征值类型", "featureValueType"),
    ("装配最新周期", "latestCycleTime"), ("空值率", "nullValueRate"),
)


def display_value(field, value):
    if value is None or value == "":
        return "-"
    if field in {"latestRatio", "nullValueRate"}:
        try:
            number = Decimal(str(value))
            if not number.is_finite():
                raise ValueError("非有限数值")
            return str((number * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)) + "%"
        except (InvalidOperation, ValueError):
            msg.warning(f"比例无法解析，保留原值：{value}")
    return str(value)


def render_assembly(result, output, label, set_id, features=False):
    if output == "json":
        print_result(result, output)
        return
    returned_id = result.get("featureSetId")
    if returned_id and returned_id != set_id:
        msg.info(f"接口返回 featureSetId={returned_id}，与请求 setId={set_id} 不同；后续查询请核对并显式指定 --set-id")
    table = Table(show_header=True, header_style="bold cyan")
    columns = FEATURE_COLUMNS if features else ASSEMBLY_COLUMNS
    for index, (title, field) in enumerate(columns):
        if field == "latestCycleTime":
            title = label + "最新周期"
        if index == 0:
            table.add_column(title, width=36, min_width=36, max_width=36,
                             no_wrap=True, overflow="ignore")
        else:
            table.add_column(title, overflow="fold", min_width=1)
    for item in result["items"]:
        table.add_row(*(Text(display_value(field, item.get(field))) for _, field in columns))
    console.print(table)
    if not result["items"]:
        print_text("暂无特征记录" if features else f"暂无{label}样本定义")
    if features:
        print_text(f"第 {result['pageIndex']} 页 · 每页 {result['pageSize']} 条 · 共 {result['count']} 条")
    else:
        print_text(f"本次返回 {result['count']} 条")


def register_assemblies(wide_app, run_list):
    for assembly_type, label in (("feature_assemble", "特征装配"), ("label_assemble", "标签装配")):
        assembly_app = typer.Typer(no_args_is_help=True, help=label + "质量信息")
        feature_app = typer.Typer(no_args_is_help=True, help=label + "特征列表")
        wide_app.add_typer(assembly_app, name=assembly_type.replace("_", "-"))
        assembly_app.add_typer(feature_app, name="feature")
        _register_commands(assembly_app, feature_app, assembly_type, label, run_list)


def _register_commands(assembly_app, feature_app, assembly_type, label, run_list):
    @assembly_app.command("list", help=f"查询{label}样本定义列表")
    def list_assemblies(
        context: typer.Context,
        set_id: str = typer.Option(..., "--set-id", help="宽表特征集 ID"),
        output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
    ):
        try:
            body = QualityService.assembly_body(set_id, assembly_type)
            run_list(context, output,
                     lambda service: service.list_assemblies(body["setId"], assembly_type),
                     renderer=lambda result, selected: render_assembly(result, selected, label, body["setId"]))
        except Exception as exc:
            fail(exc)

    @feature_app.command("list", help=f"分页查询{label}样本定义下的特征列表")
    def list_features(
        context: typer.Context,
        set_id: str = typer.Option(..., "--set-id", help="宽表特征集 ID"),
        definition_id: str = typer.Option(..., "--definition-id", help="样本定义 ID"),
        page: int = typer.Option(1, "--page", min=1, help="开始页码"),
        page_size: int = typer.Option(10, "--page-size", min=1, max=100, help="每页条数，最多 100"),
        output: Optional[str] = typer.Option(None, "--output", "-o", help="输出格式: table 或 json"),
    ):
        try:
            body = QualityService.assembly_body(set_id, assembly_type, definition_id)
            run_list(context, output, lambda service: service.list_assembly_features(
                body["setId"], body["definitionId"], assembly_type, page, page_size),
                renderer=lambda result, selected: render_assembly(result, selected, label, body["setId"], True))
        except Exception as exc:
            fail(exc)
