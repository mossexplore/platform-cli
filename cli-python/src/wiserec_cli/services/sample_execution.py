"""新版样本任务执行周期与执行记录。"""
import re
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from ..errors import ApiError, BusinessError

STATES = {
    "INIT": "初始化", "CANCELED": "已取消", "QUEUE": "排队中",
    "APPLY_FOR_RESOURCE": "申请资源", "WAIT_FOR_QUOTA_QUEUE": "等待中",
    "RUNNING": "运行中", "COMPLETED": "运行成功", "FAILED": "执行失败",
    "LACK_RESOURCE": "资源不足", "TIMEOUT": "超时", "QUEUE_TIMEOUT": "排队超时",
    "QUOTA_WAIT_TIMEOUT": "配额等待失败", "FORCE_STOP": "强制停止",
}
BEIJING = timezone(timedelta(hours=8))


def parse_time(value):
    if value is None:
        return None
    try:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value):
            raise ValueError()
        return int(datetime.strptime(value, "%Y-%m-%d %H:%M:%S").replace(tzinfo=BEIJING).timestamp() * 1000)
    except (ValueError, OverflowError, OSError) as exc:
        raise ValueError("时间必须为有效的北京时间，格式 YYYY-MM-DD HH:mm:ss") from exc


def validate_options(task_id, page, page_size, start_time=None, end_time=None, states=None):
    if not task_id.strip():
        raise ValueError("taskId 不能为空")
    if any(type(v) is not int or v < 1 for v in (page, page_size)):
        raise ValueError("page 和 page-size 必须为正整数")
    start, end = parse_time(start_time), parse_time(end_time)
    if start is not None and end is not None and start > end:
        raise ValueError("start-time 不得晚于 end-time")
    if any(s not in STATES for s in (states or [])):
        raise ValueError("state 仅支持: " + ", ".join(STATES))
    return start, end


class SampleExecutionService:
    def __init__(self, client):
        self.client = client

    def _query(self, path, body, field, task_id, page, page_size):
        if not self.client.business_id.strip():
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        payload = self.client.request("POST", path, json_body=body)
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError("样本任务执行查询响应缺少有效的 result")
        if type(result.get("code")) is not int or result["code"] != 0:
            raise ApiError(f"样本任务执行查询失败: {result.get('des') or '未知错误'} (code={result.get('code')})")
        items, count = result.get(field), result.get("count")
        if not isinstance(items, list) or not all(isinstance(i, dict) for i in items):
            raise ApiError(f"样本任务执行查询响应缺少有效的 {field} 数组")
        if type(count) is not int or count < 0:
            raise ApiError("样本任务执行查询响应缺少有效的 count")
        return {"taskId": task_id.strip(), "page": page, "pageSize": page_size,
                "total": count, "items": items}

    def list_periods(self, task_id, page=1, page_size=20, start_time=None, end_time=None, states=None):
        start, end = validate_options(task_id, page, page_size, start_time, end_time, states)
        data = {"businessId": self.client.business_id, "taskId": task_id.strip(),
                "latestFlag": True, "sortField": "periodDate", "pageIndex": page,
                "pageSize": page_size, "taskClass": 3}
        if start is not None:
            data["periodStartTime"] = start
        if end is not None:
            data["periodEndTime"] = end
        if states:
            data["states"] = list(dict.fromkeys(states))
        return self._query("/ai/backend/dpp/proxy/schedule-service/task/instances/query",
                           {"version": "1.0", "meta": {"uuid": str(uuid4())}, "data": data},
                           "instances", task_id, page, page_size)

    def list_executions(self, task_id, page=1, page_size=10, include_history=False):
        validate_options(task_id, page, page_size)
        return self._query("/ai/backend/dpp/featuretask/queryScheduleTaskList", {
            "pageIndex": page, "pageSize": page_size, "taskId": task_id.strip(),
            "source": "history", "latestFlag": "all" if include_history else "true",
        }, "jobs", task_id, page, page_size)
