"""通过 Edge 登录并管理有有效期的本地认证信息。"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable, Optional, Type

from .config import ConfigManager
from .credentials import CredentialStore
from .errors import AuthenticationError, CredentialError
from .models import Credentials, Profile


def _find_username(response_body: Any) -> str:
    if not isinstance(response_body, dict):
        return ""
    if "username" in response_body:
        return str(response_body["username"])
    for wrapper in ("data", "result"):
        nested = response_body.get(wrapper)
        if isinstance(nested, dict) and "username" in nested:
            return str(nested["username"])
    return ""


def _wait_for_edge(page: Any, message: str) -> None:
    print(message)
    try:
        page.wait_for_event("close", timeout=0)
    except Exception:
        pass


class BrowserAuthenticator:
    def __init__(self, store: CredentialStore):
        self.store = store

    def login(
        self,
        profile: Profile,
        timeout_ms: int,
        ttl_seconds: int,
        user_data_dir: Path,
        browser_channel: str,
        session_probe_timeout_ms: int,
        show_secrets: bool = False,
    ) -> Credentials:
        try:
            from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
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

            try:
                print(f"当前环境: {profile.name}")
                print(f"Edge Profile: {user_data_dir}")
                print(f"正在打开: {profile.api_endpoint}")
                credentials = self._capture_credentials(
                    context=context,
                    page=page,
                    profile=profile,
                    user_info_url=user_info_url,
                    ttl_seconds=ttl_seconds,
                    request_timeout_ms=timeout_ms,
                    capture_timeout_ms=min(
                        session_probe_timeout_ms,
                        timeout_ms,
                    ),
                    action=lambda: page.goto(
                        profile.api_endpoint,
                        wait_until="domcontentloaded",
                        timeout=timeout_ms,
                    ),
                    timeout_error=PlaywrightTimeoutError,
                )
                reused_session = credentials is not None

                if credentials is None:
                    print("未发现有效的持久登录会话，需要用户完成登录。")
                    input("请在 Edge 中完成登录，登录成功后按回车键继续...")
                    credentials = self._capture_credentials(
                        context=context,
                        page=page,
                        profile=profile,
                        user_info_url=user_info_url,
                        ttl_seconds=ttl_seconds,
                        request_timeout_ms=timeout_ms,
                        capture_timeout_ms=timeout_ms,
                        action=lambda: page.reload(
                            wait_until="domcontentloaded",
                            timeout=timeout_ms,
                        ),
                        timeout_error=PlaywrightTimeoutError,
                    )
                if credentials is None:
                    raise AuthenticationError(
                        "登录后仍未获取到有效的 Cookie、csrftoken 和用户信息"
                    )

                self.store.save(credentials)
                source = "持久 Edge 会话" if reused_session else "用户登录"
                print(
                    f"已通过{source}刷新认证信息，有效期 {ttl_seconds} 秒，用户: "
                    f"{credentials.username or '未知'}"
                )
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

    def _capture_credentials(
        self,
        context: Any,
        page: Any,
        profile: Profile,
        user_info_url: str,
        ttl_seconds: int,
        request_timeout_ms: int,
        capture_timeout_ms: int,
        action: Callable[[], Any],
        timeout_error: Type[Exception],
    ) -> Optional[Credentials]:
        try:
            with page.expect_request(
                lambda request: request.url.split("?", 1)[0].rstrip("/")
                == user_info_url.rstrip("/"),
                timeout=capture_timeout_ms,
            ) as request_info:
                action()
            captured_headers = request_info.value.all_headers()
        except timeout_error:
            return None

        cookies = context.cookies(user_info_url)
        cookie = "; ".join(
            f"{item['name']}={item['value']}" for item in cookies
        )
        csrftoken = (
            captured_headers.get("csrftoken")
            or captured_headers.get("x-csrftoken")
            or captured_headers.get("x-csrf-token")
        )
        if not cookie or not csrftoken:
            return None

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
        if not response.ok:
            return None
        try:
            username = _find_username(json.loads(response_text))
        except json.JSONDecodeError:
            return None

        return Credentials.create(
            profile=profile.name,
            cookie=cookie,
            csrftoken=csrftoken,
            username=username,
            ttl_seconds=ttl_seconds,
        )


class AuthManager:
    def __init__(self, config: ConfigManager, store: CredentialStore):
        self.config = config
        self.store = store
        self.browser = BrowserAuthenticator(store)

    def ensure_credentials(self, force_refresh: bool = False) -> Credentials:
        profile = self.config.current_profile()
        credentials = self.store.load(profile.name)

        if force_refresh:
            print(f"正在刷新 profile {profile.name!r} 的认证信息...")
        elif credentials is None:
            print(f"profile {profile.name!r} 尚未登录，将打开 Edge 获取认证信息。")
        elif credentials.is_expired():
            print(
                f"profile {profile.name!r} 的认证信息已过期，将打开 Edge 重新获取。"
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
            raise CredentialError(f"profile {self.config.current_name!r} 尚未登录")
        return credentials
