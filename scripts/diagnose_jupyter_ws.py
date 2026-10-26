"""复用已安装 CLI 的配置与认证，诊断已有终端的 WebSocket 握手。"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError, version
import json
import os
from pathlib import Path
import platform
import socket
import ssl
import sys
import time
from urllib.parse import quote, urlsplit, urlunsplit


def exception_details(error):
    """仅输出结构化安全字段；异常正文可能含认证头、URL、响应体。"""
    chain, seen, hints = [], set(), []
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        item = {"type": type(error).__name__}
        for key in ("errno", "winerror", "status_code", "verify_code"):
            value = getattr(error, key, None)
            if isinstance(value, int):
                item[key] = value
        chain.append(item)
        status = item.get("status_code")
        if isinstance(error, ssl.SSLCertVerificationError):
            hints.append("证书校验失败：检查企业 CA、证书链及主机名；核对 jupyter.ca_file")
        elif isinstance(error, ssl.SSLError):
            hints.append("TLS 协商失败：检查 TLS 配置及中间代理")
        elif isinstance(error, socket.gaierror):
            hints.append("DNS 解析失败：比较浏览器代理/PAC 与本机 DNS")
        elif isinstance(error, TimeoutError) or "Timeout" in type(error).__name__:
            hints.append("连接或握手超时：检查网络路径、网关日志及配置超时")
        elif isinstance(error, ConnectionError):
            hints.append("连接被拒绝或中断：检查目标端口、网关和后端状态")
        if status in (401, 403):
            hints.append("握手认证或策略拒绝：比较 Cookie、Token、Origin、权限与版本策略")
        elif isinstance(status, int) and 300 <= status < 400:
            hints.append("发生重定向：CLI 禁止跟随 WebSocket 跳转；检查登录态与目标路径")
        elif status == 404:
            hints.append("路径或终端不存在：比较浏览器 WS 路径并重新列出终端")
        elif status in (502, 503, 504):
            hints.append("网关或后端故障：检查 WebSocket 转发、上游实例及网关错误日志")
        elif status == 400:
            hints.append("握手请求被拒绝：检查 Upgrade、Connection、Origin 及代理转发")
        error = error.__cause__ or (None if error.__suppress_context__ else error.__context__)
    return {"exception_chain": chain, "hints": list(dict.fromkeys(hints)) or [
        "结合异常类型与同一时刻的网关/Jupyter 日志定位；不应仅凭通用提示认定 Token 错误"
    ]}


def safe_url(url, secrets=()):
    parts = urlsplit(url)
    host = parts.hostname or ""
    if ":" in host:
        host = "[" + host + "]"
    if parts.port:
        host += ":" + str(parts.port)
    result = urlunsplit((parts.scheme, host, parts.path, "", ""))
    for secret in secrets:
        if secret:
            result = result.replace(secret, "[REDACTED]").replace(quote(secret, safe=""), "[REDACTED]")
    return result


def installed_versions():
    result = {}
    for name in ("wiserec-cli", "httpx", "websocket-client"):
        try:
            result[name] = version(name)
        except PackageNotFoundError:
            result[name] = "未安装"
    return result


def probe(connection, terminal):
    from wiserec_cli.jupyter.connection import JupyterClient

    report = {"steps": []}
    stage = "HTTP GET api/terminals"
    start = time.monotonic()
    try:
        with JupyterClient(connection) as client:
            terminals = client.request("GET", "api/terminals")
            if not isinstance(terminals, list):
                raise ValueError("Unexpected terminal list")
            report["steps"].append({"stage": stage, "ok": True,
                                    "elapsed_seconds": round(time.monotonic() - start, 3),
                                    "terminal_count": len(terminals)})
            if terminal is None:
                report["ok"] = False
                report["action"] = "请先运行 ml jupyter terminal list，再以 --terminal NAME 指定已有终端"
                return report
            if not any(isinstance(item, dict) and str(item.get("name")) == terminal for item in terminals):
                report["ok"] = False
                report["action"] = "指定终端不在当前列表；请核对实例和终端名称，不会自动创建终端"
                return report
            path = "terminals/websocket/" + quote(terminal, safe="")
            parts = urlsplit(connection.url + path)
            ws_url = urlunsplit(("wss" if parts.scheme == "https" else "ws",
                                parts.netloc, parts.path, parts.query, ""))
            report["connection"] = {
                "websocket_url": safe_url(ws_url, (connection.token,)),
                "origin": safe_url(urlunsplit((parts.scheme, parts.netloc, "", "", ""))),
                "authorization_present": "Authorization" in client.headers,
                "businessid_present": bool(client.headers.get("businessid")),
                "cookie_present": bool(client._cookie_header(path)),
                "tls": ("自定义 SSLContext" if isinstance(connection.verify, ssl.SSLContext)
                        else "默认校验" if connection.verify else "校验已关闭"),
                "timeout_seconds": connection.timeout,
                "proxy_policy": "HTTP trust_env=False；WebSocket http_no_proxy=[目标主机]",
                "redirect_limit": 0,
            }
            stage = "WebSocket handshake"
            start = time.monotonic()
            ws = client.socket(path)
            report["steps"].append({"stage": stage, "ok": True,
                                    "status_code": ws.getstatus(),
                                    "elapsed_seconds": round(time.monotonic() - start, 3)})
            # 只断开 WebSocket，不发送 stdin/exit，不调用 DELETE 终端接口。
            stage = "WebSocket disconnect"
            start = time.monotonic()
            ws.close(timeout=1)
            report["ok"] = True
            report["action"] = "本次握手成功，未验证 Shell 交互；若原命令仍失败，核对 Python 环境、CLI 版本及配置"
    except Exception as error:
        report["ok"] = False
        report["steps"].append({"stage": stage, "ok": False,
                                "elapsed_seconds": round(time.monotonic() - start, 3),
                                **exception_details(error)})
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, help="与 ml --config 相同；省略时沿用 ML_CONFIG/默认配置")
    parser.add_argument("--studio-id", help="Web Studio envId；省略时沿用当前默认实例")
    parser.add_argument("--terminal", help="已有终端名称，例如 1；省略时仅检查 HTTP")
    parser.add_argument("--output", type=Path, help="将脱敏 JSON 写入新文件，不覆盖已有文件")
    args = parser.parse_args(argv)
    if args.output and args.output.exists():
        parser.error("--output 已存在，请使用新的文件名")
    report = {
        "time_beijing": datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M:%S"),
        "python": sys.version.split()[0], "python_executable": sys.executable,
        "platform": platform.system(), "openssl": ssl.OPENSSL_VERSION,
        "packages": installed_versions(),
        "environment_variables_present": [name for name in (
            "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY", "http_proxy", "https_proxy",
            "all_proxy", "no_proxy", "SSL_CERT_FILE", "SSL_CERT_DIR", "REQUESTS_CA_BUNDLE",
        ) if os.environ.get(name)],
    }
    stage = "加载 CLI 与配置"
    start = time.monotonic()
    try:
        import wiserec_cli
        from wiserec_cli.runtime import Runtime
        from wiserec_cli.jupyter.connection import from_runtime

        report["cli_code_version"] = wiserec_cli.__version__
        report["cli_module"] = str(wiserec_cli.__file__)
        runtime = Runtime(config_path=args.config)
        runtime.invocation_command = "ml jupyter terminal attach" if args.terminal else "ml jupyter terminal list"
        runtime.full_command = runtime.invocation_command + " [WebSocket diagnostic]"
        report["profile"] = runtime.config.current_name
        stage = "认证与解析连接"
        start = time.monotonic()
        connection = from_runtime(runtime, args.studio_id)
        report.update(probe(connection, args.terminal))
    except Exception as error:
        report.update(ok=False, steps=[{"stage": stage, "ok": False,
                                       "elapsed_seconds": round(time.monotonic() - start, 3),
                                       **exception_details(error)}])
    payload = json.dumps(report, ensure_ascii=False, indent=2)
    print(payload)
    if args.output:
        try:
            with args.output.open("x", encoding="utf-8") as stream:
                stream.write(payload + "\n")
        except OSError as error:
            print("报告保存失败：" + type(error).__name__, file=sys.stderr)
            return 1
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("诊断已取消", file=sys.stderr)
        raise SystemExit(130)
