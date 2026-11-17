"""Validate exact HTTPS origins and build Edge client certificate rules."""

import json
import re


AUTO_SELECT = "AutoSelectCertificateForUrls"
PROMPT_ON_MULTIPLE = "PromptOnMultipleMatchingCertificates"

_DNS_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
_HTTPS_ORIGIN = re.compile(
    rf"https://(?P<host>{_DNS_LABEL}(?:\.{_DNS_LABEL})*)"
    r"(?::(?P<port>[0-9]{1,5}))?/?",
    re.ASCII | re.IGNORECASE,
)


def normalize_origin(value: str) -> str:
    match = _HTTPS_ORIGIN.fullmatch(value) if isinstance(value, str) else None
    if match is None:
        raise ValueError(
            "请填写 HTTPS 主机地址，可带端口，例如 https://auth.example.com"
            "，不可包含通配符、路径、凭据或查询参数"
        )
    host = match["host"].lower()
    port = int(match["port"] or "443")
    if len(host) > 253 or not 1 <= port <= 65535:
        raise ValueError("主机名过长或端口不在 1 到 65535 之间")
    return f"https://{host}:{port}"


def certificate_rule(origin: str) -> str:
    return json.dumps({"pattern": origin, "filter": {}}, separators=(",", ":"))


def rule_covers_origin(rule: str, origin: str) -> bool:
    """Recognize existing Edge rules covering a configured HTTPS origin."""
    try:
        policy = json.loads(rule)
    except (TypeError, ValueError):
        return False
    pattern = policy.get("pattern") if isinstance(policy, dict) else None
    if not isinstance(pattern, str):
        return False
    if pattern == "*":
        return True

    scheme, separator, authority = pattern.lower().partition("://")
    if separator and scheme not in ("https", "*"):
        return False
    if not separator:
        authority = scheme
    hostname, _, port = authority.split("/", 1)[0].partition(":")
    target_host, target_port = origin.removeprefix("https://").split(":")
    if port not in ("", "*", target_port):
        return False
    if hostname.startswith("[*.]"):
        domain = hostname[4:]
        return target_host == domain or target_host.endswith("." + domain)
    return hostname in ("*", target_host)
