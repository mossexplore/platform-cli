"""生成隔离的开发配置并在前台启动本机 JupyterLab；不修改管理台配置。"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys


def prepare(root: Path, port: int):
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    for name in ["workspace", "runtime", "config-dir", "data", "ipython"]:
        (root / name).mkdir(exist_ok=True)
    token_path = root / "token"
    if not token_path.exists():
        token_path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    token_path.chmod(0o600)
    config = {
        "current": "jupyter-local", "access_control": {"enabled": False},
        "profiles": [{"name": "jupyter-local", "api_endpoint": f"http://127.0.0.1:{port}/",
                      "jupyter": {"token_file": "token", "business_file": "business.json", "kernel": "python3"}}],
    }
    (root / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
    # 仅初始化开发环境业务目录。实际请求仍从该文件当前环境 selected.businessId 读取。
    from wiserec_cli.business import BusinessStore, Department, Tenant
    store = BusinessStore(root / "business.json")
    if not store.path.exists():
        store.refresh("jupyter-local", "local-developer",
                      [Department("local", "本地开发", (Tenant("local-development", "本地测试业务", (), ()),))],
                      browser_business_id="local-development")
    settings = {
        "ServerApp": {"ip": "127.0.0.1", "port": port, "port_retries": 0,
                      "open_browser": False, "root_dir": str(root / "workspace"),
                      "base_url": "/", "log_level": "WARN"},
        "IdentityProvider": {"token": token_path.read_text(encoding="utf-8").strip()},
    }
    server_config = root / "jupyter_server_config.json"
    server_config.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    server_config.chmod(0o600)
    return server_config


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8888)
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port 必须在 1 到 65535 之间")
    root = Path(__file__).resolve().parents[1] / ".jupyter-local"
    server_config = prepare(root, args.port)
    print(f"本地 CLI 配置：{root / 'config.json'}", flush=True)
    print(f"JupyterLab：http://127.0.0.1:{args.port}/lab （Token 保存在本地 token 文件）", flush=True)
    if args.prepare_only:
        return
    os.environ.update({"JUPYTER_RUNTIME_DIR": str(root / "runtime"),
                       "JUPYTER_CONFIG_DIR": str(root / "config-dir"),
                       "JUPYTER_DATA_DIR": str(root / "data"),
                       "IPYTHONDIR": str(root / "ipython")})
    os.execv(sys.executable, [sys.executable, "-m", "jupyterlab", "--config=" + str(server_config)])


if __name__ == "__main__":
    main()
