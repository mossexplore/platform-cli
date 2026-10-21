"""新旧样本任务列表接口。"""
from uuid import uuid4

from ..errors import ApiError, BusinessError

LEGACY_TYPES = {
    "feature_preprocess_realtime": "特征预处理(实时)",
    "feature_preprocess_offline": "特征预处理(离线)",
    "feature_assemble": "特征装配",
    "label_assemble": "标签装配",
    "feature_monitor": "样本监控",
    "new_feature_assemble": "新特征装配",
    "spark_jar": "spark_jar",
}
NEW_TYPES = {
    "FEATURE_ASSEMBLE": "特征装配任务",
    "LABEL_ASSEMBLE": "标签装配任务",
    "FEATURE_SYNC": "特征同步任务",
    "FEATURE_IMPORT_OFFLINE": "离线特征导入任务",
    "FEATURE_IMPORT_REALTIME": "实时特征导入任务",
    "OFFLINE_FEATURE_SYNC": "离线特征回流同步任务",
    "FEATURE_PREPROCESS_OFFLINE": "预处理任务",
    "FEATURE_QUALITY_MONITOR": "监控任务",
    "OFFLINE_FEEDBACK": "离线回流任务",
    "REAL_TIME_FEEDBACK": "实时回流任务",
    "REALTIME_LABEL_CALC": "实时标签计算任务",
    "SAMPLE_GENERATION_OFFLINE": "样本生成离线任务",
    "SAMPLE_GENERATION_REALTIME": "样本生成实时任务",
}
DEFAULT_CATEGORY = "feature_preprocess_realtime,feature_preprocess_offline,feature_assemble,label_assemble"


def validate_options(source, page, page_size, types, status, sort):
    if source not in {"legacy", "new"}:
        raise ValueError("source 仅支持 legacy 或 new")
    if any(type(v) is not int or v < 1 for v in (page, page_size)):
        raise ValueError("page 和 page-size 必须为正整数")
    if source == "new" and status is not None:
        raise ValueError("新版列表接口不支持 --status 筛选")
    if source == "legacy" and sort is not None:
        raise ValueError("旧版列表接口不支持 --sort")
    if status not in {None, "all", "stopped", "started"}:
        raise ValueError("status 仅支持 all、stopped 或 started")
    if sort not in {None, "desc"}:
        raise ValueError("sort 目前仅支持 desc")
    allowed = NEW_TYPES if source == "new" else LEGACY_TYPES
    if any(value not in allowed for value in (types or [])):
        raise ValueError(f"{source} 的 type 仅支持: " + ", ".join(allowed))


class SampleTaskService:
    def __init__(self, client):
        self.client = client

    def list_tasks(self, *, source="legacy", page=1, page_size=10,
                   name=None, creator=None, updater=None, types=None,
                   status=None, sort=None):
        validate_options(source, page, page_size, types, status, sort)
        if not self.client.business_id.strip():
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        data = {"businessId": self.client.business_id, "pageSize": page_size}
        types = list(dict.fromkeys(types or []))
        if source == "legacy":
            path = "/ai/backend/dpp/proxy/schedule-service/task/list"
            data.update(pageIndex=page, category=",".join(types) if types else DEFAULT_CATEGORY)
            for key, value in (("taskName", name), ("createUser", creator), ("updateUser", updater)):
                if value is not None:
                    data[key] = value
            if status in {"stopped", "started"}:
                data["taskStatusList"] = {"stopped": "STOP", "started": "START"}[status]
        else:
            path = "/ai/backend/dpp/proxy/featureStore/v2/task/list"
            data.update(pageNo=page, sortType=sort or "desc", taskName=name or "",
                        createBy=creator or "", updateBy=updater or "")
            if types:
                data["taskSubCategoryList"] = types
        payload = self.client.request("POST", path, json_body={
            "version": "1.0", "meta": {"uuid": str(uuid4())}, "data": data,
        })
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError("样本任务查询响应缺少有效的 result")
        if type(result.get("code")) is not int or result["code"] != 0:
            raise ApiError(f"样本任务查询失败: {result.get('des') or '未知错误'} (code={result.get('code')})")
        if source == "legacy":
            items, total = result.get("taskInfos"), result.get("count")
        else:
            body = result.get("data")
            if not isinstance(body, dict):
                raise ApiError("样本任务查询响应缺少有效的 data")
            items, total = body.get("list"), body.get("total")
            if isinstance(items, list):
                items = [item for group in items for item in (group if isinstance(group, list) else [group])]
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiError("样本任务查询响应缺少有效的任务数组")
        if type(total) is not int or total < 0:
            raise ApiError("样本任务查询响应缺少有效的总数")
        return {"source": source, "page": page, "pageSize": page_size, "total": total, "items": items}
