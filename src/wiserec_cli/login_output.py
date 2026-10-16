"""登录过程的单行进度与环境别名校验。"""

from .errors import AuthenticationError
from .output import console


class LoginProgress:
    def __init__(self, alias):
        self.alias = (alias or "").strip()
        if not self.alias:
            raise AuthenticationError("请先在 config.json 中为当前环境配置非空的 alias 后再登录")
        self.status = None

    def __enter__(self):
        console.print(f"正在登录【{self.alias}】", markup=False)
        message = "正在打开登录页面…"
        if console.is_terminal and not console.is_dumb_terminal:
            self.status = console.status(message, spinner="dots")
            self.status.start()
        else:
            console.print(message)
        return self

    def update(self, message):
        if self.status is not None:
            self.status.update(message)

    def stop(self):
        if self.status is not None:
            self.status.stop()
            self.status = None

    def __exit__(self, *_):
        self.stop()
