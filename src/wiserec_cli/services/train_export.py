"""通过平台认证连接流式导出训练任务配置。"""

from __future__ import annotations

import os
import re
import tempfile
from email.message import Message
from pathlib import Path
from typing import Callable, Optional

from ..client import PlatformClient
from ..errors import ApiError, BusinessError


def _filename(disposition: str, task_id: str) -> str:
    message = Message()
    message["Content-Disposition"] = disposition
    fallback_id = re.sub(r"[^A-Za-z0-9_-]", "_", task_id) or "task"
    fallback = f"{fallback_id}.yaml"
    name = message.get_filename() or fallback
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", name).strip(" .")
    if not name or name.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        name = fallback
    return name


def export_config(
    client: PlatformClient, task_id: str, destination: Optional[Path] = None,
    *, progress: Optional[Callable[[int, Optional[int]], None]] = None,
) -> tuple[Path, int]:
    task_id = task_id.strip()
    if not task_id:
        raise ValueError("taskId 不能为空")
    if not client.business_id:
        raise BusinessError("尚未选择租户或团队，请运行 ml business use")
    temporary: Optional[Path] = None
    try:
        with client.stream(
            "GET", "/ai/backend/mtp/traintask/export",
            params={"taskId": task_id, "businessId": client.business_id},
        ) as response:
            if "json" in response.headers.get("content-type", "").lower():
                raise ApiError("导出接口返回 JSON，未收到配置文件")
            target = destination or Path(_filename(
                response.headers.get("content-disposition", ""), task_id,
            ))
            target = target.expanduser().absolute()
            if not target.parent.is_dir():
                raise ApiError(f"目标目录不存在：{target.parent}")
            length = response.headers.get("content-length", "")
            total = int(length) if length.isdigit() else None
            received = 0
            with tempfile.NamedTemporaryFile(
                dir=target.parent, prefix=".ml-train-export-", suffix=".part", delete=False,
            ) as output:
                temporary = Path(output.name)
                if progress:
                    progress(0, total)
                for chunk in response.iter_bytes():
                    output.write(chunk)
                    received += len(chunk)
                    if progress:
                        progress(received, total)
                if total is not None and received != total:
                    raise ApiError("配置下载不完整：实际大小与 Content-Length 不一致")
                output.flush()
                os.fsync(output.fileno())
            candidate = target
            number = 0
            while True:
                try:
                    os.link(temporary, candidate)
                    return candidate, received
                except FileExistsError:
                    number += 1
                    candidate = target.with_name(f"{target.stem} ({number}){target.suffix}")
    except OSError as exc:
        raise ApiError(f"配置保存失败：{exc.strerror}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
