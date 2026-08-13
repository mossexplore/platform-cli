#!/usr/bin/env python3
"""使用 Playwright 登录 CloudTest 控制台并获取认证信息。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


CONFIG_PATH = Path(__file__).with_name("config.json")


def load_current_profile(config_path: Path = CONFIG_PATH) -> tuple[dict[str, Any], dict[str, Any]]:
    """读取配置并返回完整配置和 current 指定的 profile。"""
    try:
        with config_path.open("r", encoding="utf-8") as file:
            config = json.load(file)
    except FileNotFoundError as exc:
        raise ValueError(f"配置文件不存在: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件不是有效的 JSON: {exc}") from exc

    current = config.get("current")
    profiles = config.get("profiles")
    if not isinstance(current, str) or not current:
        raise ValueError("config.json 中的 current 必须是非空字符串")
    if not isinstance(profiles, list):
        raise ValueError("config.json 中的 profiles 必须是数组")

    profile = next(
        (
            item
            for item in profiles
            if isinstance(item, dict) and item.get("name") == current
        ),
        None,
    )
    if profile is None:
        raise ValueError(f"profiles 中不存在 name 为 {current!r} 的配置")

    endpoint = profile.get("api_endpoint")
    parsed_endpoint = urlsplit(endpoint) if isinstance(endpoint, str) else None
    if not parsed_endpoint or parsed_endpoint.scheme not in {"http", "https"} or not parsed_endpoint.netloc:
        raise ValueError("当前 profile 的 api_endpoint 不是有效的 HTTP(S) URL")

    return config, profile


def build_user_info_url(api_endpoint: str) -> str:
    """从控制台地址提取 origin，并拼接用户信息接口。"""
    parsed = urlsplit(api_endpoint)
    return f"{parsed.scheme}://{parsed.netloc}/ai/user/info"


def find_username(response_body: Any) -> Any:
    """兼容 username 位于响应顶层或常见 data/result 包装中的情况。"""
    if not isinstance(response_body, dict):
        return None
    if "username" in response_body:
        return response_body["username"]
    for wrapper in ("data", "result"):
        nested = response_body.get(wrapper)
        if isinstance(nested, dict) and "username" in nested:
            return nested["username"]
    return None


def capture_auth(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    """打开浏览器等待登录，然后调用用户接口并捕获认证信息。"""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "success": False,
            "message": "未安装playwright，请运行: pip install playwright && playwright install chromium",
        }

    try:
        config, profile = load_current_profile(config_path)
    except ValueError as exc:
        return {"success": False, "message": str(exc)}

    api_endpoint = profile["api_endpoint"]
    user_info_url = build_user_info_url(api_endpoint)
    timeout = config.get("api", {}).get("timeout", 30000)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        timeout = 30000

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(timeout)

            print(f"当前环境: {profile['name']}")
            print(f"正在打开: {api_endpoint}")
            page.goto(api_endpoint, wait_until="domcontentloaded", timeout=timeout)
            input("请在浏览器中完成登录，登录成功后按回车键继续...")

            # 重新加载控制台，让页面自身发起用户信息请求。这样可以保留前端
            # 为请求追加的 cookie、csrftoken 等请求头。
            try:
                with page.expect_response(
                    lambda item: item.url.split("?", 1)[0].rstrip("/")
                    == user_info_url.rstrip("/"),
                    timeout=timeout,
                ) as response_info:
                    page.reload(wait_until="domcontentloaded", timeout=timeout)
                response = response_info.value
            except PlaywrightTimeoutError:
                # 某些控制台页面不会在刷新时调用该接口，此时直接访问接口兜底。
                response = page.goto(
                    user_info_url,
                    wait_until="domcontentloaded",
                    timeout=timeout,
                )
            if response is None:
                return {"success": False, "message": "未收到用户信息接口的响应"}

            request_headers = response.request.all_headers()
            cookie = request_headers.get("cookie")
            csrftoken = (
                request_headers.get("csrftoken")
                or request_headers.get("x-csrftoken")
                or request_headers.get("x-csrf-token")
            )

            # 如果服务端把 CSRF token 仅保存在 Cookie 中，也返回该 cookie 的值。
            if csrftoken is None:
                csrf_cookie = next(
                    (
                        item
                        for item in context.cookies(user_info_url)
                        if item["name"].lower() == "csrftoken"
                    ),
                    None,
                )
                if csrf_cookie is not None:
                    csrftoken = csrf_cookie["value"]

            try:
                response_body = response.json()
            except Exception as exc:
                return {
                    "success": False,
                    "message": f"用户信息接口响应体不是有效的 JSON: {exc}",
                }

            username = find_username(response_body)

            print(f"cookie: {cookie}")
            print(f"csrftoken: {csrftoken}")
            print(f"username: {username}")

            browser.close()
            return {
                "success": True,
                "cookie": cookie,
                "csrftoken": csrftoken,
                "username": username,
            }
    except Exception as exc:
        return {"success": False, "message": f"浏览器登录或认证信息获取失败: {exc}"}


def main() -> None:
    result = capture_auth()
    if not result["success"]:
        print(result["message"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
