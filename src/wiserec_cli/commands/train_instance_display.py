"""执行实例表格中的运行状态动画。"""

import sys
import time

from rich.console import Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text


def running_status() -> Spinner:
    return Spinner("circleQuarters", text=Text("执行中", style="yellow"), style="yellow")


def show_running_instances(console, table, pagination: str) -> None:
    page = Group(table, Text(pagination))
    if not console.is_interactive or not sys.stdin.isatty():
        console.print(page)
        return

    console.print(Text("按 Ctrl+C 停止动画"))
    try:
        with Live(page, console=console, refresh_per_second=12,
                  redirect_stdout=False, redirect_stderr=False):
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        pass
