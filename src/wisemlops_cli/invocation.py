"""记录本次 CLI 的参数序列，脱敏后供权限调用日志使用。"""
import os
import re
import shlex
import subprocess
from typer.core import TyperGroup

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
    def parse_args(self, ctx, args):
        # 必须在 Click 消费参数前捕获；兼容真实入口和 CliRunner，不读取其他进程参数。
        ctx.meta['full_command'] = format_invocation(args)
        return super().parse_args(ctx, args)
