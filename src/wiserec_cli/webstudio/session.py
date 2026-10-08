"""恢复 HTTP Cookie 的完整作用域，并在同一代连接内更新会话。"""
from http.cookiejar import Cookie
import sys

from ..errors import ConfigError


def cookie_records(jar):
    result = []
    for cookie in jar:
        value = vars(cookie).copy()
        value['rest'] = value.pop('_rest')
        result.append(value)
    return result


class CachedSession:
    def __init__(self, cache, key, entry):
        self.cache, self.key, self.entry = cache, key, entry

    def restore(self, client, entry):
        try:
            cookies = [Cookie(**value) for value in entry['cookies']]
        except (TypeError, ValueError, KeyError):
            return False
        client.http.cookies.clear()
        for cookie in cookies:
            client.http.cookies.jar.set_cookie(cookie)
        return entry.get('session_ready') is True

    def prepare(self, client, bootstrap):
        with self.cache.locked():
            entry = self.cache.read().get(self.key)
            if entry and entry['generation'] == self.entry['generation'] and self.restore(client, entry):
                return
            bootstrap()
            self.cache.save_session(self.key, self.entry['generation'], cookie_records(client.http.cookies.jar))

    def save(self, client):
        try:
            with self.cache.locked():
                self.cache.save_session(self.key, self.entry['generation'], cookie_records(client.http.cookies.jar))
        except (OSError, ConfigError):
            # 缓存更新失败不能把已完成的远端写操作报告为失败。
            print('警告：无法更新 Web Studio 会话缓存；本次请求已完成', file=sys.stderr)

    def invalidate(self):
        self.cache.invalidate(self.key, self.entry['generation'])
