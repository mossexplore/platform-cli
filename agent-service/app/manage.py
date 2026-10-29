"""Explicit migration, safe diagnosis and single-worker local startup."""

import argparse
import sys
from .settings import load_settings
from .db import connect, migrate, verify_schema


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
    except Exception:
        print(
            "配置读取失败：请检查配置文件位置、JSON 字段、服务地址及 gateway_token（至少32字符）。不会输出配置中的秘密。",
            file=sys.stderr,
        )
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
    engine, db = connect(cfg)
    try:
        if args.command == "migrate":
            migrate(engine)
            print("Agent 数据库结构已就绪")
        else:
            verify_schema(db)
            print(
                "配置与 Agent 数据库结构检查通过；模型、平台登录及权限服务仍需实际联调"
            )
    except Exception as exc:
        print(
            f"数据库检查未通过（{type(exc).__name__}）。请核对连接、数据库创建及迁移状态。",
            file=sys.stderr,
        )
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
