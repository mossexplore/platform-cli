"""配置同级 JSONL 历史文件：跨进程锁、原子更新与容量控制。"""

import json
import os
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

LIMIT = 1000


def warning(message):
    import click
    click.echo(f'警告：{message}', err=True)


@contextmanager
def file_lock(path, timeout=3):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as lock:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0, 2)
            if lock.tell() == 0:
                lock.write(b'0')
                lock.flush()
            def acquire():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            def release():
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            def acquire():
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            def release():
                fcntl.flock(lock, fcntl.LOCK_UN)
        deadline = time.monotonic() + timeout
        while True:
            try:
                acquire()
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise OSError('历史文件正在使用，请稍后重试')
                time.sleep(0.05)
        try:
            yield
        finally:
            release()


def atomic_write(path, text):
    descriptor, name = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='\n') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class HistoryStore:
    def __init__(self, config_path):
        self.path = Path(config_path).parent / 'history.jsonl'
        self.lock_path = self.path.with_suffix('.lock')

    def _read(self):
        if not self.path.exists():
            return []
        records = []
        damaged = 0
        with self.path.open('r', encoding='utf-8', errors='replace') as stream:
            for index, line in enumerate(stream):
                try:
                    record = json.loads(line)
                    if not isinstance(record, dict) or not all(
                        isinstance(record.get(key), str) for key in ('command', 'time', 'status')
                    ):
                        raise ValueError('invalid record')
                    record.pop('id', None)
                    if not isinstance(record.get('_key'), str):
                        # 无键的已有文本行生成稳定内部标识，不对用户暴露序号。
                        record['_key'] = str(uuid5(NAMESPACE_URL, f'{self.path}:{index}:{line}'))
                    records.append(record)
                except (ValueError, TypeError):
                    damaged += 1
        if damaged:
            warning(f'历史文件有 {damaged} 条损坏记录，已跳过；下次更新会移除损坏行')
        return records

    def _write(self, records):
        atomic_write(self.path, ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in records))

    def read(self):
        with file_lock(self.lock_path):
            return [{key: value for key, value in row.items() if key != '_key'} for row in self._read()]

    def append(self, record):
        with file_lock(self.lock_path):
            records = self._read()
            row = {key: value for key, value in record.items() if key not in {'id', '_key'}}
            row['_key'] = str(uuid4())
            records.append(row)
            records.sort(key=lambda item: item.get('started_at', 0))
            self._write(records[-LIMIT:])

    def remove(self, predicate, confirm):
        with file_lock(self.lock_path):
            keys = {row['_key'] for row in self._read() if predicate(row)}
        # 确认期间不持锁；后续新记录不会被本次清理匹配。
        if not keys or not confirm(len(keys)):
            return 0
        with file_lock(self.lock_path):
            records = self._read()
            remaining = [row for row in records if row['_key'] not in keys]
            self._write(remaining)
            return len(records) - len(remaining)
