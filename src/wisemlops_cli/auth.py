"""通过 Edge 登录并管理有有效期的本地认证信息。"""

from __future__ import annotations

import json
import shutil
import time
from collections import deque
from dataclasses import replace
from pathlib import Path
from typing import Any, Deque, Dict, Optional

from .business import BusinessStore, parse_business_list
from .config import ConfigManager
from .credentials import CredentialStore
from .errors import AuthenticationError, CredentialError
from .models import Credentials, Profile


def _parse_user_info(response_body: Any) -> Optional[Dict[str, str]]:
    if not isinstance(response_body, dict):
        return None
    result = response_body.get("result")
    if not isinstance(result, dict) or result.get("code") != 0:
        return None
    return {
        "username": str(result.get("username") or ""),
        "cn_name": str(result.get("cnName") or ""),
        "department": str(result.get("department") or ""),
    }


def _wait_for_edge(page: Any, message: str) -> None:
    print(message)
    try:
        page.wait_for_event("close", timeout=0)
    except Exception:
        pass


class BrowserAuthenticator:
    def __init__(
        self,
        store: CredentialStore,
        business_store: Optional[BusinessStore] = None,
    ):
        self.store = store
        self.business_store = business_store

    def login(
        self,
        profile: Profile,
        timeout_ms: int,
        ttl_seconds: int,
        user_data_dir: Path,
        browser_channel: str,
        session_probe_timeout_ms: int,
        login_timeout_ms: int,
        show_secrets: bool = False,
    ) -> Credentials:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise AuthenticationError(
                "未安装 playwright，请运行: py -m pip install playwright"
            ) from exc

        user_info_url = f"{profile.base_url}/ai/user/info"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                channel=browser_channel,
                headless=False,
            )
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(timeout_ms)
            captured_headers: Deque[Dict[str, str]] = deque()

            def capture_auth_request(request: Any) -> None:
                request_url = request.url.split("?", 1)[0].rstrip("/")
                if request_url != user_info_url.rstrip("/"):
                    return
                try:
                    headers = request.all_headers()
                except Exception:
                    return
                if self._find_csrftoken(headers):
                    captured_headers.append(headers)

            context.on("request", capture_auth_request)

            try:
                print(f"当前环境: {profile.name}")
                print(f"Edge Profile: {user_data_dir}")
                print(f"正在打开: {profile.api_endpoint}")
                page.goto(
                    profile.api_endpoint,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                credentials = self._wait_for_credentials(
                    context=context,
                    profile=profile,
                    user_info_url=user_info_url,
                    ttl_seconds=ttl_seconds,
                    request_timeout_ms=timeout_ms,
                    wait_timeout_ms=min(
                        session_probe_timeout_ms,
                        timeout_ms,
                    ),
                    captured_headers=captured_headers,
                )
                reused_session = credentials is not None

                if credentials is None:
                    print("未发现有效的持久登录会话，需要用户完成登录。")
                    print("正在等待登录成功...")
                    credentials = self._wait_for_credentials(
                        context=context,
                        profile=profile,
                        user_info_url=user_info_url,
                        ttl_seconds=ttl_seconds,
                        request_timeout_ms=timeout_ms,
                        wait_timeout_ms=login_timeout_ms,
                        captured_headers=captured_headers,
                    )
                if credentials is None:
                    raise AuthenticationError(
                        f"等待登录超时（{login_timeout_ms // 1000} 秒），仍未获取到"
                        "有效的 Cookie、csrftoken 和用户信息"
                    )

                credentials = replace(
                    credentials,
                    business_id=self._read_local_storage(
                        context, "ai-businessId"
                    ),
                )
                business_warning = self._refresh_business_catalog(
                    context, profile, credentials
                )
                self.store.save(credentials)
                source = "持久 Edge 会话" if reused_session else "用户登录"
                print(
                    f"已通过{source}刷新认证信息，有效期 {ttl_seconds} 秒"
                )
                print(f"账号: {credentials.username}")
                print(f"中文名: {credentials.cn_name}")
                print(f"部门: {credentials.department}")
                print(f"租户: {credentials.business_id}")
                if business_warning:
                    print(f"警告: {business_warning}")
                if show_secrets:
                    print(f"cookie: {credentials.cookie}")
                    print(f"csrftoken: {credentials.csrftoken}")
                print("认证成功，正在自动关闭 Edge...")
                context.close()
                return credentials
            except Exception as exc:
                if page.is_closed():
                    raise
                print(f"登录失败: {exc}")
                _wait_for_edge(
                    page,
                    "Edge 将保持打开；请检查页面，完成后手动关闭 Edge。",
                )
                raise

    @staticmethod
    def _read_local_storage(context: Any, key: str) -> str:
        for page in reversed(context.pages):
            if page.is_closed():
                continue
            try:
                value = page.evaluate(
                    f"() => localStorage.getItem({json.dumps(key)})"
                )
            except Exception:
                continue
            if value is not None:
                return str(value)
        return ""

    def _refresh_business_catalog(
        self,
        context: Any,
        profile: Profile,
        credentials: Credentials,
    ) -> str:
        if self.business_store is None:
            return ""
        raw_business_list = self._read_local_storage(
            context, "ai-businessList"
        )
        if not raw_business_list:
            return (
                "未读取到 ai-businessList，请运行 ml business refresh 后重试"
            )
        try:
            departments = parse_business_list(raw_business_list)
            self.business_store.refresh(
                profile=profile.name,
                username=credentials.username,
                departments=departments,
                browser_business_id=credentials.business_id,
            )
        except Exception as exc:
            return f"业务目录刷新失败: {exc}"
        return ""

    def _wait_for_credentials(
        self,
        context: Any,
        profile: Profile,
        user_info_url: str,
        ttl_seconds: int,
        request_timeout_ms: int,
        wait_timeout_ms: int,
        captured_headers: Deque[Dict[str, str]],
    ) -> Optional[Credentials]:
        deadline = time.monotonic() + wait_timeout_ms / 1000
        while time.monotonic() < deadline:
            while captured_headers:
                credentials = self._credentials_from_headers(
                    context=context,
                    profile=profile,
                    user_info_url=user_info_url,
                    ttl_seconds=ttl_seconds,
                    request_timeout_ms=request_timeout_ms,
                    captured_headers=captured_headers.popleft(),
                )
                if credentials is not None:
                    return credentials

            open_pages = [page for page in context.pages if not page.is_closed()]
            if not open_pages:
                raise AuthenticationError("Edge 已关闭，未能完成登录认证")
            remaining_ms = int((deadline - time.monotonic()) * 1000)
            if remaining_ms <= 0:
                break
            open_pages[-1].wait_for_timeout(min(250, remaining_ms))
        return None

    @staticmethod
    def _find_csrftoken(headers: Dict[str, str]) -> str:
        normalized = {str(key).lower(): value for key, value in headers.items()}
        return str(
            normalized.get("csrftoken")
            or normalized.get("x-csrftoken")
            or normalized.get("x-csrf-token")
            or ""
        )

    def _credentials_from_headers(
        self,
        context: Any,
        profile: Profile,
        user_info_url: str,
        ttl_seconds: int,
        request_timeout_ms: int,
        captured_headers: Dict[str, str],
    ) -> Optional[Credentials]:

        cookies = context.cookies(user_info_url)
        cookie = "; ".join(
            f"{item['name']}={item['value']}" for item in cookies
        )
        csrftoken = self._find_csrftoken(captured_headers)
        if not cookie or not csrftoken:
            return None

        try:
            response = context.request.get(
                user_info_url,
                headers={
                    "cookie": cookie,
                    "csrftoken": csrftoken,
                    "referer": profile.api_endpoint,
                },
                timeout=request_timeout_ms,
            )
            response_text = response.text()
        except Exception:
            return None
        if not response.ok:
            return None
        try:
            user_info = _parse_user_info(json.loads(response_text))
        except json.JSONDecodeError:
            return None
        if user_info is None:
            return None

        return Credentials.create(
            profile=profile.name,
            cookie=cookie,
            csrftoken=csrftoken,
            username=user_info["username"],
            cn_name=user_info["cn_name"],
            department=user_info["department"],
            ttl_seconds=ttl_seconds,
        )


class AuthManager:
    def __init__(
        self,
        config: ConfigManager,
        store: CredentialStore,
        business_store: Optional[BusinessStore] = None,
    ):
        self.config = config
        self.store = store
        self.browser = BrowserAuthenticator(store, business_store)

    def ensure_credentials(self, force_refresh: bool = False) -> Credentials:
        profile = self.config.current_profile()
        credentials = self.store.load(profile.name)

        if force_refresh:
            print(f"正在刷新环境 {profile.name!r} 的认证信息...")
        elif credentials is None:
            print(f"环境 {profile.name!r} 尚未登录，将打开 Edge 获取认证信息。")
        elif credentials.is_expired():
            print(
                f"环境 {profile.name!r} 的认证信息已过期，将打开 Edge 重新获取。"
            )
        else:
            return credentials

        return self.browser.login(
            profile=profile,
            timeout_ms=self.config.timeout_ms,
            ttl_seconds=self.config.auth_ttl_seconds,
            user_data_dir=self.config.browser_profile_dir(profile.name),
            browser_channel=self.config.browser_channel,
            session_probe_timeout_ms=self.config.session_probe_timeout_ms,
            login_timeout_ms=self.config.login_timeout_ms,
        )

    def login(self, show_secrets: bool = False) -> Credentials:
        profile = self.config.current_profile()
        return self.browser.login(
            profile=profile,
            timeout_ms=self.config.timeout_ms,
            ttl_seconds=self.config.auth_ttl_seconds,
            user_data_dir=self.config.browser_profile_dir(profile.name),
            browser_channel=self.config.browser_channel,
            session_probe_timeout_ms=self.config.session_probe_timeout_ms,
            login_timeout_ms=self.config.login_timeout_ms,
            show_secrets=show_secrets,
        )

    def logout(
        self,
        all_profiles: bool = False,
        forget_browser: bool = False,
    ) -> None:
        if all_profiles:
            self.store.delete()
        else:
            self.store.delete(self.config.current_name)
        if forget_browser:
            target = (
                self.config.browser_profile_root
                if all_profiles
                else self.config.browser_profile_dir()
            )
            if target.exists():
                shutil.rmtree(target)

    def status(self) -> Credentials:
        credentials = self.store.load(self.config.current_name)
        if credentials is None:
            raise CredentialError(f"环境 {self.config.current_name!r} 尚未登录")
        return credentials
