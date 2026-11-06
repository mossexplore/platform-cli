"""本地平台操作关系；MLOps 只开放显式登记的能力。"""
from .train import list_mlops
from ..errors import MlError

# 值为实际实现，未登记的业务操作一律不支持。
MLOPS_BINDINGS = {"train list": list_mlops}
LOCAL_GROUPS = {"env", "history", "context", "tree", "access"}
# 认证与业务选择沿用现有机制，仍执行原有权限检查。
CONTEXT_GROUPS = {"login", "logout", "auth", "business"}


def supported(platform_type, command):
    if platform_type == "wiserec":
        return True
    if command.startswith("auth ping"):
        return command == "auth ping status"
    return (command in MLOPS_BINDINGS or
            command.split(" ")[0] in LOCAL_GROUPS | CONTEXT_GROUPS)


def require_supported(platform_type, command):
    if not supported(platform_type, command):
        raise MlError(f"管理台 {platform_type} 不支持命令 ml {command}；运行 ml tree 查看支持的命令")


def invocation_path(context):
    """仅解析嵌套命令，不执行回调或接口。"""
    command = context.command
    parts = []
    args = list(context.meta.get("command_args", []))
    while command is not None and hasattr(command, "commands") and args:
        child_name, child, remaining = command.resolve_command(context, args)
        if child is None:
            break
        parts.append(child_name)
        command = child
        args = remaining
    return " ".join(parts)
