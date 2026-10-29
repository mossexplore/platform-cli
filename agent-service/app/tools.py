"""Explicit function schemas; no generic HTTP or shell escape hatch."""

from typing import Callable
from pydantic import BaseModel, ConfigDict, Field


class Params(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(Params):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=10, ge=1, le=100)


class Search(Page):
    name: str = Field(default="", max_length=200)


class ModelID(Params):
    model_id: str = Field(min_length=1, max_length=128)


class TaskID(Params):
    task_id: str = Field(min_length=1, max_length=128)


class Instances(TaskID, Page):
    pass


class ServiceSearch(Search):
    model_name: str | None = Field(default=None, max_length=200)


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


REGISTRY = {
    "list_models": (
        Search,
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
        "查询已验证主机与文件的尾部日志，支持关键词；不支持精确起止时间过滤",
    ),
}


def build_tools(invoke: Callable):
    from agents import FunctionTool

    tools = []
    for name, (schema, description) in REGISTRY.items():

        async def call(ctx, raw, tool_name=name, params=schema):
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
            )
        )
    return tools
