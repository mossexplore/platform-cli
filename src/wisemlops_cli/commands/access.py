"""权限服务接入状态。"""
import typer
from ..output import console
from .common import runtime_from_context, fail

access_app = typer.Typer(no_args_is_help=True, help='检查 CLI 在线访问授权')


@access_app.command('status')
def status(context: typer.Context):
    """实时检查当前平台账号及环境的访问授权。"""
    try:
        runtime = runtime_from_context(context)
        settings = runtime.config.access_control
        if not settings or not settings.get('enabled', True):
            console.print('未启用在线权限检查，请联系管理员配置 access_control。')
            return
        runtime.authenticated_call(lambda client: None)
        console.print('当前账号已获当前环境访问授权。')
    except Exception as exc:
        fail(exc)
