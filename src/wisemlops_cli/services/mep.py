"""MEP 接口。"""

from __future__ import annotations

from typing import Any

from ..client import PlatformClient


class MepService:
    def __init__(self, client: PlatformClient):
        self.client = client

    def query_config(self, key: str) -> Any:
        return self.client.request(
            "POST",
            "/ai/backend/mep/config/queryConfig",
            json_body={"key": key},
        )
