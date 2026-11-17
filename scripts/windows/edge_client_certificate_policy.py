"""Generate managed Edge policy values for trusted certificate-request origins."""

import argparse
import json
import re


DNS_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
HTTPS_ORIGIN = re.compile(
    rf"https://(?P<host>{DNS_LABEL}(?:\.{DNS_LABEL})*)"
    r"(?::(?P<port>[0-9]{1,5}))?/?",
    re.ASCII | re.IGNORECASE,
)


def parse_origin(value: str) -> str:
    match = HTTPS_ORIGIN.fullmatch(value)
    if match is None:
        raise argparse.ArgumentTypeError(
            "请填写 HTTPS 主机地址，可带端口，例如 https://auth.example.com"
            "，不可包含通配符、路径、凭据或查询参数"
        )
    host = match["host"].lower()
    port = int(match["port"] or "443")
    if len(host) > 253 or not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("主机名过长或端口不在 1 到 65535 之间")
    return f"https://{host}:{port}"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("origin", nargs="+", type=parse_origin, metavar="HTTPS_ORIGIN")
    origins = parser.parse_args().origin
    policies = {
        "AutoSelectCertificateForUrls": [
            json.dumps({"pattern": origin, "filter": {}}, separators=(",", ":"))
            for origin in dict.fromkeys(origins)
        ],
        "PromptOnMultipleMatchingCertificates": True,
    }
    print(json.dumps(policies, indent=2))


if __name__ == "__main__":
    main()
