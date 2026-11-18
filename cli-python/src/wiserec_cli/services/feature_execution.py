"""特征任务执行记录和日志接口。"""
from uuid import uuid4

from ..errors import ApiError, BusinessError


def positive(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(f"{name} 必须为正整数")


def validate_log_options(job_id, start_line, end_line, keywords, scope, scope_lines):
    if not job_id.strip():
        raise ValueError("jobId 不能为空")
    positive(start_line, "start-line")
    positive(end_line, "end-line")
    if end_line < start_line:
        raise ValueError("end-line 不得小于 start-line")
    if keywords is not None and any(not isinstance(k, str) or not k.strip() for k in keywords):
        raise ValueError("keyword 不能为空白字符串")
    if scope is not None and scope not in {"A", "B", "C"}:
        raise ValueError("scope 仅支持 A、B、C")
    if scope_lines is not None:
        positive(scope_lines, "scope-lines")


class FeatureExecutionService:
    def __init__(self, client):
        self.client = client

    def request(self, path, body):
        if not self.client.business_id.strip():
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        payload = self.client.request("POST", path, json_body=body)
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError("特征任务执行记录接口响应缺少有效的 result")
        if type(result.get("code")) is not int or result["code"] != 0:
            raise ApiError(f"特征任务执行记录接口失败: {result.get('des') or '未知错误'} (code={result.get('code')})")
        return payload

    def list_executions(self, task_id, page=1, page_size=10, include_history=False):
        if not task_id.strip():
            raise ValueError("taskId 不能为空")
        positive(page, "page")
        positive(page_size, "page-size")
        payload = self.request("/ai/backend/dpp/featuretask/queryScheduleTaskList", {
            "pageIndex": page, "pageSize": page_size, "taskId": task_id.strip(),
            "source": "history", "latestFlag": "all" if include_history else "true",
        })
        result = payload["result"]
        items, count = result.get("jobs"), result.get("count")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiError("执行记录响应缺少有效的 jobs 数组")
        if type(count) is not int or count < 0:
            raise ApiError("执行记录响应缺少有效的 count")
        return {"items": items, "count": count, "pageIndex": page, "pageSize": page_size}

    def search_logs(self, job_id, start_line=1, end_line=2000, keywords=None,
                    scope=None, scope_lines=None):
        validate_log_options(job_id, start_line, end_line, keywords, scope, scope_lines)
        data = {"jobId": job_id.strip(), "businessId": self.client.business_id,
                "searchStartLine": start_line, "searchEndLine": end_line}
        if keywords:
            data["keywords"] = list(keywords)
        if scope is not None:
            data["searchScope"] = scope
        if scope_lines is not None:
            data["searchScopeLine"] = scope_lines
        return self.request("/ai/backend/mtp/traintask/advancedLogSearch", {
            "version": "1.0", "meta": {"uuid": str(uuid4())}, "data": data,
        })
