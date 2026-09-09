"""统一 table/json 输出。"""

from __future__ import annotations

import json
from typing import Any

from rich.console import Console
from rich.table import Table


console = Console()
error_console = Console(stderr=True)


def print_result(value: Any, output_format: str = "table") -> None:
    selected = output_format.lower()
    if selected == "json":
        console.print_json(json.dumps(value, ensure_ascii=False, default=str))
        return
    if selected != "table":
        raise ValueError("output 仅支持 table 或 json")

    table = Table(show_header=True, header_style="bold cyan")
    if isinstance(value, dict):
        table.add_column("字段")
        table.add_column("值")
        for key, item in value.items():
            rendered = (
                json.dumps(item, ensure_ascii=False, default=str)
                if isinstance(item, (dict, list))
                else str(item)
            )
            table.add_row(str(key), rendered)
    elif isinstance(value, list) and all(isinstance(item, dict) for item in value):
        keys = list(dict.fromkeys(key for item in value for key in item))
        for key in keys:
            table.add_column(str(key))
        for item in value:
            table.add_row(*(str(item.get(key, "")) for key in keys))
    else:
        table.add_column("结果")
        table.add_row(str(value))
    console.print(table)
