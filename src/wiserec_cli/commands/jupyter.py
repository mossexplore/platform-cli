"""Jupyter 第一阶段：Notebook 前台执行与交互 Terminal。"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import typer
from rich.table import Table
from rich.text import Text

from ..jupyter.connection import JupyterClient, from_runtime
from ..jupyter.notebook import run_notebook
from ..jupyter.terminal import attach, require_tty
from ..output import console
from .common import fail, runtime_from_context

jupyter_app = typer.Typer(no_args_is_help=True, help="Jupyter Notebook 前台执行与 Terminal")
notebook_app = typer.Typer(no_args_is_help=True, help="执行完整 Notebook")
terminal_app = typer.Typer(no_args_is_help=True, help="远程交互终端；Ctrl+] 断开连接")
jupyter_app.add_typer(notebook_app, name="notebook")
jupyter_app.add_typer(terminal_app, name="terminal")

# Notebook 输出作为文本展示；Terminal 为交互用途有意保留控制序列。
_CONTROL = re.compile(r"\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b\[[0-?]*[ -/]*[@-~]|[\x00-\x08\x0b-\x1f\x7f]")


def text_output(value):
    typer.echo(_CONTROL.sub("", value), nl=False, err=True)


def client_for(context):
    return JupyterClient(from_runtime(runtime_from_context(context)))


def display_time(value):
    if not value:
        return "-"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return str(value)
        return parsed.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return str(value)


@jupyter_app.command("doctor")
def doctor(context: typer.Context):
    """验证 Token、业务上下文、Kernel 与终端管理接口（不创建资源）。"""
    try:
        with client_for(context) as client:
            specs = client.request("GET", "api/kernelspecs")
            terminals = client.request("GET", "api/terminals")
            typer.echo("Jupyter HTTP 认证成功；businessid 已携带")
            typer.echo("可用 Kernel：" + ", ".join(specs.get("kernelspecs", {})))
            typer.echo(f"Terminal 接口可用，现有终端 {len(terminals)} 个")
            typer.echo("WebSocket 通道将在实际执行或 attach 时验证。")
    except Exception as exc:
        fail(exc)


@notebook_app.command("run")
def run(context: typer.Context,
        source: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
        download: Path = typer.Option(Path("results"), "--download", help="本地结果根目录，每次新建 UUID 子目录"),
        kernel: Optional[str] = typer.Option(None, "--kernel", help="覆盖当前环境 Kernel 名称"),
        cwd: str = typer.Option("", "--cwd", help="相对服务器根目录的工作目录；默认使用本次独立目录"),
        timeout: float = typer.Option(600, "--timeout", min=0.1, help="全部单元格执行时限（秒）"),
        startup_timeout: float = typer.Option(60, "--startup-timeout", min=0.1, help="Kernel 就绪等待（秒）"),
        output: str = typer.Option("text", "--output", help="text 或 json")):
    """上传并按顺序执行 Notebook；失败也保存部分结果，不自动重试。"""
    if output not in {"text", "json"}:
        fail("--output 仅支持 text 或 json")
    if source.suffix.lower() != ".ipynb":
        fail("输入必须为 .ipynb 文件")
    try:
        with client_for(context) as client:
            result = run_notebook(client, source, download, kernel=kernel, cwd=cwd,
                                  timeout=timeout, startup_timeout=startup_timeout, emit=text_output)
    except Exception as exc:
        fail(exc)
    if output == "json":
        typer.echo(json.dumps(result, ensure_ascii=False))
    else:
        typer.echo(f"执行 ID：{result['id']}\n状态：{result['status']}")
        typer.echo(f"完成时间：{display_time(result['finished_at'])}\n结果：{result['notebook']}")
        if result.get("error"):
            typer.echo(result["error"], err=True)
        for warning in result["cleanup_errors"]:
            typer.echo(warning, err=True)
    code = {"SUCCEEDED": 0, "TIMED_OUT": 124, "INTERRUPTED": 130, "LOST": 2}.get(result["status"], 1)
    raise typer.Exit(code=code)


@terminal_app.command("list")
def list_terminals(context: typer.Context):
    """列出当前 Jupyter 身份可见的终端。"""
    try:
        with client_for(context) as client:
            items = client.request("GET", "api/terminals")
        table = Table()
        table.add_column("终端名称", min_width=36, max_width=36, width=36, no_wrap=True, overflow="ignore")
        table.add_column("最后活动（北京时间）", overflow="fold")
        for item in items:
            table.add_row(Text(str(item["name"])), Text(display_time(item.get("last_activity"))))
        console.print(table)
    except Exception as exc:
        fail(exc)


@terminal_app.command("open")
def open_terminal(context: typer.Context):
    """创建终端并连接，Ctrl+] 仅断开本地连接。"""
    try:
        require_tty()
        with client_for(context) as client:
            terminal = client.request("POST", "api/terminals", {})
            typer.echo(f"终端名称：{terminal['name']}；按 Ctrl+] 断开，exit 关闭远程 Shell。")
            attach(client, terminal["name"])
    except Exception as exc:
        fail(exc)


@terminal_app.command("attach")
def attach_terminal(context: typer.Context, name: str = typer.Argument(...)):
    """连接已有终端，不保证补取完整历史输出。"""
    try:
        require_tty()
        with client_for(context) as client:
            typer.echo(f"连接终端 {name}；按 Ctrl+] 断开。")
            attach(client, name)
    except Exception as exc:
        fail(exc)


@terminal_app.command("close")
def close_terminal(context: typer.Context, name: str = typer.Argument(...)):
    """关闭指定远程终端及其 Shell，会影响在其中运行的进程。"""
    try:
        with client_for(context) as client:
            client.request("DELETE", "api/terminals/" + quote(name, safe=""))
        typer.echo("已关闭远程终端：" + name)
    except Exception as exc:
        fail(exc)
