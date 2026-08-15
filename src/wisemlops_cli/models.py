"""CLI 使用的数据模型。"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Profile:
    name: str
    api_endpoint: str
    output_format: str = "table"
    verify_ssl: Optional[bool] = None

    @property
    def base_url(self) -> str:
        parsed = urlsplit(self.api_endpoint)
        return f"{parsed.scheme}://{parsed.netloc}"


@dataclass(frozen=True)
class Credentials:
    profile: str
    cookie: str
    csrftoken: str
    username: str
    acquired_at: float
    expires_at: float

    @classmethod
    def create(
        cls,
        profile: str,
        cookie: str,
        csrftoken: str,
        username: str,
        ttl_seconds: int,
    ) -> "Credentials":
        acquired_at = time.time()
        return cls(
            profile=profile,
            cookie=cookie,
            csrftoken=csrftoken,
            username=username,
            acquired_at=acquired_at,
            expires_at=acquired_at + ttl_seconds,
        )

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Credentials":
        return cls(
            profile=str(value["profile"]),
            cookie=str(value["cookie"]),
            csrftoken=str(value["csrftoken"]),
            username=str(value.get("username", "")),
            acquired_at=float(value["acquired_at"]),
            expires_at=float(value["expires_at"]),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def is_expired(self, now: float = None) -> bool:
        current = time.time() if now is None else now
        return current >= self.expires_at

    def remaining_seconds(self, now: float = None) -> int:
        current = time.time() if now is None else now
        return max(0, int(self.expires_at - current))
