"""Explicit function schemas; no generic HTTP or shell escape hatch."""

from typing import Callable, Literal
from pydantic import BaseModel, ConfigDict, Field


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(Params):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


class Search(Page):
    name: str = Field(default="", max_length=200)


class ModelSearch(Search):
    model_type: str | None = None
    owner: str | None = None
    team_id: str = ''


class ModelID(Params):
    model_id: str = Field(min_length=1, max_length=128)


class TaskID(Params):
    task_id: str = Field(min_length=1, max_length=128)


class Instances(TaskID, Page):
    pass


class ServiceSearch(Search):
    model_name: str | None = Field(default=None, max_length=200)
    model_version: str | None = Field(default=None, max_length=200)


class ServiceID(Params):
    service_id: str = Field(min_length=1, max_length=128)


class Hosts(ServiceID):
    page: int = Field(default=1, ge=1)
    pod_ip: str | None = Field(default=None, max_length=100)


class LogFiles(ServiceID):
    pod_name: str = Field(min_length=1, max_length=256)
    cluster_name: str = Field(min_length=1, max_length=256)
    log_type: str = Field(min_length=1, max_length=50)


class Logs(LogFiles):
    file_name: str = Field(min_length=1, max_length=512)
    keywords: list[str] = Field(default_factory=list, max_length=5)
    lines: int = Field(default=100, ge=1, le=1000)
    search_order: Literal['head', 'tail'] = 'tail'
    grep_scope: Literal['A', 'B', 'C'] = 'C'
    grep_line: int = Field(default=0, ge=0, le=1000)


REGISTRY = {
    "list_models": (
        ModelSearch,
        "查询当前业务模型列表，支持名称筛选与分页；第一页不代表全部",
    ),
    "get_model": (ModelID, "按模型 ID 查询模型详情"),
    "get_model_source": (ModelID, "查询模型来源和训练版本"),
    "get_model_training": (ModelID, "查询该模型对应的训练任务"),
    "list_train_tasks": (Search, "按名称查询训练任务列表"),
    "get_train_task": (
        TaskID,
        "在有界分页范围内查找训练任务，找不到不代表全平台不存在",
    ),
    "list_train_instances": (
        Instances,
        "查询训练任务执行实例，task_id 不能使用 job_id 代替",
    ),
    "list_train_history": (TaskID, "查询训练任务最近执行记录，固定第一页十条"),
    "list_services": (ServiceSearch, "查询服务列表及状态，可按服务名或模型名筛选"),
    "list_service_hosts": (Hosts, "查询服务主机、Pod 与集群，固定每页十条"),
    "get_service_deployments": (ServiceID, "查询服务部署视图，不执行部署操作"),
    "list_service_log_files": (
        LogFiles,
        "从已查询的服务主机获取日志文件列表；log_type 可为 run 等主机支持类型",
    ),
    "search_service_logs": (
        Logs,
        "查询已验证主机与文件的首部或尾部日志，支持关键词与上下文行数；不支持精确起止时间过滤",
    ),
}


from .business_tools import OPERATIONS
REGISTRY.update({name: (op.schema, op.description) for name, op in OPERATIONS.items()})

def build_tools(invoke: Callable, selection=None):
    from agents import FunctionTool

    tools = []
    for name, (schema, description) in REGISTRY.items():

        async def call(ctx, raw, tool_name=name, params=schema):
            if selection is not None and tool_name not in selection.loaded:
                raise ValueError("工具尚未加载")
            validated = params.model_validate_json(raw)
            return await invoke(tool_name, validated.model_dump())

        # Strict mode requires optional fields to be required/nullable; explicit non-strict
        # schema allows conventional OpenAI-compatible servers to honor defaults.
        tools.append(
            FunctionTool(
                name=name,
                description=description,
                params_json_schema=schema.model_json_schema(),
                on_invoke_tool=call,
                strict_json_schema=False,
                is_enabled=(lambda ctx, agent, key=name: key in selection.loaded)
                if selection is not None else True,
            )
        )
    if selection is not None:
        from .tool_catalog import DISCOVERY_NAME, Discovery

        async def discover_call(ctx, raw):
            params = Discovery.model_validate_json(raw)
            result = await invoke(DISCOVERY_NAME, params.model_dump())
            return selection.apply(result)

        tools.append(FunctionTool(
            name=DISCOVERY_NAME,
            description="查找并加载业务工具；按 query 或 domain 查询，每次最多四个工具，使用 offset 翻页。"
                        "空 query 返回完整领域目录，包含查询、写入、附件及 Jupyter 执行。"
                        "无匹配时返回目录；query 也可以填写精确工具名。不授予业务访问权限",
            params_json_schema=Discovery.model_json_schema(),
            on_invoke_tool=discover_call,
            strict_json_schema=False,
        ))
    return tools
