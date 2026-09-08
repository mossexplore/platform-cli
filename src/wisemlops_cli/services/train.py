"""训练任务与执行实例的只读接口。"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..client import PlatformClient
from ..errors import ApiError, BusinessError
from ..downloads import https_url


class TrainService:
    def __init__(self, client: PlatformClient):
        self.client = client

    def list_tasks(
        self, page_index: int = 1, page_size: int = 10,
        task_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        if page_index < 1 or page_size < 1:
            raise ValueError("page 和 page-size 必须大于等于 1")
        if not self.client.business_id:
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        data = {
            "taskName": task_name if task_name is not None else "",
            "taskType": None, "taskType1": "mtp-all",
            "businessId": self.client.business_id,
            "cronFlag": "", "depTask": "", "scene": "", "subScene": "",
            "noticeTime": [], "updateNoticeTime": [], "jobStatus": [],
            "teamId": "", "noRunDays": "", "createUser": "", "updateUser": "",
            "taskTags": [], "trainEngine": "", "trainMode": "",
            "distFramework": "", "tags": None, "reverseTaskTags": [],
            "reverseTags": [], "category": "mtp-all", "private": False,
            "baseInfo": False, "isDeleted": "", "region": "", "scope": "",
            "inputName": "", "algorithmName": "", "algoInputName": "",
            "algorithmVersion": "", "taskOwner": "", "imagePackageId": "",
            "bucketName": "", "taskStr": "", "external": False,
            "inputTaskId": "", "customLabels": "", "sharing": False,
            "beginTime": None, "endTime": None, "updateBeginTime": None,
            "updateEndTime": None, "pageIndex": page_index,
            "pageSize": page_size, "running": False,
            "excludeSpecFlag": False, "taskId": "",
        }
        payload = self.client.request(
            "POST", "/ai/backend/modelDev/modelTrain/list", json_body={"data": data},
        )
        result = self._result(payload)
        return self._page(result.get("data"), "taskInfos", page_index, page_size)

    def find_task(self, task_id: str) -> Dict[str, Any]:
        task_id = task_id.strip()
        if not task_id:
            raise ValueError("taskId 不能为空")
        page = 1
        seen = set()
        while True:
            result = self.list_tasks(page_index=page)
            for task in result["items"]:
                if task.get("taskId") == task_id:
                    for field in ("businessId", "taskType"):
                        if not isinstance(task.get(field), str) or not task[field].strip():
                            raise ApiError(f"训练任务缺少有效的 {field}")
                    return task
            if not result["items"] or page * result["pageSize"] >= result["count"]:
                break
            ids = {item.get("taskId") for item in result["items"]
                   if isinstance(item.get("taskId"), str)}
            if not ids or ids.issubset(seen):
                raise ApiError("训练任务分页未返回新任务，无法继续查找")
            seen.update(ids)
            page += 1
        raise ApiError(f"当前业务下未找到训练任务 {task_id}")

    def list_instances(self, task: Dict[str, Any]) -> Dict[str, Any]:
        for field in ("taskId", "businessId", "taskType"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise ApiError(f"训练任务缺少有效的 {field}")
        payload = self.client.request(
            "POST", "/ai/backend/mtp/traintask/queryJobInstanceByTaskId",
            json_body={
                "taskId": task["taskId"], "businessId": task["businessId"],
                "jobType": task["taskType"], "pageIndex": 1, "pageSize": 10,
                "sortField": "createTime", "sortOrder": "ascend",
            },
        )
        return self._page(self._result(payload), "jobs", 1, 10)

    def list_history(self, task_id: str) -> Dict[str, Any]:
        """直接查询任务执行记录，固定第一页，按创建时间倒序。"""
        task_id = task_id.strip()
        if not task_id:
            raise ValueError("taskId 不能为空")
        if not self.client.business_id:
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        payload = self.client.request(
            "POST", "/ai/backend/mtp/traintask/queryScheduleTaskList",
            json_body={
                "pageIndex": 1, "pageSize": 10, "sortField": "createTime",
                "sortOrder": "descend", "taskId": task_id, "source": "history",
                "latestFlag": "true", "status": [],
            },
        )
        return self._page(self._result(payload), "jobs", 1, 10)

    def update_config(self, task_id: str, customize_config: str, update_user: str, name: str) -> None:
        if not task_id.strip():
            raise ValueError("taskId 不能为空")
        if not self.client.business_id:
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        if not update_user.strip():
            raise BusinessError("当前环境 business.json 缺少 username，请运行 ml login 或 ml business refresh")
        payload = self.client.request(
            "POST", "/ai/backend/modelDev/modelTrain/updateNew",
            json_body={"data": {
                "id": task_id, "businessId": self.client.business_id, "name": name,
                "creator": "", "modifier": "",
                "taskInfo": {"parameter": {"customizeConfig": customize_config},
                             "updateUser": update_user},
            }},
        )
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError("更新训练任务自定义参数失败：响应缺少 result")
        if type(result.get("code")) is not int or result["code"] != 0 or result.get("des") != "success":
            raise ApiError(f"更新训练任务自定义参数失败：code={result.get('code')}，des={result.get('des')}")

    def get_log_url(self, task_id: str, job_id: str) -> str:
        """直接提交用户 ID，由下载地址接口验证其有效性。"""
        payload = self.client.request(
            "GET", "/ai/backend/mtp/traintask/downloadLogUrl",
            params={"jobId": job_id, "taskId": task_id,
                    "businessId": self.client.business_id,
                    "isApplicantPromise": "true"},
            headers={"businessid": self.client.business_id},
        )
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError("无法获取下载日志地址：响应缺少 result")
        summary = f"code={result.get('code')}，des={result.get('des')}"
        if type(result.get("code")) is not int or result["code"] != 0 or result.get("des") != "success":
            raise ApiError(f"无法获取下载日志地址：{summary}")
        try:
            https_url(result.get("url"))
        except ApiError as exc:
            raise ApiError(f"无法获取下载日志地址：{summary}；{exc}") from None
        return result["url"]

    @staticmethod
    def _result(payload: Any) -> Dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
            raise ApiError("查询响应缺少 result")
        result = payload["result"]
        if type(result.get("code")) is not int or result["code"] != 0:
            raise ApiError(f"查询失败: {result.get('des') or '未知错误'} (code={result.get('code')})")
        return result

    @staticmethod
    def _page(data: Any, field: str, page: int, size: int) -> Dict[str, Any]:
        if not isinstance(data, dict) or not isinstance(data.get(field), list):
            raise ApiError(f"查询响应缺少有效的 {field} 数组")
        if not all(isinstance(item, dict) for item in data[field]):
            raise ApiError(f"查询响应中的 {field} 包含无效记录")
        if type(data.get("count")) is not int or data["count"] < 0:
            raise ApiError("查询响应缺少有效的 count")
        return {"count": data["count"], "pageIndex": page,
                "pageSize": size, "items": data[field]}
