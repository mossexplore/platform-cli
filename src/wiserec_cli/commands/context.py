"""Inspect the effective execution context without network access."""
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
import typer
from .. import __version__
from ..execution import current
from ..config import ConfigManager, user_config_dir
from ..output import print_result
from .common import fail


def show_context(context: typer.Context,
                 as_json: bool = typer.Option(False, "--json", help="输出 JSON")):
    """查看当前运行模式及生效配置路径"""
    try:
        path = context.find_root().params.get("config")
        config = ConfigManager(Path(path) if path else None)
        endpoint = urlsplit(config.current_profile().api_endpoint)
        # Drop credentials, query parameters and fragments.
        host = endpoint.hostname or ""
        if ":" in host:
            host = "[" + host + "]"
        if endpoint.port:
            host += ":" + str(endpoint.port)
        data = {"运行模式": current().mode, "当前环境": config.current_name,
                "平台地址": urlunsplit((endpoint.scheme, host, endpoint.path, "", "")),
                "CLI 版本": __version__, "CLI 路径": str(Path(sys.argv[0]).resolve()),
                "配置路径": str(config.path), "状态目录": str(user_config_dir()),
                **current().details}
        print_result(data, output_format="json" if as_json else "table")
    except Exception as exc:
        fail(exc)
