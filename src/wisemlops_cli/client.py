"""与业务无关的统一 HTTP 客户端。"""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

import httpx

from .business import BusinessSelection
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
        self._username = credentials.username
        self._business_selection = business_selection
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
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise ApiError(f"请求失败: {exc}") from exc

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
            return response.json()
        except ValueError as exc:
            raise ApiError(f"接口没有返回有效 JSON: {response.text[:500]}") from exc
