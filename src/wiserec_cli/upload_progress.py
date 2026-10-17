"""为同步 Multipart 文件流提供终端发送进度。"""

import sys
from contextlib import contextmanager

from rich.progress import Progress, BarColumn, DownloadColumn

from . import messages as msg


class TrackedFile:
    def __init__(self, content, progress, task):
        self.content = content
        self.progress = progress
        self.task = task

    def read(self, size=-1):
        chunk = self.content.read(size)
        self.progress.update(self.task, completed=self.content.tell())
        return chunk

    def __getattr__(self, name):
        return getattr(self.content, name)


@contextmanager
def upload_content(file_path):
    with file_path.open('rb') as content, Progress(
        msg.MessageColumn(), BarColumn(), DownloadColumn(),
        console=msg.error_console, disable=not sys.stderr.isatty(),
    ) as progress:
        task = progress.add_task('发送文件', total=file_path.stat().st_size)
        yield TrackedFile(content, progress, task)
