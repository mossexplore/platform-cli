"""训练任务管理与执行记录接口。"""

from __future__ import annotations

from copy import deepcopy
from uuid import uuid4
from typing import Any, Dict, Optional

from ..client import PlatformClient
from ..errors import ApiError, BusinessError, AuthenticationError
from ..downloads import https_url


class TrainService:
    def __init__(self, client: PlatformClient):
        self.client = client

    def start(self, task_id: str) -> Optional[str]:
        """直接启动任务；提交后不触发公共运行时的认证重试。"""
        task_id = task_id.strip()
        if not task_id:
            raise ValueError("taskId 不能为空")
        if not self.client.business_id:
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        try:
            payload = self.client.request(
                "POST", "/ai/backend/modelDev/modelTrain/startScheduleTask",
                json_body={"version": "1.0", "meta": {"uuid": str(uuid4())},
                           "data": {"taskId": task_id}},
            )
        except (ApiError, AuthenticationError) as exc:
            raise ApiError(
                f"训练任务执行请求未能确认结果：{exc}；未自动重试，"
                "请先查询执行记录确认，避免重复启动任务"
            ) from exc
        result = self._config_result(payload, "训练任务执行")
        data = result.get("data")
        job_id = data.get("jobId") if isinstance(data, dict) else None
        return job_id if isinstance(job_id, str) and job_id.strip() else None

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

    def find_task(self, task_id: str,
                  required_fields: tuple[str, ...] = ("businessId", "taskType")) -> Dict[str, Any]:
        task_id = task_id.strip()
        if not task_id:
            raise ValueError("taskId 不能为空")
        page = 1
        seen = set()
        while True:
            result = self.list_tasks(page_index=page)
            for task in result["items"]:
                if task.get("taskId") == task_id:
                    for field in required_fields:
                        if not isinstance(task.get(field), str) or (
                            field != "teamId" and not task[field].strip()
                        ):
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

    def list_instances(self, task: Dict[str, Any], page: int = 1, size: int = 10) -> Dict[str, Any]:
        for field in ("taskId", "businessId", "taskType"):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise ApiError(f"训练任务缺少有效的 {field}")
        payload = self.client.request(
            "POST", "/ai/backend/mtp/traintask/queryJobInstanceByTaskId",
            json_body={
                "taskId": task["taskId"], "businessId": task["businessId"],
                "jobType": task["taskType"], "pageIndex": page, "pageSize": size,
                "sortField": "createTime", "sortOrder": "ascend",
            },
        )
        return self._page(self._result(payload), "jobs", page, size)

    def all_instances(self, task: Dict[str, Any]) -> list[Dict[str, Any]]:
        """分页取全并拒绝重复页，避免遗漏或重复取消。"""
        items: list[Dict[str, Any]] = []
        seen: set[str] = set()
        page = 1
        while True:
            result = self.list_instances(task, page)
            batch = result["items"]
            for item in batch:
                job_id = item.get("jobId")
                task_name = item.get("taskName")
                if not isinstance(job_id, str) or not job_id.strip():
                    raise ApiError("执行实例缺少有效的 jobId")
                if not isinstance(task_name, str) or not task_name.strip():
                    raise ApiError(f"执行实例 {job_id} 缺少有效的 taskName")
                if job_id in seen:
                    raise ApiError(f"执行实例分页重复返回 jobId：{job_id}")
                seen.add(job_id)
                items.append(item)
            if len(items) >= result["count"]:
                return items
            if not batch:
                raise ApiError("执行实例分页提前结束，无法确认完整列表")
            page += 1

    def cancel_instance(self, task_id: str, job_id: str, task_name: str) -> str:
        from ..errors import AuthenticationError
        try:
            payload = self.client.request(
                "POST", "/ai/backend/mtp/train/cancelMultiInstanceTask",
                json_body={"version": "1.0", "meta": {"uuid": str(uuid4())},
                           "data": {"taskId": task_id, "jobId": job_id},
                           "eventTarget": task_name},
            )
        except AuthenticationError as exc:
            raise ApiError(f"取消执行实例 {job_id} 的结果未能确认：{exc}；请查询实例状态") from exc
        result = self._action_result(payload, "取消执行实例")
        return str(result.get("des") or "")

    def delete_task(self, task: Dict[str, Any]) -> None:
        for field in ("taskId", "teamId", "taskName"):
            if not isinstance(task.get(field), str) or (field != "teamId" and not task[field].strip()):
                raise ApiError(f"训练任务缺少有效的 {field}")
        try:
            payload = self.client.request(
                "POST", "/ai/backend/modelDev/modelTrain/v2/delete",
                json_body={"taskId": task["taskId"], "teamId": task["teamId"],
                           "target": task["taskName"], "softDeleteFlag": True},
            )
        except AuthenticationError as exc:
            raise ApiError(f"删除训练任务结果未能确认：{exc}；请查询任务列表") from exc
        self._action_result(payload, "删除训练任务")

    def clone_detail(self, task: Dict[str, Any]) -> Dict[str, Any]:
        if not isinstance(task.get("teamId"), str):
            raise ApiError("训练任务缺少有效的 teamId")
        payload = self.client.request(
            "POST", "/ai/backend/modelDev/modelTrain/detailNew",
            json_body={"data": {"id": task["taskId"],
                                "businessId": self.client.business_id,
                                "teamId": task["teamId"]}},
        )
        result = self._action_result(payload, "获取训练任务详情")
        detail = result.get("data")
        if not isinstance(detail, dict):
            raise ApiError("获取训练任务详情失败：缺少有效的 result.data")
        return detail

    def clone_task(self, detail: Dict[str, Any], name: str,
                   customize_config: Optional[str]) -> Optional[str]:
        if not name.strip():
            raise ValueError("克隆后新任务名称不能为空")
        data = deepcopy(detail)
        info = data.get("taskInfo")
        if not isinstance(info, dict) or not isinstance(info.get("baseInfo"), dict):
            raise ApiError("训练任务详情缺少有效的 taskInfo.baseInfo")
        data["name"] = name
        info["baseInfo"]["taskName"] = name
        if customize_config is not None:
            if info.get("parameter") is None:
                info["parameter"] = {}
            if not isinstance(info["parameter"], dict):
                raise ApiError("训练任务详情的 taskInfo.parameter 不是对象")
            info["parameter"]["customizeConfig"] = customize_config
        try:
            payload = self.client.request(
                "POST", "/ai/backend/modelDev/modelTrain/createNew",
                json_body={"data": data},
            )
        except AuthenticationError as exc:
            raise ApiError(f"克隆训练任务结果未能确认：{exc}；请查询任务列表") from exc
        result = self._action_result(payload, "克隆训练任务")
        created = result.get("data")
        return created.get("id") if isinstance(created, dict) and isinstance(created.get("id"), str) else None

    @staticmethod
    def _action_result(payload: Any, action: str) -> Dict[str, Any]:
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError(f"{action}失败：响应缺少 result")
        if type(result.get("code")) is not int or result["code"] != 0:
            raise ApiError(f"{action}失败：code={result.get('code')}，des={result.get('des')}")
        return result

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

    def update_config(self, task_id: str, customize_config: str, update_user: str) -> None:
        if not task_id.strip():
            raise ValueError("taskId 不能为空")
        if not self.client.business_id:
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        if not update_user.strip():
            raise BusinessError("当前环境 business.json 缺少 username，请运行 ml login 或 ml business refresh")
        detail_payload = self.client.request(
            "POST", "/ai/backend/modelDev/modelTrain/detailNew",
            json_body={"data": {"id": task_id, "businessId": self.client.business_id, "teamId": ""}},
        )
        detail_result = self._config_result(detail_payload, "获取训练任务详情")
        detail = detail_result.get("data")
        if not isinstance(detail, dict) or not isinstance(detail.get("taskInfo"), dict):
            raise ApiError("获取训练任务详情失败：缺少有效的 data.taskInfo")
        if not isinstance(detail.get("name"), str):
            raise ApiError("获取训练任务详情失败：缺少有效的 data.name")
        task_info = deepcopy(detail["taskInfo"])
        if task_info.get("parameter") is None:
            task_info["parameter"] = {}
        if not isinstance(task_info["parameter"], dict):
            raise ApiError("获取训练任务详情失败：taskInfo.parameter 不是对象")
        task_info["parameter"]["customizeConfig"] = customize_config
        task_info["updateUser"] = update_user
        payload = self.client.request(
            "POST", "/ai/backend/modelDev/modelTrain/updateNew",
            json_body={"data": {
                "id": task_id, "businessId": self.client.business_id, "name": detail["name"],
                "creator": "", "modifier": "",
                "taskInfo": task_info,
            }},
        )
        self._config_result(payload, "更新训练任务自定义参数")

    @staticmethod
    def _config_result(payload: Any, action: str) -> Dict[str, Any]:
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError(f"{action}失败：响应缺少 result")
        if type(result.get("code")) is not int or result["code"] != 0 or result.get("des") != "success":
            raise ApiError(f"{action}失败：code={result.get('code')}，des={result.get('des')}")
        return result

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
