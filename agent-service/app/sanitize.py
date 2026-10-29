"""Bounded tool content and redaction before model, database or browser output."""

import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal

SECRET_KEY = re.compile(
    r"cookie|csrf|token|password|secret|authorization|credential|signature", re.I
)
SECRET_TEXT = re.compile(
    r"(?i)\b(cookie|csrftoken|authorization|api[_-]?key|password|token|secret)\s*[:=]\s*[^\s,;]+"
)
URL_QUERY = re.compile(r"(https?://[^\s?]+)\?[^\s]+")


def clean(value, secrets=()):
    if isinstance(value, dict):
        return {
            str(k): clean(v, secrets)
            for k, v in value.items()
            if not SECRET_KEY.search(str(k))
        }
    if isinstance(value, (list, tuple)):
        return [clean(v, secrets) for v in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, str):
        for secret in secrets:
            if secret:
                value = value.replace(secret, "[已隐藏]")
        value = SECRET_TEXT.sub(lambda m: m.group(1) + "=[已隐藏]", value)
        value = URL_QUERY.sub(r"\1?[已隐藏]", value)
        if re.fullmatch(r"\d{4}-\d\d-\d\dT[\d:.]+(?:Z|[+-]\d\d:\d\d)", value):
            try:
                return (
                    datetime.fromisoformat(value.replace("Z", "+00:00"))
                    .astimezone(timezone(timedelta(hours=8)))
                    .strftime("%Y-%m-%d %H:%M:%S")
                )
            except ValueError:
                pass
        return value
    return value
