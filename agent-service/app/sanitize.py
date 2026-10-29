"""Normalize serialization types and display timestamps without redacting content."""

import re
from datetime import datetime, timezone, timedelta
from decimal import Decimal


def clean(value):
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, str):
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
