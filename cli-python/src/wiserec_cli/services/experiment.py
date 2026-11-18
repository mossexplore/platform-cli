"""离线实验接口。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

from ..client import PlatformClient
from ..errors import ApiError, BusinessError


EXPERIMENT_FIELDS = (
    "projectId",
    "projectName",
    "description",
    "createUser",
    "updateUser",
    "createTime",
    "updateTime",
    "configName",
)

TRIAL_FIELDS = (
    "experimentName",
    "experimentType",
    "creator",
    "updater",
    "createTime",
    "updateTime",
    "cronIntervalStartFlag",
    "description",
)


class ExperimentService:
    def __init__(self, client: PlatformClient):
        self.client = client

    def list_projects(
        self,
        page_index: int = 1,
        page_size: int = 10,
        project_name: Optional[str] = None,
        description: Optional[str] = None,
        create_user: Optional[str] = None,
        update_user: Optional[str] = None,
        team_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询当前业务上下文中的离线实验。"""
        if page_index < 1:
            raise ValueError("page 必须大于等于 1")
        if page_size < 1:
            raise ValueError("page-size 必须大于等于 1")
        if not self.client.business_id:
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")

        params: Dict[str, Any] = {
            "businessId": self.client.business_id,
            "pageIndex": page_index,
            "pageSize": page_size,
        }
        optional_params = {
            "projectName": project_name,
            "description": description,
            "createUser": create_user,
            "updateUser": update_user,
            "teamId": team_id,
        }
        params.update(
            {
                key: value
                for key, value in optional_params.items()
                if value is not None
            }
        )

        payload = self.client.request(
            "GET",
            "/ai/backend/experiment/project/list",
            params=params,
            headers={"businessid": self.client.business_id},
        )
        return self._parse_list_response(payload, page_index, page_size)

    def list_trials(
        self,
        project_id: str,
        page_index: int = 1,
        page_size: int = 10,
        experiment_name: Optional[str] = None,
        experiment_type: Optional[str] = None,
        creator: Optional[str] = None,
        updater: Optional[str] = None,
        aimodule: Optional[str] = None,
    ) -> Dict[str, Any]:
        """分页查询指定离线实验下的全部 trial。"""
        selected_project_id = project_id.strip()
        if not selected_project_id:
            raise ValueError("projectId 不能为空")
        if page_index < 1:
            raise ValueError("page 必须大于等于 1")
        if page_size < 1:
            raise ValueError("page-size 必须大于等于 1")
        self._require_business_selection()

        params: Dict[str, Any] = {
            "businessId": self.client.business_id,
            "pageIndex": page_index,
            "pageSize": page_size,
            "projectId": selected_project_id,
        }
        optional_params = {
            "experimentNameRef": experiment_name,
            "experimentType": experiment_type,
            "creator": creator,
            "updater": updater,
            "aimodule": aimodule,
        }
        params.update(
            {
                key: value
                for key, value in optional_params.items()
                if value is not None
            }
        )
        payload = self.client.request(
            "GET",
            "/ai/backend/experiment",
            params=params,
            headers={"businessid": self.client.business_id},
        )
        return self._parse_trial_list_response(payload, page_index, page_size)

    def get_project(self, project_id: str) -> Dict[str, Any]:
        """按 projectId 查询当前业务上下文中的实验详情。"""
        selected_id = project_id.strip()
        if not selected_id:
            raise ValueError("projectId 不能为空")
        self._require_business_selection()

        payload = self.client.request(
            "GET",
            f"/ai/backend/experiment/project/{quote(selected_id, safe='')}",
            params={"businessId": self.client.business_id},
            headers={"businessid": self.client.business_id},
        )
        detail = self._result_data(payload, "查询实验详情", dict)
        if str(detail.get("projectId") or "") != selected_id:
            raise ApiError("实验详情响应中的 projectId 与查询条件不一致")
        if str(detail.get("businessId") or "") != self.client.business_id:
            raise BusinessError(
                "源实验不属于当前业务上下文，请切换租户或团队后重试"
            )
        return detail

    def build_clone_request(
        self,
        detail: Dict[str, Any],
        project_name: str,
        request_uuid: str,
    ) -> Dict[str, Any]:
        """根据实验详情构造仅修改名称的创建请求。"""
        selected_name = project_name.strip()
        if not selected_name:
            raise ValueError("克隆后的实验名称不能为空")
        if not request_uuid:
            raise ValueError("请求 UUID 不能为空")
        if not self.client.username:
            raise ApiError("当前认证信息缺少登录账号")
        if str(detail.get("businessId") or "") != self.client.business_id:
            raise BusinessError(
                "源实验不属于当前业务上下文，请切换租户或团队后重试"
            )

        return {
            "version": "1.0",
            "meta": {"uuid": request_uuid},
            "data": {
                "projectId": "",
                "projectName": selected_name,
                "description": detail.get("description") or "",
                "businessId": detail.get("businessId") or "",
                "region": detail.get("region") or "",
                "subDomain": detail.get("subDomain") or "",
                "serviceChannel": detail.get("serviceChannel") or "",
                "teamId": detail.get("teamId") or "",
                "clusterName": detail.get("clusterName") or "",
                "configId": detail.get("configId") or "",
                "configName": detail.get("configName") or "",
                "createUser": self.client.username,
                "updateUser": self.client.username,
            },
        }

    def create_project(self, request_body: Dict[str, Any]) -> Dict[str, Any]:
        """同步创建克隆后的离线实验。"""
        self._require_business_selection()
        data = request_body.get("data")
        if not isinstance(data, dict):
            raise ValueError("创建实验请求缺少 data")
        if str(data.get("businessId") or "") != self.client.business_id:
            raise BusinessError("创建实验请求中的 businessId 与当前业务上下文不一致")

        payload = self.client.request(
            "POST",
            "/ai/backend/experiment/project",
            json_body=request_body,
            headers={"businessid": self.client.business_id},
        )
        self._result(payload, "克隆实验")
        return payload

    def _require_business_selection(self) -> None:
        if not self.client.business_id:
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")

    @staticmethod
    def _result(payload: Any, action: str) -> Dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(
            payload.get("result"), dict
        ):
            raise ApiError(f"{action}响应缺少 result")
        result = payload["result"]
        if result.get("code") != 0:
            description = str(result.get("des") or "未知错误")
            raise ApiError(
                f"{action}失败: {description} (code={result.get('code')})"
            )
        return result

    @classmethod
    def _result_data(
        cls,
        payload: Any,
        action: str,
        expected_type: type,
    ) -> Any:
        result = cls._result(payload, action)
        data = result.get("data")
        if not isinstance(data, expected_type):
            raise ApiError(f"{action}响应中的 result.data 格式错误")
        return data

    @staticmethod
    def _parse_list_response(
        payload: Any,
        page_index: int,
        page_size: int,
    ) -> Dict[str, Any]:
        result = ExperimentService._result(payload, "查询离线实验")
        data = result.get("data")
        if not isinstance(data, list):
            raise ApiError("离线实验列表响应中的 result.data 不是数组")

        items: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            items.append({field: item.get(field, "") for field in EXPERIMENT_FIELDS})

        return {
            "pageIndex": page_index,
            "pageSize": page_size,
            "count": result.get("count", len(items)),
            "total": result.get("total", len(items)),
            "items": items,
        }

    @staticmethod
    def _parse_trial_list_response(
        payload: Any,
        page_index: int,
        page_size: int,
    ) -> Dict[str, Any]:
        result = ExperimentService._result(payload, "查询离线实验 trial")
        data = result.get("data")
        if not isinstance(data, list):
            raise ApiError("离线实验 trial 列表响应中的 result.data 不是数组")

        items: List[Dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            items.append({field: item.get(field, "") for field in TRIAL_FIELDS})

        return {
            "pageIndex": page_index,
            "pageSize": page_size,
            "count": result.get("count", len(items)),
            "total": result.get("total", len(items)),
            "items": items,
        }
