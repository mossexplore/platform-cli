"""Explicit migration, safe diagnosis and single-worker local startup."""

import argparse
import sys
from .settings import load_settings
from .config_errors import describe_config_error
from .db import connect, migrate, verify_schema, SchemaError


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["migrate", "check", "serve"])
    parser.add_argument("--config")
    args = parser.parse_args()
    if args.config:
        import os

        os.environ["WISEREC_AGENT_CONFIG"] = str(
            __import__("pathlib").Path(args.config).resolve()
        )
    try:
        cfg = load_settings()
    except Exception as exc:
        print("配置读取失败：\n" + describe_config_error(exc), file=sys.stderr)
        return 1
    if args.command == "serve":
        import uvicorn

        uvicorn.run(
            "app.main:create_app",
            factory=True,
            host=cfg.server.host,
            port=cfg.server.port,
            workers=1,
            access_log=False,
            log_level="info",
        )
        return 0
    engine = None
    try:
        engine, db = connect(cfg)
        if args.command == "migrate":
            migrate(engine)
            print("Agent 数据库结构已就绪")
        else:
            verify_schema(db)
            print(
                "配置与 Agent 数据库结构检查通过；模型、平台登录及权限服务仍需实际联调"
            )
    except SchemaError as exc:
        print("数据库结构检查未通过：" + str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        args = getattr(getattr(exc, "orig", None), "args", ())
        code = args[0] if args and type(args[0]) is int else None
        detail = f"，MySQL 错误编号 {code}" if code is not None else ""
        print(
            f"数据库检查未通过（{type(exc).__name__}{detail}）。请核对连接、权限与表结构；未输出连接串或 SQL 参数。",
            file=sys.stderr,
        )
        return 1
    finally:
        if engine is not None:
            engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
