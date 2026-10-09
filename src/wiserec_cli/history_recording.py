"""与配置加载解耦的调用捕获与脱敏，只在调用结束后写历史。"""

import json
import os
import time
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import user_config_dir
from .history_store import HistoryStore, warning
from .models import BEIJING_TIMEZONE


ACTIVE_RECORD = ContextVar('ml_history_record', default=None)


def observe_runtime(runtime):
    record = ACTIVE_RECORD.get()
    if record is not None and not record.observed:
        record.path = runtime.config.path
        record.before = runtime.config.current_name
        record.observed = True
        try:
            data = json.loads(runtime.business.path.read_text(encoding='utf-8'))
            record.business_id = data.get('profiles', {}).get(record.before, {}).get('selected', {}).get('businessId')
        except (OSError, ValueError, AttributeError):
            pass


def root_arguments(args):
    config = os.environ.get('ML_CONFIG')
    remaining = []
    disabled = os.environ.get('ML_HISTORY') == '0'
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == '--config' and index + 1 < len(args):
            config = args[index + 1]
            index += 2
            continue
        if arg.startswith('--config='):
            config = arg.split('=', 1)[1]
        elif arg == '--no-history':
            disabled = True
        elif not arg.startswith('-'):
            remaining = args[index:]
            break
        index += 1
    return config, remaining, disabled


def config_location(config=None):
    if config:
        return Path(config).expanduser().resolve()
    local = Path.cwd() / 'config.json'
    return local.resolve() if local.exists() else user_config_dir() / 'config.json'


def environment(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8')).get('current')
        return value if isinstance(value, str) else None
    except (OSError, ValueError, AttributeError):
        return None


def safe_text(value):
    return ''.join(f'\\x{ord(char):02x}' if ord(char) < 32 or ord(char) == 127 else char for char in value)


def safe_command(args, remaining):
    from .invocation import format_invocation
    if remaining[:2] == ['jupyter', 'exec']:
        # 任意子进程参数可能包含脚本或凭据，整段隐藏。
        start = len(args) - len(remaining)
        args = args[:start + 2] + ['[REDACTED EXEC]']
    return safe_text(format_invocation(args))


class InvocationRecord:
    def __init__(self, args):
        config, remaining, disabled = root_arguments(args)
        self.enabled = bool(remaining) and not disabled and remaining[0] not in {'history', 'tree'}
        if '--help' in (remaining[:remaining.index('--')] if '--' in remaining else remaining):
            self.enabled = False
        self.observed = False
        self.business_id = None
        self.interrupted = False
        self.started = time.time()
        self.clock = time.monotonic()
        self.path = config_location(config)
        self.before = environment(self.path)
        self.command = safe_command(args, remaining)
        self.cwd = str(Path.cwd())

    def finish(self, exit_code):
        if not self.enabled:
            return
        try:
            if self.interrupted:
                exit_code = 130
            HistoryStore(self.path).append({
                'time': datetime.fromtimestamp(self.started, BEIJING_TIMEZONE).strftime('%Y-%m-%d %H:%M:%S'),
                'started_at': self.started, 'finished_at': time.time(),
                'duration_ms': round((time.monotonic() - self.clock) * 1000),
                'command': self.command, 'env': self.before, 'env_after': environment(self.path),
                'config': safe_text(str(self.path)), 'cwd': safe_text(self.cwd),
                'business_id': self.business_id, 'version': __version__, 'exit_code': exit_code,
                'status': 'success' if exit_code == 0 else 'interrupted' if exit_code == 130 else 'failed',
                'redacted': 'REDACTED' in self.command, 'truncated': '[已截断]' in self.command,
            })
        except (OSError, ValueError, TypeError):
            warning('无法保存本次命令历史，原命令执行结果不受影响')
