"""权限服务接入状态。"""
import typer
from ..output import console
from ..access_diagnostics import AccessDiagnostics
from .. import __version__
from .common import runtime_from_context, fail

access_app = typer.Typer(no_args_is_help=True, help='检查 CLI 在线访问授权')


@access_app.command('status')
def status(context: typer.Context, diagnose: bool = typer.Option(False, "--diagnose", help="显示权限请求连接、耗时和有限响应头，不输出凭据")):
    """实时检查当前平台账号及环境的访问授权。"""
    try:
        runtime = runtime_from_context(context)
        if diagnose:
            runtime.access_diagnostics = AccessDiagnostics(lambda text: console.print(text, markup=False, highlight=False))
            runtime.access_diagnostics.line('CLI 版本', __version__)
            runtime.access_diagnostics.line('配置文件', runtime.config.path)
        settings = runtime.config.access_control
        if not settings or not settings.get('enabled', True):
            console.print('未启用在线权限检查，请联系管理员配置 access_control。')
            return
        runtime.authenticated_call(lambda client: None)
        console.print('当前账号已获当前环境访问授权。')
    except Exception as exc:
        fail(exc)
    finally:
        if 'runtime' in locals():
            runtime.access_diagnostics = None
