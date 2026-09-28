"""从独立 HTTPS 地址安全下载算法仓文件。"""

from __future__ import annotations

import os
import re
import tempfile
from email.message import Message
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import unquote

import httpx

from .downloads import https_url
from .errors import ApiError


def _filename(disposition: str, url: httpx.URL, algorithm_id: str) -> str:
    message = Message()
    message["Content-Disposition"] = disposition
    fallback = re.sub(r"[^A-Za-z0-9_-]", "_", algorithm_id) or "algorithm"
    name = message.get_filename() or unquote(url.path.rsplit("/", 1)[-1]) or fallback
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', "_", name).strip(" .")
    if not name or name.split(".")[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        return fallback
    return name


def download_algorithm(
    url: str, algorithm_id: str, destination: Optional[Path] = None,
    *, verify_ssl: bool = True,
    progress: Optional[Callable[[int, Optional[int]], None]] = None,
    transport: Optional[httpx.BaseTransport] = None,
) -> tuple[Path, int]:
    current = https_url(url)
    temporary: Optional[Path] = None
    try:
        with httpx.Client(
            verify=verify_ssl, timeout=60, follow_redirects=False,
            transport=transport, headers={"Accept-Encoding": "identity"},
        ) as client:
            for redirect in range(6):
                client.cookies.clear()
                with client.stream("GET", current) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if redirect == 5 or not location:
                            raise ApiError("算法仓下载失败：跳转次数过多或缺少地址")
                        try:
                            current = https_url(str(current.join(location)))
                        except httpx.InvalidURL:
                            raise ApiError("算法仓下载失败：跳转地址无效") from None
                        continue
                    if response.status_code != 200:
                        raise ApiError(f"算法仓下载失败：HTTP {response.status_code}")
                    if "json" in response.headers.get("content-type", "").lower():
                        raise ApiError("算法仓下载失败：下载地址返回 JSON 而不是文件")
                    target = destination or Path(_filename(
                        response.headers.get("content-disposition", ""), current, algorithm_id,
                    ))
                    target = target.expanduser().absolute()
                    if not target.parent.is_dir():
                        raise ApiError(f"目标目录不存在：{target.parent}")
                    length = response.headers.get("content-length", "")
                    total = int(length) if length.isdigit() else None
                    received = 0
                    with tempfile.NamedTemporaryFile(
                        dir=target.parent, prefix=".ml-algorithm-", suffix=".part", delete=False,
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
                            raise ApiError("算法仓下载不完整：实际大小与 Content-Length 不一致")
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
    except httpx.HTTPError as exc:
        raise ApiError(f"算法仓下载失败：网络异常（{type(exc).__name__}）") from None
    except OSError as exc:
        raise ApiError(f"算法仓保存失败：{exc.strerror}") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    raise ApiError("算法仓下载失败")
