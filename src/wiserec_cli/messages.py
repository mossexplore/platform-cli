"""面向用户的消息输出；结果数据继续使用 stdout。"""
from __future__ import annotations

import os
import re
import sys
from contextlib import redirect_stdout

import typer
from rich.text import Text
from rich.progress import ProgressColumn

from .output import error_console

_LEVELS = {
    "info": ("提示", "cyan"),
    "success": ("成功", "green"),
    "warning": ("警告", "yellow"),
    "error": ("错误", "red"),
}
_CONTROL = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x08\x0b-\x1f\x7f]")
_PREFIX = re.compile(r"^(?:\[(?:提示|成功|警告|错误)\]\s*|(?:提示|成功|警告|错误|升级提醒)[:：]\s*)")
_PLAIN = re.compile(r"https?://\S+|\bml(?:\s+[\w-]+)+|--[\w-]+|\b[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\b")


def render(message: object, level: str = "info") -> Text:
    """前缀着色；警告和错误仅摘要着色，补充说明使用默认色。"""
    label, color = _LEVELS[level]
    body = _PREFIX.sub("", _CONTROL.sub("", str(message)))
    lines = body.splitlines() or [""]
    text = Text(f"[{label}] ", style=color)
    # 显式设置正文样式，避免继承前缀颜色。
    summary = re.split(r"；|，(?=请)", lines[0], maxsplit=1)[0]
    text.append(lines[0], style="default")
    if level in {"warning", "error"}:
        text.stylize(color, len(label) + 3, len(label) + 3 + len(summary))
    if len(lines) > 1:
        text.append("\n" + "\n".join(lines[1:]), style="default")
    offset = len(label) + 3
    for match in _PLAIN.finditer(body):
        text.stylize("default", offset + match.start(), offset + match.end())
    return Text(text.plain) if "NO_COLOR" in os.environ else text


def emit(message: object, level: str = "info") -> None:
    text = render(message, level)
    if not error_console.is_terminal:
        text = Text(text.plain)
    error_console.print(text, highlight=False, soft_wrap=True)


def info(message: object) -> None:
    emit(message)


def detail(message: object) -> None:
    """辅助上下文、进度和操作引导，不额外标记消息级别。"""
    error_console.print(Text(_CONTROL.sub("", str(message))), highlight=False, soft_wrap=True)


def success(message: object) -> None:
    emit(message, "success")


def warning(message: object) -> None:
    emit(message, "warning")


def error(message: object) -> None:
    emit(message, "error")


class MessageColumn(ProgressColumn):
    """进度名称保持原样，不添加消息级别。"""
    def render(self, task) -> Text:
        return Text(task.description)


def ping_status(message: str) -> None:
    """保活服务返回状态文本，退出码由调用方决定。"""
    if message.startswith(("警告", "无法")):
        warning(message)
    elif message.startswith("自动保活已启动"):
        success(message)
    else:
        detail(message)


def prompt_text(message: str) -> str:
    return _CONTROL.sub("", message)


def prompt(message: str, **kwargs):
    # Click 的 input 空格及输入回显也必须走 stderr，避免污染 stdout。
    with redirect_stdout(sys.stderr):
        return typer.prompt(prompt_text(message), err=True, **kwargs)


def confirm(message: str, default: bool = False, abort: bool = False, **kwargs):
    kwargs.pop("err", None)
    choices = "Y/n" if default else "y/N"
    while True:
        answer = prompt(f"{message} [{choices}]", default="", show_default=False, **kwargs).strip().lower()
        if answer in {"", "y", "yes", "n", "no"}:
            result = default if not answer else answer in {"y", "yes"}
            if abort and not result:
                raise typer.Abort()
            return result
        error("请输入 y 或 n")
