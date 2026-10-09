"""记录本次 CLI 的参数序列，脱敏后供权限调用日志使用。"""
import os
import re
import shlex
import subprocess
from typer.core import TyperGroup
from .client_metadata import begin_invocation

MAX_COMMAND_LENGTH = 8192
_SECRET = re.compile(r'password|passwd|secret|token|cookie|csrf|authorization|api[-_]?key|credential', re.I)
_OPAQUE = {'--data', '--json', '--body', '--payload', '--header', '--headers', '-h'}


def format_invocation(args):
    """保留参数顺序与值；敏感选项及不透明请求体整体隐藏，不读取文件内容。"""
    safe = []
    hide_next = False
    for value in args:
        if hide_next:
            safe.append('[REDACTED]')
            hide_next = False
            continue
        key, separator, content = value.partition('=')
        if (value.startswith('-') and (_SECRET.search(key) or key.lower() in _OPAQUE)):
            safe.append(key + '=[REDACTED]' if separator else key)
            hide_next = not separator
        elif _SECRET.search(key) and separator:
            safe.append(key + '=[REDACTED]')
        elif re.search(r'://[^/\s]*@', value) or re.search(r'[?&](?:access[-_]?token|token|key|password|secret|api[-_]?key)=', value, re.I):
            safe.append('[REDACTED URL]')
        elif re.search(r'"[^"]*(?:password|secret|token|cookie|authorization|api_key)[^"]*"\s*:', value, re.I):
            safe.append('[REDACTED JSON]')
        else:
            safe.append(value)
    parts = ['ml', *safe]
    result = subprocess.list2cmdline(parts) if os.name == 'nt' else shlex.join(parts)
    suffix = ' …[已截断]'
    return result if len(result) <= MAX_COMMAND_LENGTH else result[:MAX_COMMAND_LENGTH-len(suffix)] + suffix


class InvocationGroup(TyperGroup):
    def main(self, args=None, *positional, **kwargs):
        import sys
        import click
        from .history_recording import ACTIVE_RECORD, InvocationRecord
        from .history_store import warning

        arguments = list(sys.argv[1:] if args is None else args)
        record = None
        try:
            record = InvocationRecord(arguments)
        except (OSError, ValueError):
            warning('无法准备命令历史，原命令继续执行')
        token = ACTIVE_RECORD.set(record)
        code = 1
        try:
            result = super().main(arguments, *positional, **kwargs)
            code = result if type(result) is int else 0
            return result
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 0 if exc.code is None else 1
            raise
        except click.exceptions.Exit as exc:
            code = exc.exit_code
            raise
        except click.ClickException as exc:
            code = exc.exit_code
            raise
        except (KeyboardInterrupt, click.Abort):
            code = 130
            raise
        finally:
            try:
                if record is not None:
                    record.finish(code)
            finally:
                ACTIVE_RECORD.reset(token)

    def invoke(self, ctx):
        import click
        from .history_recording import ACTIVE_RECORD
        try:
            return super().invoke(ctx)
        except (KeyboardInterrupt, click.Abort):
            record = ACTIVE_RECORD.get()
            if record is not None:
                record.interrupted = True
            raise

    def parse_args(self, ctx, args):
        begin_invocation()
        # 必须在 Click 消费参数前捕获；兼容真实入口和 CliRunner，不读取其他进程参数。
        ctx.meta['full_command'] = format_invocation(args)
        return super().parse_args(ctx, args)
