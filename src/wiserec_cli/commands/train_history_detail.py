"""执行记录详情及分布式角色表格。"""
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
import sys
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.text import Text

from ..output import console, error_console, print_result
from ..services.train_history_logs import HistoryLogService, role_records
from .common import fail, runtime_from_context


ROLE_COLUMNS = (
    ('名称', 'roleType'), ('算法名称', 'algorithmName'), ('状态', 'status'),
    ('节点数', 'infraSize'), ('CPU', 'cpuSize'), ('GPU', 'gpuSize'),
    ('内存', 'memorySize'), ('执行节点', 'hostIp'), ('开始时间', 'createTime'),
)


def role_value(field, value):
    if value is None or value == '':
        return '-'
    if field == 'createTime':
        try:
            zone = timezone(timedelta(hours=8))
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                date = datetime.fromtimestamp(value / 1000, zone)
            else:
                date = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
                if date.tzinfo is None:
                    return '-'
                date = date.astimezone(zone)
            return date.strftime('%Y-%m-%d %H:%M:%S')
        except (ValueError, OverflowError, OSError):
            return '-'
    return str(value)


def show_roles(roles, *, selection=False):
    table = Table(header_style='bold cyan')
    table.add_column('角色作业 ID', width=36, min_width=36, max_width=36,
                     no_wrap=True, overflow='ignore')
    if selection:
        table.add_column('编号', justify='right')
    for title, _ in ROLE_COLUMNS:
        table.add_column(title, overflow='fold', min_width=4)
    for index, role in enumerate(roles, 1):
        cells = [Text(role_value('roleJobId', role.get('roleJobId')))]
        if selection:
            cells.append(str(index))
        cells.extend(Text(role_value(field, role.get(field))) for _, field in ROLE_COLUMNS)
        table.add_row(*cells)
    target = error_console if selection else console
    Console(file=target.file, width=max(target.width, 165)).print(table)


def history_detail(
    context: typer.Context,
    task_id: str = typer.Argument(..., help='训练任务 ID'),
    job_id: str = typer.Argument(..., help='执行记录 ID'),
    output: Optional[str] = typer.Option(None, '--output', '-o', help='输出格式: table 或 json'),
):
    """查询执行记录详情及分布式角色列表"""
    try:
        from .train import selected_output, render_page

        runtime = runtime_from_context(context)
        selected = selected_output(runtime, output)
        task_id, job_id = task_id.strip(), job_id.strip()
        with redirect_stdout(sys.stderr):
            record = runtime.authenticated_call(
                lambda client: HistoryLogService(client).find_record(task_id, job_id))
        if selected == 'json':
            print_result(record, selected)
            return
        if record.get('jobType') == 'dps-train':
            roles = role_records(record)
            console.print(f'任务 ID：{task_id}\n作业 ID：{job_id}\n任务类型：分布式训练', markup=False)
            show_roles(roles)
            if not roles:
                console.print('暂无角色信息')
        else:
            render_page({'items': [record], 'count': 1, 'pageIndex': 1, 'pageSize': 1},
                        selected, history_task_id=task_id)
    except Exception as exc:
        fail(exc)
