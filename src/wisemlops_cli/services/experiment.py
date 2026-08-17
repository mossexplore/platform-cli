"""离线实验接口。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..client import PlatformClient
from ..errors import ApiError, BusinessError


EXPERIMENT_FIELDS = (
    "projectName",
    "description",
    "createUser",
    "updateUser",
    "createTime",
    "updateTime",
    "configName",
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
        )
        return self._parse_list_response(payload, page_index, page_size)

    @staticmethod
    def _parse_list_response(
        payload: Any,
        page_index: int,
        page_size: int,
    ) -> Dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(
            payload.get("result"), dict
        ):
            raise ApiError("离线实验列表响应缺少 result")

        result = payload["result"]
        if result.get("code") != 0:
            description = str(result.get("des") or "未知错误")
            raise ApiError(
                f"查询离线实验失败: {description} (code={result.get('code')})"
            )
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
