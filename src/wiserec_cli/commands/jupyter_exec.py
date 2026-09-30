"""Agent 非交互子进程执行入口。"""
from typing import List, Optional

import typer

from ..jupyter.execution import execute
from .jupyter_files import operation, output_result


def exec_command(context: typer.Context,
                 command: List[str] = typer.Argument(..., help='-- 后的程序及参数；不隐式使用 Shell'),
                 cwd: str = typer.Option('', '--cwd', help='远端已有目录，相对 Jupyter 根目录'),
                 timeout: float = typer.Option(60, '--timeout', min=0.1),
                 startup_timeout: float = typer.Option(60, '--startup-timeout', min=0.1),
                 max_output: int = typer.Option(1048576, '--max-output', min=1, max=10485760,
                                               help='stdout/stderr 各自保留的最大字节数'),
                 kernel: Optional[str] = typer.Option(None, '--kernel', help='远端 Python Kernel 名称'),
                 output: str = typer.Option('text', '--output', '-o'),
                 studio_id: Optional[str] = typer.Option(None, '--studio-id')):
    """独立 Python Kernel 启动 POSIX 子进程，收集结果后释放 Kernel；不重试。"""
    with operation(context, studio_id, output) as client:
        result = execute(client, command, cwd, timeout, startup_timeout, max_output, kernel)
        output_result(client, result, output)
    status = result['status']
    code = {'SUCCEEDED': 0, 'TIMED_OUT': 124, 'INTERRUPTED': 130, 'LOST': 2}.get(status, 1)
    if status == 'FAILED' and isinstance(result['exit_code'], int) and 0 < result['exit_code'] < 124:
        code = result['exit_code']
    raise typer.Exit(code)
