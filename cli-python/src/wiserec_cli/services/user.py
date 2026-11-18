"""用户接口。"""

from __future__ import annotations

from typing import Any

from ..client import PlatformClient


class UserService:
    def __init__(self, client: PlatformClient):
        self.client = client

    def info(self) -> Any:
        return self.client.request("GET", "/ai/user/info")
