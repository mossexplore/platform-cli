"""本地平台操作关系；MLOps 只开放显式登记的能力。"""
from .train import list_mlops
from ..errors import MlError

# 值为实际实现，未登记的业务操作一律不支持。
MLOPS_BINDINGS = {"train list": list_mlops}
# 已确认与 WiseRec 协议一致的公开命令，直接复用既有命令和 Service。
# 按叶命令登记，未来新增操作需确认后显式开放。
SHARED_COMMANDS = frozenset({
    "auth ping start", "auth ping stop", "auth ping status", "user info", "mep config get",
    "model list", "model detail", "model source", "model deploy",
    "resource template list", "resource template detail",
    "deployment template list", "deployment template detail",
    "dataset list", "dataset detail", "dataset files list", "dataset files upload",
    "feature-task detail",
    "train history list", "train history detail", "train history logs download", "train instance list", "train instance logs download",
    "webstudio list", "webstudio login", "webstudio start", "webstudio stop", "webstudio show",
    "jupyter exec", "jupyter doctor",
    "jupyter files list", "jupyter files stat", "jupyter files read", "jupyter files write",
    "jupyter files mkdir", "jupyter files upload", "jupyter files download",
    "jupyter files move", "jupyter files copy", "jupyter files delete",
    "jupyter notebook run", "jupyter terminal list", "jupyter terminal open",
    "jupyter terminal attach", "jupyter terminal close",
    "service list", "service logs", "service mock", "service host list",
    "service host mock", "service deployment list",
})
LOCAL_GROUPS = {"env", "history", "context", "tree", "access"}
# 认证与业务选择沿用现有机制，仍执行原有权限检查。
CONTEXT_GROUPS = {"login", "logout", "auth", "business"}


def supported(platform_type, command):
    if platform_type == "wiserec":
        return True
    return (command in MLOPS_BINDINGS or command in SHARED_COMMANDS or
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
