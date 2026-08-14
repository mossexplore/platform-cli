"""通过 Edge 登录并管理有有效期的本地认证信息。"""

from __future__ import annotations

import json
from typing import Any

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
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="msedge", headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            try:
                print(f"当前环境: {profile.name}")
                print(f"正在打开: {profile.api_endpoint}")
                page.goto(
                    profile.api_endpoint,
                    wait_until="domcontentloaded",
                    timeout=timeout_ms,
                )
                input("请在 Edge 中完成登录，登录成功后按回车键继续...")

                try:
                    with page.expect_request(
                        lambda request: request.url.split("?", 1)[0].rstrip("/")
                        == user_info_url.rstrip("/"),
                        timeout=timeout_ms,
                    ) as request_info:
                        page.reload(
                            wait_until="domcontentloaded",
                            timeout=timeout_ms,
                        )
                    captured_headers = request_info.value.all_headers()
                except PlaywrightTimeoutError as exc:
                    raise AuthenticationError(
                        "未捕获到 /ai/user/info 请求，无法获取 csrftoken"
                    ) from exc

                cookies = context.cookies(user_info_url)
                cookie = "; ".join(
                    f"{item['name']}={item['value']}" for item in cookies
                )
                csrftoken = (
                    captured_headers.get("csrftoken")
                    or captured_headers.get("x-csrftoken")
                    or captured_headers.get("x-csrf-token")
                )
                if not cookie:
                    raise AuthenticationError("登录后未获取到 Cookie")
                if not csrftoken:
                    names = ", ".join(sorted(captured_headers))
                    raise AuthenticationError(
                        "请求头中未找到 csrftoken。实际请求头名称: " + names
                    )

                response = context.request.get(
                    user_info_url,
                    headers={
                        "cookie": cookie,
                        "csrftoken": csrftoken,
                        "referer": profile.api_endpoint,
                    },
                    timeout=timeout_ms,
                )
                response_text = response.text()
                if not response.ok:
                    raise AuthenticationError(
                        f"用户信息接口请求失败，HTTP {response.status}: "
                        f"{response_text[:300]}"
                    )
                try:
                    username = _find_username(json.loads(response_text))
                except json.JSONDecodeError as exc:
                    raise AuthenticationError(
                        "用户信息接口没有返回有效 JSON: " + response_text[:300]
                    ) from exc

                credentials = Credentials.create(
                    profile=profile.name,
                    cookie=cookie,
                    csrftoken=csrftoken,
                    username=username,
                    ttl_seconds=ttl_seconds,
                )
                self.store.save(credentials)
                print(
                    f"认证信息已保存，有效期 {ttl_seconds} 秒，用户: "
                    f"{username or '未知'}"
                )
                if show_secrets:
                    print(f"cookie: {cookie}")
                    print(f"csrftoken: {csrftoken}")
                _wait_for_edge(
                    page,
                    "Edge 将保持打开；请手动关闭 Edge 以继续执行命令。",
                )
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
        )

    def login(self, show_secrets: bool = False) -> Credentials:
        profile = self.config.current_profile()
        return self.browser.login(
            profile=profile,
            timeout_ms=self.config.timeout_ms,
            ttl_seconds=self.config.auth_ttl_seconds,
            show_secrets=show_secrets,
        )

    def logout(self, all_profiles: bool = False) -> None:
        if all_profiles:
            self.store.delete()
        else:
            self.store.delete(self.config.current_name)

    def status(self) -> Credentials:
        credentials = self.store.load(self.config.current_name)
        if credentials is None:
            raise CredentialError(f"profile {self.config.current_name!r} 尚未登录")
        return credentials
