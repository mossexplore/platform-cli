"""Server-owned discovery catalog; never imports tools named by model output."""

from dataclasses import dataclass
from typing import Literal
from pydantic import Field
from .tools import Params, REGISTRY


@dataclass(frozen=True)
class Domain:
    description: str
    names: tuple[str, ...]
    keywords: tuple[str, ...]


DOMAINS = {
    "models": Domain("模型查询、详情、来源和关联训练", (
        "list_models", "get_model", "get_model_source", "get_model_training",
    ), ("模型", "model", "溯源")),
    "training": Domain("训练任务、执行实例和历史记录", (
        "list_train_tasks", "get_train_task", "list_train_instances", "list_train_history",
    ), ("训练", "train", "task", "任务", "执行记录", "实例")),
    "services": Domain("服务查询、主机和部署视图", (
        "list_services", "list_service_hosts", "get_service_deployments",
    ), ("服务", "service", "主机", "host", "pod", "部署")),
    "logs": Domain("验证服务主机后查询日志文件与日志内容", (
        "list_service_log_files", "search_service_logs",
    ), ("日志", "log", "报错")),
}

from .business_tools import OPERATIONS
KEYWORDS = {'algorithms': ('算法', 'algorithm'), 'datasets': ('数据集', 'dataset'),
    'templates': ('部署模板',), 'resources': ('资源模板',), 'offline': ('离线实验', 'offline'),
    'featuresets': ('特征集', 'featureset'), 'mep': ('mep',), 'account': ('用户信息',),
    'feature_tasks': ('特征任务',), 'samples': ('样本', 'sample'), 'swanboard': ('swanboard', '训练看板'),
    'webstudio': ('webstudio', '开发环境'), 'inference': ('推理测试',),
    'training_write': ('启动训练', '取消训练', '删除训练', '克隆训练'),
    'training_files': ('训练配置', '训练日志下载'), 'deployment': ('发布模型', '部署模型'),
    'jupyter': ('jupyter', '执行代码', 'notebook'), 'jupyter_files': ('远端文件',),
    'jupyter_terminals': ('终端', 'terminal')}
for key, keywords in KEYWORDS.items():
    names = tuple(name for name, op in OPERATIONS.items() if op.domain == key)
    DOMAINS[key] = Domain(' / '.join(keywords), names, keywords)

DISCOVERY_NAME = "discover_tools"


class Discovery(Params):
    query: str = Field(default="", max_length=200)
    domain: Literal[tuple(DOMAINS)] | None = None
    offset: int = Field(default=0, ge=0, le=100)


def domain_catalog():
    return [{"domain": key, "description": item.description} for key, item in DOMAINS.items()]


def match_domain(query):
    text = query.casefold()
    scores = {key: sum(word in text for word in item.keywords) for key, item in DOMAINS.items()}
    key = max(scores, key=scores.get)
    return key if scores[key] else None


def discover(arguments):
    """Return at most one domain (four tools); unknown requests return the directory."""
    params = Discovery.model_validate(arguments)
    exact = params.query.strip()
    domain = params.domain or match_domain(params.query)
    if not params.domain and exact in REGISTRY:
        names = (exact,)
    else:
        names = DOMAINS[domain].names[params.offset:params.offset + 4] if domain else ()
    return {
        "ok": True,
        "next_offset": params.offset + 4 if domain and params.offset + 4 < len(DOMAINS[domain].names) else None,
        "tools": [{"name": name, "description": REGISTRY[name][1]} for name in names],
        "domains": domain_catalog(),
        "message": "工具候选已找到" if names else "未匹配工具，请选择目录中的 domain；不要据此判断平台能力不存在",
    }


class ToolSelection:
    """A fresh selection per model run, independent of history and other users."""
    def __init__(self, message, limit=16):
        domain = match_domain(message)
        self.limit = limit
        self.loaded = set(DOMAINS[domain].names[:min(4, limit)] if domain else ())

    def apply(self, result):
        if not result.get("ok"):
            return result
        names = {item["name"] for item in result.get("tools", [])}
        if not names <= REGISTRY.keys():
            raise ValueError("发现结果含未注册工具")
        if len(self.loaded | names) > self.limit:
            return {
                "ok": False, "error": "TOOL_LOAD_LIMIT",
                "message": "本轮工具数量达到上限，请按精确工具名发现，或让用户拆分问题；本次未加载新工具",
                "loaded_tools": sorted(self.loaded),
            }
        self.loaded.update(names)
        return {**result, "loaded_tools": sorted(self.loaded),
                "message": result["message"] + "；已加载工具可在下一次模型请求调用"}
