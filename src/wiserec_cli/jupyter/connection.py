"""当前环境的 Jupyter Token 认证与 HTTP/WebSocket 传输。"""
from __future__ import annotations

import os
import json
import ssl
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

import httpx
import websocket

from ..access import check_access
from ..business import BusinessStore
from ..errors import MlError


class JupyterError(MlError):
    pass


@dataclass(frozen=True)
class Connection:
    url: str
    token: str = field(repr=False)
    business_id: str
    kernel: str = "python3"
    verify: Any = True
    timeout: float = 30
    studio_id: str = ""


def from_runtime(runtime, studio_id=None, report=None) -> Connection:
    settings = runtime.config.jupyter_settings()
    mode = settings.get("mode", "direct")
    if mode == "webstudio":
        from ..webstudio.resolve import resolve
        return resolve(runtime, studio_id, report=report)
    if mode != "direct":
        raise JupyterError("jupyter.mode 仅支持 direct 或 webstudio")
    if studio_id:
        raise JupyterError("--studio-id 需要 jupyter.mode=webstudio")
    profile = runtime.config.current_profile()
    url = settings.get("server_url", profile.api_endpoint)
    parts = urlsplit(url)
    if (parts.scheme not in {"http", "https"} or not parts.hostname
            or parts.username or parts.password or parts.query or parts.fragment):
        raise JupyterError("Jupyter server_url 须为不含凭据、查询参数或片段的 HTTP(S) 地址")
    base = runtime.config.path.parent

    def local_path(value):
        path = Path(value).expanduser()
        return path if path.is_absolute() else base / path

    token = os.environ.get(settings.get("token_env", "ML_JUPYTER_TOKEN"), "")
    if not token and settings.get("token_file"):
        token = local_path(settings["token_file"]).read_text(encoding="utf-8").strip()
    if not token or any(c in token for c in "\r\n"):
        raise JupyterError("请设置当前环境的 Jupyter token_env 或 token_file；不支持匿名连接")
    store = (BusinessStore(local_path(settings["business_file"]))
             if settings.get("business_file") else runtime.business)
    username = ""
    credentials = None
    if runtime.config.access_control.get("enabled"):
        credentials = runtime.auth.ensure_credentials()
        username = credentials.username
    selection = store.require_selection(profile.name, username)
    stored = json.loads(store.path.read_text(encoding="utf-8"))
    business_id = stored["profiles"][profile.name]["selected"].get("businessId")
    if (not isinstance(business_id, str) or not business_id
            or business_id != selection.business_id or any(c in business_id for c in "\r\n")):
        raise JupyterError("当前环境 selected.businessId 无效")
    if credentials is not None:
        check_access(runtime.config.access_control, profile, credentials, selection,
                     command=runtime.invocation_command, full_command=runtime.full_command)
    verify = runtime.config.verify_ssl
    if settings.get("ca_file"):
        verify = ssl.create_default_context(cafile=str(local_path(settings["ca_file"])))
    return Connection(url.rstrip("/") + "/", token, business_id,
                      settings.get("kernel", "python3"), verify,
                      runtime.config.timeout_ms / 1000)


def remote_path(value: str) -> str:
    """Contents 路径相对服务器根目录，拒绝歧义和越界。"""
    if value.startswith("/") or "\\" in value or "\x00" in value:
        raise JupyterError("远程路径必须相对 Jupyter 根目录")
    parts = value.split("/")
    if ".." in parts:
        raise JupyterError("远程路径不可包含 ..")
    return "/".join(p for p in parts if p and p != ".")


class JupyterClient:
    def __init__(self, connection: Connection, transport=None):
        self.connection = connection
        self.headers = {"Authorization": "token " + connection.token,
                        "businessid": connection.business_id}
        self.http = httpx.Client(base_url=connection.url, headers=self.headers,
                                 timeout=connection.timeout, verify=connection.verify,
                                 follow_redirects=False, trust_env=False, transport=transport)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.http.close()

    def request(self, method, path, body=None):
        try:
            response = self.http.request(method, path, json=body)
        except httpx.HTTPError as exc:
            raise JupyterError("Jupyter 网络请求失败；未自动重试") from exc
        if response.status_code in {401, 403}:
            raise JupyterError(f"Jupyter {method} {path.split(chr(63))[0]} 认证或权限失败（HTTP {response.status_code}）；请检查动态凭据与接口权限")
        if not response.is_success:
            raise JupyterError(f"Jupyter 请求失败（HTTP {response.status_code}）；请检查地址、路径和服务能力")
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise JupyterError("Jupyter 未返回 JSON，可能连接到了登录页或错误代理路径") from exc

    def socket(self, path):
        parts = urlsplit(self.connection.url + path)
        url = urlunsplit(("wss" if parts.scheme == "https" else "ws",
                          parts.netloc, parts.path, parts.query, ""))
        verify = self.connection.verify
        sslopt = ({"context": verify} if isinstance(verify, ssl.SSLContext)
                  else {} if verify else {"cert_reqs": ssl.CERT_NONE, "check_hostname": False})
        try:
            socket = websocket.create_connection(
                url, header=self.headers, timeout=self.connection.timeout,
                origin=urlunsplit((urlsplit(self.connection.url).scheme, parts.netloc, "", "", "")),
                sslopt=sslopt, http_no_proxy=[parts.hostname], enable_multithread=True,
                redirect_limit=0,
            )
            if socket.getstatus() != 101:
                socket.close()
                raise JupyterError("Jupyter WebSocket 被重定向或未完成协议升级")
            return socket
        except Exception as exc:
            raise JupyterError("Jupyter WebSocket 连接失败；请检查 Token 和代理 Upgrade 配置") from exc

    def contents(self, path):
        return "api/contents/" + quote(remote_path(path), safe="/")

    def save_notebook(self, path, notebook):
        return self.request("PUT", self.contents(path),
                            {"type": "notebook", "format": "json", "content": notebook})

    def ensure_directory(self, path):
        current = []
        for part in remote_path(path).split("/"):
            if not part:
                continue
            current.append(part)
            endpoint = self.contents("/".join(current))
            # PUT directory is idempotent on Jupyter's Contents API.
            self.request("PUT", endpoint, {"type": "directory"})
