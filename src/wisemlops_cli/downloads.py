"""HTTPS 文件下载，不继承平台认证信息。"""

from __future__ import annotations

import os
import re
import tempfile
from email.message import Message
from pathlib import Path
from typing import Callable, Optional, Tuple

import httpx

from .errors import ApiError


def https_url(value: object) -> httpx.URL:
    try:
        url = httpx.URL(value) if isinstance(value, str) else None
        if url is None or url.scheme != "https" or not url.host or url.userinfo:
            raise ValueError()
        return url
    except (ValueError, httpx.InvalidURL):
        raise ApiError("下载地址为空或不是有效的 HTTPS 地址") from None


def download_filename(disposition: str, job_id: str) -> str:
    message = Message()
    message["Content-Disposition"] = disposition
    filename = message.get_filename() or f"{job_id}-logs"
    filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    filename = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", filename).strip(" .")
    if not filename:
        filename = "download-logs"
    if filename.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        filename = "_" + filename
    return filename


def download_file(
    url: str, job_id: str, destination: Optional[Path] = None,
    *, progress: Optional[Callable[[int, Optional[int]], None]] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> Tuple[Path, int]:
    """流式下载至同目录临时文件，完成后以不覆盖方式发布。"""
    current = https_url(url)
    temporary = None
    try:
        with httpx.Client(verify=True, timeout=60, follow_redirects=False,
                          transport=transport, headers={"Accept-Encoding": "identity"}) as client:
            for redirect in range(6):
                client.cookies.clear()
                with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect == 5 or not response.headers.get("location"):
                            raise ApiError("日志下载失败：重定向次数过多或缺少跳转地址")
                        try:
                            current = https_url(str(current.join(response.headers["location"])))
                        except httpx.InvalidURL:
                            raise ApiError("日志下载失败：无效的跳转地址") from None
                        continue
                    if response.status_code != 200:
                        raise ApiError(f"日志下载失败：HTTP {response.status_code}")
                    target = destination if destination is not None else Path(
                        download_filename(response.headers.get("content-disposition", ""), job_id)
                    )
                    target = target.expanduser().absolute()
                    if os.path.lexists(target):
                        raise ApiError(f"目标文件已存在：{target}")
                    if not target.parent.is_dir():
                        raise ApiError(f"目标目录不存在：{target.parent}")
                    length = response.headers.get("content-length", "")
                    total = int(length) if length.isdigit() else None
                    received = 0
                    with tempfile.NamedTemporaryFile(
                        dir=target.parent, prefix=".ml-logs-", suffix=".part", delete=False,
                    ) as output:
                        temporary = Path(output.name)
                        if progress:
                            progress(received, total)
                        for chunk in response.iter_raw():
                            output.write(chunk)
                            received += len(chunk)
                            if progress:
                                progress(received, total)
                        if total is not None and received != total:
                            raise ApiError("日志下载不完整：实际大小与 Content-Length 不一致")
                        output.flush()
                        os.fsync(output.fileno())
                    # 同目录硬链接使完整文件一次性可见，目标竞争创建时也绝不覆盖。
                    os.link(temporary, target)
                    return target, received
    except httpx.HTTPError:
        # 异常通常包含签名 URL，不向用户回显。
        raise ApiError("日志下载失败：网络连接、证书校验、超时或传输异常，请重试") from None
    except OSError as exc:
        raise ApiError(f"日志保存失败：{exc.strerror}") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    raise ApiError("日志下载失败")
