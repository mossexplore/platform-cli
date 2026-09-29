"""与业务无关的统一 HTTP 客户端。"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Dict, Mapping, Optional

import httpx

from .business import BusinessSelection
from .client_metadata import client_headers, check_version_response
from .errors import ApiError, AuthenticationError
from .models import Credentials, Profile


class PlatformClient:
    def __init__(
        self,
        profile: Profile,
        credentials: Credentials,
        timeout_ms: int,
        retry_times: int,
        verify_ssl: bool,
        transport: Optional[httpx.BaseTransport] = None,
        business_selection: Optional[BusinessSelection] = None,
        on_platform_success: Optional[Callable[[], None]] = None,
    ):
        selected_transport = transport or httpx.HTTPTransport(
            retries=retry_times,
            verify=verify_ssl,
        )
        headers = {
            "cookie": credentials.cookie,
            "csrftoken": credentials.csrftoken,
            "content-type": "application/json",
            "referer": profile.api_endpoint,
        }
        if business_selection is not None:
            headers["ai-businessId"] = business_selection.business_id
            headers["businessid"] = business_selection.business_id
        self._username = credentials.username
        self._business_selection = business_selection
        self._platform_url = httpx.URL(profile.base_url)
        self._on_platform_success = on_platform_success
        self._client = httpx.Client(
            base_url=profile.base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout_ms / 1000),
            transport=selected_transport,
            follow_redirects=False,
        )

    def __enter__(self) -> "PlatformClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    @property
    def business_id(self) -> str:
        """返回当前已校验业务上下文中的 businessId。"""
        if self._business_selection is None:
            return ""
        return self._business_selection.business_id

    @property
    def username(self) -> str:
        """返回当前认证信息中的登录账号。"""
        return self._username

    @staticmethod
    def _request_headers(headers):
        merged = httpx.Headers(headers or {})
        generated = client_headers()
        if 'x-request-id' in merged:
            generated.pop('X-Request-ID')
        merged.update(generated)
        return merged

    def _mark_platform_response(self, response: httpx.Response) -> None:
        """外部下载地址和其他服务的响应不能延长平台认证有效期。"""
        url = response.request.url
        if (url.scheme, url.host, url.port) == (
            self._platform_url.scheme, self._platform_url.host, self._platform_url.port,
        ) and self._on_platform_success is not None:
            self._on_platform_success()

    def request(
        self,
        method: str,
        path: str,
        json_body: Optional[Dict[str, Any]] = None,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
    ) -> Any:
        try:
            response = self._client.request(
                method,
                path,
                json=json_body,
                params=params,
                headers=self._request_headers(headers),
            )
        except httpx.HTTPError as exc:
            raise ApiError(f"请求失败: {exc}") from exc

        check_version_response(response)
        if response.status_code in {401, 403, 419, 440}:
            raise AuthenticationError(
                f"认证信息已被服务端拒绝，HTTP {response.status_code}"
            )
        if 300 <= response.status_code < 400:
            raise AuthenticationError(
                "接口请求被重定向，认证信息可能已经失效，"
                f"HTTP {response.status_code}"
            )
        if not response.is_success:
            raise ApiError(
                f"接口请求失败，HTTP {response.status_code}: {response.text[:500]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ApiError(f"接口没有返回有效 JSON: {response.text[:500]}") from exc
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict) or "code" not in result or (
            type(result["code"]) is int and result["code"] == 0
        ):
            self._mark_platform_response(response)
        return payload

    @contextmanager
    def stream(self, method: str, path: str, *, params: Optional[Mapping[str, Any]] = None):
        """以当前登录和业务请求头读取平台文件响应。"""
        try:
            with self._client.stream(
                method, path, params=params,
                headers=self._request_headers({"Accept-Encoding": "identity"}),
            ) as response:
                # 流式成功响应尚未读取，response.json() 会触发 ResponseNotRead。
                # 仅对错误或 JSON 响应读取包装体，以保留版本准入诊断。
                if not response.is_success or "json" in response.headers.get("content-type", "").lower():
                    response.read()
                    check_version_response(response)
                if response.status_code in {401, 403, 419, 440}:
                    raise AuthenticationError(f"认证信息已被服务端拒绝，HTTP {response.status_code}")
                if 300 <= response.status_code < 400:
                    raise AuthenticationError(f"接口请求被重定向，HTTP {response.status_code}")
                if not response.is_success:
                    raise ApiError(f"接口请求失败，HTTP {response.status_code}")
                yield response
                self._mark_platform_response(response)
        except httpx.HTTPError as exc:
            raise ApiError(f"下载请求失败: {exc}") from exc
