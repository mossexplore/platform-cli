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


def wait_for_edge_to_close(page: Any) -> None:
    """保持脚本和浏览器运行，直到用户主动关闭 Edge 窗口。"""
    print("认证信息获取完成。Edge 将保持打开，请手动关闭 Edge 以结束程序。")
    try:
        page.wait_for_event("close", timeout=0)
    except Exception:
        # 用户关闭整个浏览器时，页面对象可能直接失效，这是正常退出流程。
        pass


def capture_auth(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    """打开浏览器等待登录，然后调用用户接口并捕获认证信息。"""
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "success": False,
            "message": "未安装playwright，请运行: python -m pip install playwright",
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
            # 使用 Windows 系统安装的 Microsoft Edge，无需下载 Playwright Chromium。
            browser = playwright.chromium.launch(channel="msedge", headless=False)
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(timeout)

            print(f"当前环境: {profile['name']}")
            print(f"正在打开: {api_endpoint}")
            page.goto(api_endpoint, wait_until="domcontentloaded", timeout=timeout)
            input("请在浏览器中完成登录，登录成功后按回车键继续...")

            # 刷新控制台以触发页面自身的 /ai/user/info 请求，并立即读取真实
            # 请求头。这里只捕获 Request，不读取导航 Response，避免响应体失效。
            try:
                with page.expect_request(
                    lambda request: request.url.split("?", 1)[0].rstrip("/")
                    == user_info_url.rstrip("/"),
                    timeout=timeout,
                ) as request_info:
                    page.reload(wait_until="domcontentloaded", timeout=timeout)
                captured_headers = request_info.value.all_headers()
            except PlaywrightTimeoutError:
                result = {
                    "success": False,
                    "message": (
                        "未捕获到 /ai/user/info 请求，无法从真实请求头中获取 "
                        "csrftoken。请确认登录后控制台页面能够正常加载。"
                    ),
                }
                print(result["message"])
                wait_for_edge_to_close(page)
                return result

            # browser_context.request 与浏览器上下文共享 Cookie。直接请求接口，
            # 避免读取页面导航响应时，Edge 已经释放响应体。
            # Cookie 从浏览器上下文读取全部匹配项，不能使用某一次请求头中的
            # cookie 字段，否则可能只得到该请求实际携带的部分 Cookie。
            cookies = context.cookies(user_info_url)
            cookie = "; ".join(
                f"{item['name']}={item['value']}" for item in cookies
            )
            csrftoken = (
                captured_headers.get("csrftoken")
                or captured_headers.get("x-csrftoken")
                or captured_headers.get("x-csrf-token")
            )
            if not csrftoken:
                header_names = ", ".join(sorted(captured_headers))
                result = {
                    "success": False,
                    "message": (
                        "已捕获 /ai/user/info 请求，但请求头中不存在 csrftoken、"
                        "x-csrftoken 或 x-csrf-token。实际请求头名称: "
                        f"{header_names}"
                    ),
                }
                print(result["message"])
                wait_for_edge_to_close(page)
                return result

            request_headers = {"referer": api_endpoint}
            if cookie:
                request_headers["cookie"] = cookie
            if csrftoken:
                request_headers["csrftoken"] = csrftoken

            response = context.request.get(
                user_info_url,
                headers=request_headers,
                timeout=timeout,
            )
            # 在进行任何后续操作前立刻保存响应文本。
            response_text = response.text()
            if not response.ok:
                result = {
                    "success": False,
                    "message": (
                        f"用户信息接口请求失败，HTTP {response.status}: "
                        f"{response_text[:300]}"
                    ),
                }
                print(result["message"])
                wait_for_edge_to_close(page)
                return result
            try:
                response_body = json.loads(response_text)
            except json.JSONDecodeError as exc:
                result = {
                    "success": False,
                    "message": (
                        f"用户信息接口响应体不是有效的 JSON: {exc}; "
                        f"响应内容: {response_text[:300]}"
                    ),
                }
                print(result["message"])
                wait_for_edge_to_close(page)
                return result

            username = find_username(response_body)

            print(f"cookie: {cookie}")
            print(f"csrftoken: {csrftoken}")
            print(f"username: {username}")

            result = {
                "success": True,
                "cookie": cookie,
                "csrftoken": csrftoken,
                "username": username,
            }
            wait_for_edge_to_close(page)
            return result
    except Exception as exc:
        return {"success": False, "message": f"浏览器登录或认证信息获取失败: {exc}"}


def main() -> None:
    result = capture_auth()
    if not result["success"]:
        print(result["message"])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
