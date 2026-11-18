"""执行实例表格中的状态动画。"""

import sys
import time

from rich.console import Group
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text


ANIMATED_STATUSES = {"RUNNING": ("执行中", "yellow"), "QUEUE": ("排队中", "blue")}


def instance_status_spinner(status: str) -> Spinner:
    label, color = ANIMATED_STATUSES[status]
    return Spinner("circleHalves", text=Text(label, style=color), style=color, speed=0.4)


def show_animated_instances(console, table, pagination: str) -> None:
    page = Group(table, Text(pagination))
    if not console.is_interactive or not sys.stdin.isatty():
        console.print(page)
        return

    try:
        with Live(page, console=console, refresh_per_second=12,
                  redirect_stdout=False, redirect_stderr=False):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
