"""ml 命令行入口。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from . import __version__
from .commands.history import history_app
from .commands.context import show_context
from .commands.access import access_app
from .commands.algorithm import algorithm_app
from .commands.dataset import dataset_app
from .commands.dataset_files import files_app as dataset_files_app
from .commands.service import service_app
from .commands.auth import auth_app, login, logout
from .commands.jupyter import jupyter_app
from .commands.webstudio import webstudio_app
from .commands.business import business_app
from .commands.common import fail
from .commands.env import env_app
from .commands.featureset import featureset_app
from .commands.feature_task import feature_task_app
from .commands.mep import mep_app
from .commands.mtp import mtp_app
from .commands.offline import offline_app
from .commands.train import train_app
from .commands.model import model_app
from .commands.model_deploy import deploy as deploy_model
from .commands.resource import resource_app
from .commands.deployment import deployment_app
from .commands.tree import show_tree
from .commands.user import user_app
from .runtime import Runtime
from . import ping
from .invocation import InvocationGroup


app = typer.Typer(
    name="ml",
    cls=InvocationGroup,
    no_args_is_help=True,
    help="WiseRec平台命令行客户端",
)
app.command("context")(show_context)
app.command("login")(login)
app.command("logout")(logout)
app.command("tree")(show_tree)
app.add_typer(history_app, name="history")
app.add_typer(auth_app, name="auth")
app.add_typer(access_app, name="access")
app.add_typer(business_app, name="business")
app.add_typer(env_app, name="env")
app.add_typer(user_app, name="user")
app.add_typer(mep_app, name="mep")
app.add_typer(mtp_app, name="mtp")
app.add_typer(offline_app, name="offline")
app.add_typer(train_app, name="train")
model_app.command("deploy")(deploy_model)
app.add_typer(model_app, name="model")
app.add_typer(resource_app, name="resource")
app.add_typer(deployment_app, name="deployment")
app.add_typer(algorithm_app, name="algorithm")
app.add_typer(dataset_app, name="dataset")
dataset_app.add_typer(dataset_files_app, name="files")
app.add_typer(service_app, name="service")
app.add_typer(featureset_app, name="featureset")
app.add_typer(feature_task_app, name="feature-task")
app.add_typer(jupyter_app, name="jupyter")
app.add_typer(webstudio_app, name="webstudio")


def version_callback(value: bool) -> None:
    if value:
        typer.echo(f"ml {__version__}")
        raise typer.Exit()


@app.callback()
def initialize(
    context: typer.Context,
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        envvar="ML_CONFIG",
        exists=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="config.json 路径，也可使用 ML_CONFIG 环境变量",
    ),
    no_history: bool = typer.Option(False, "--no-history", help="不保存本次命令历史"),
    version: bool = typer.Option(
        False,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="显示版本",
    ),
) -> None:
    """初始化 CLI 运行时。"""
    del version, no_history
    if context.invoked_subcommand in {"tree", "history", "context"}:
        return
    try:
        context.obj = Runtime(config_path=config)
        if (sys.stdin.isatty() and context.invoked_subcommand
                not in {"login", "logout", "auth", "tree"}
                and context.obj.config.auto_ping):
            ping.auto_start(context.obj)
    except Exception as exc:
        fail(exc)


def configure_windows_output() -> None:
    """Use UTF-8 for redirected Windows output, including CI and log files."""
    if sys.platform != "win32":
        return
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and not stream.isatty() and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")


def run() -> None:
    import click
    from . import messages as msg
    from .command_errors import show_usage_error

    try:
        configure_windows_output()
        app()
    except click.ClickException as exc:
        show_usage_error(exc)
        raise SystemExit(exc.exit_code) from None
    except KeyboardInterrupt:
        msg.detail("已取消操作")
        raise SystemExit(130) from None
    except Exception as exc:
        # 最外层边界也覆盖参数解析/运行时/历史记录等非业务路径。
        # 禁止 Typer 将内部异常及局部变量直接打印到用户终端。
        msg.error(f"命令执行失败：{exc}")
        raise SystemExit(1) from None


if __name__ == "__main__":
    run()
