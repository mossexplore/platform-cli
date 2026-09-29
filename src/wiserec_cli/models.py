"""CLI 使用的数据模型。"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from urllib.parse import urlsplit


BEIJING_TIMEZONE = timezone(timedelta(hours=8))


def _read_credential_time(value: Any) -> float:
    """读取旧版时间戳或带时区的可读时间。"""
    if isinstance(value, str):
        try:
            moment = datetime.fromisoformat(value)
        except ValueError:
            return float(value)
        if moment.tzinfo is None:
            raise ValueError("认证时间缺少时区")
        return moment.timestamp()
    return float(value)


def _format_credential_time(value: float) -> str:
    return datetime.fromtimestamp(value, BEIJING_TIMEZONE).isoformat(
        sep=" ", timespec="seconds"
    )


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
    cn_name: str = ""
    department: str = ""
    business_id: str = ""

    @classmethod
    def create(
        cls,
        profile: str,
        cookie: str,
        csrftoken: str,
        username: str,
        ttl_seconds: int,
        cn_name: str = "",
        department: str = "",
        business_id: str = "",
    ) -> "Credentials":
        acquired_at = time.time()
        return cls(
            profile=profile,
            cookie=cookie,
            csrftoken=csrftoken,
            username=username,
            acquired_at=acquired_at,
            expires_at=acquired_at + ttl_seconds,
            cn_name=cn_name,
            department=department,
            business_id=business_id,
        )

    @classmethod
    def from_dict(cls, value: Dict[str, Any]) -> "Credentials":
        return cls(
            profile=str(value["profile"]),
            cookie=str(value["cookie"]),
            csrftoken=str(value["csrftoken"]),
            username=str(value.get("username", "")),
            acquired_at=_read_credential_time(value["acquired_at"]),
            expires_at=_read_credential_time(value["expires_at"]),
            cn_name=str(value.get("cn_name", "")),
            department=str(value.get("department", "")),
            business_id=str(value.get("business_id", "")),
        )

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["acquired_at"] = _format_credential_time(self.acquired_at)
        data["expires_at"] = _format_credential_time(self.expires_at)
        return data

    def is_expired(self, now: float = None) -> bool:
        current = time.time() if now is None else now
        return current >= self.expires_at

    def remaining_seconds(self, now: float = None) -> int:
        current = time.time() if now is None else now
        return max(0, int(self.expires_at - current))
