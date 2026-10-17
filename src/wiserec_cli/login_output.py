"""登录过程的单行进度与环境别名校验。"""

import os
from contextlib import contextmanager

from . import messages as msg
from .errors import AuthenticationError
from .output import console

class LoginProgress:
    def __init__(self, alias):
        self.alias = (alias or "").strip()
        if not self.alias:
            raise AuthenticationError("请先在 config.json 中为当前环境配置非空的 alias 后再登录")
        self.status = None

    def __enter__(self):
        msg.info(f"正在登录【{self.alias}】")
        message = "正在打开登录页面…"
        if msg.error_console.is_terminal and not msg.error_console.is_dumb_terminal:
            self.status = msg.error_console.status(msg.render(message), spinner="dots")
            self.status.start()
        else:
            msg.info(message)
        return self

    def update(self, message):
        if self.status is not None:
            self.status.update(msg.render(message))

    def stop(self):
        if self.status is not None:
            self.status.stop()
            self.status = None

    def __exit__(self, *_):
        self.stop()


@contextmanager
def quiet_node_warnings():
    """Let the login driver inherit quiet warnings without changing TLS settings."""
    previous = os.environ.get('NODE_NO_WARNINGS')
    os.environ['NODE_NO_WARNINGS'] = '1'
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop('NODE_NO_WARNINGS', None)
        else:
            os.environ['NODE_NO_WARNINGS'] = previous
