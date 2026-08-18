"""训练看板（SwanBoard）接口。"""

from __future__ import annotations

from typing import Any, Dict, List
from urllib.parse import quote

from ..client import PlatformClient
from ..errors import ApiError, BusinessError


class SwanBoardService:
    def __init__(self, client: PlatformClient):
        self.client = client

    def list_projects(
        self,
        page_num: int = 1,
        page_size: int = 10,
        team_id: str = "",
        creator: str = "",
    ) -> Dict[str, Any]:
        self._validate_page(page_num, page_size)
        self._require_business_selection()
        payload = self.client.request(
            "POST",
            "/ai/backend/mtp/swanboard/project/list",
            json_body={
                "pageNum": page_num,
                "pageSize": page_size,
                "businessId": self.client.business_id,
                "teamId": team_id,
                "creator": creator,
            },
            headers={"businessid": self.client.business_id},
        )
        return self._list_response(payload, "查询训练看板项目", page_num, page_size)

    def list_namespaces(self, project_id: str, team_id: str = "") -> Dict[str, Any]:
        selected_project_id = self._identifier(project_id, "projectId")
        self._require_business_selection()
        payload = self.client.request(
            "GET",
            "/ai/backend/mtp/swanboard/namespace/query/"
            f"{quote(selected_project_id, safe='')}",
            params={
                "projectId": selected_project_id,
                "teamId": team_id,
                "businessId": self.client.business_id,
            },
            headers={"businessid": self.client.business_id},
        )
        return self._list_response(payload, "查询训练看板项目空间")

    def list_experiments(
        self,
        project_id: str,
        namespace_id: str,
        team_id: str = "",
    ) -> Dict[str, Any]:
        selected_project_id = self._identifier(project_id, "projectId")
        selected_namespace_id = self._identifier(namespace_id, "namespaceId")
        self._require_business_selection()
        payload = self.client.request(
            "POST",
            "/ai/backend/mtp/swanboard/experiment/page",
            json_body={
                "projectId": selected_project_id,
                "teamId": team_id,
                "businessId": self.client.business_id,
                "namespaceId": selected_namespace_id,
            },
            headers={"businessid": self.client.business_id},
        )
        result = self._result(payload, "查询训练看板实验")
        data = result.get("data")
        if not isinstance(data, dict) or not isinstance(data.get("list"), list):
            raise ApiError("训练看板实验列表响应中的 result.data.list 不是数组")
        return {
            "pageNum": data.get("pageNum"),
            "pageSize": data.get("pageSize"),
            "total": data.get("total", len(data["list"])),
            "totalPages": data.get("totalPages"),
            "items": [item for item in data["list"] if isinstance(item, dict)],
        }

    def list_features(
        self,
        experiment_id: str,
        page_index: int = 1,
        page_size: int = 10,
    ) -> Dict[str, Any]:
        selected_experiment_id = self._identifier(experiment_id, "experimentId")
        self._validate_page(page_index, page_size)
        self._require_business_selection()
        payload = self.client.request(
            "GET",
            "/ai/backend/mtp/swanboard/experiment/"
            f"{quote(selected_experiment_id, safe='')}/feature",
            params={
                "experimentId": selected_experiment_id,
                "businessId": self.client.business_id,
                "pageIndex": page_index,
                "pageSize": page_size,
            },
            headers={"businessid": self.client.business_id},
        )
        return self._list_response(payload, "查询训练看板实验特性", page_index, page_size)

    def get_environment(self, experiment_id: str) -> Dict[str, Any]:
        selected_experiment_id = self._identifier(experiment_id, "experimentId")
        self._require_business_selection()
        payload = self.client.request(
            "GET",
            "/ai/backend/mtp/swanboard/label/experiment/"
            f"{quote(selected_experiment_id, safe='')}",
            params={
                "experimentId": selected_experiment_id,
                "businessId": self.client.business_id,
            },
            headers={"businessid": self.client.business_id},
        )
        return self._data(payload, "查询训练看板实验环境", dict)

    def get_metric_stats(self, experiment_id: str, tag: str) -> Dict[str, Any]:
        selected_experiment_id = self._identifier(experiment_id, "experimentId")
        selected_tag = self._identifier(tag, "指标名称")
        self._require_business_selection()
        payload = self.client.request(
            "GET",
            "/ai/backend/mtp/swanboard/tag/experiment/"
            f"{quote(selected_experiment_id, safe='')}/"
            f"{quote(selected_tag, safe='')}/stats",
            params={"businessId": self.client.business_id},
            headers={"businessid": self.client.business_id},
        )
        return self._data(payload, f"查询训练看板指标 {selected_tag}", dict)

    def get_config(self, experiment_id: str) -> Dict[str, Any]:
        selected_experiment_id = self._identifier(experiment_id, "experimentId")
        self._require_business_selection()
        payload = self.client.request(
            "GET",
            "/ai/backend/mtp/swanboard/experiment/"
            f"{quote(selected_experiment_id, safe='')}/config",
            params={"businessId": self.client.business_id},
            headers={"businessid": self.client.business_id},
        )
        return self._data(payload, "查询训练看板实验配置", dict)

    def inspect_experiment(self, experiment_id: str) -> Dict[str, Any]:
        """查询实验的特性、环境、默认指标和配置。"""
        return {
            "features": self.list_features(experiment_id),
            "environment": self.get_environment(experiment_id),
            "metrics": [
                self.get_metric_stats(experiment_id, "loss"),
                self.get_metric_stats(experiment_id, "accuracy"),
            ],
            "config": self.get_config(experiment_id),
        }

    def _require_business_selection(self) -> None:
        if not self.client.business_id:
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")

    @staticmethod
    def _identifier(value: str, field: str) -> str:
        selected = value.strip()
        if not selected:
            raise ValueError(f"{field} 不能为空")
        return selected

    @staticmethod
    def _validate_page(page: int, page_size: int) -> None:
        if page < 1:
            raise ValueError("page 必须大于等于 1")
        if page_size < 1:
            raise ValueError("page-size 必须大于等于 1")

    @staticmethod
    def _result(payload: Any, action: str) -> Dict[str, Any]:
        if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
            raise ApiError(f"{action}响应缺少 result")
        result = payload["result"]
        if result.get("code") != 0:
            raise ApiError(
                f"{action}失败: {result.get('des') or '未知错误'} "
                f"(code={result.get('code')})"
            )
        return result

    @classmethod
    def _data(cls, payload: Any, action: str, expected_type: type) -> Any:
        data = cls._result(payload, action).get("data")
        if not isinstance(data, expected_type):
            raise ApiError(f"{action}响应中的 result.data 格式错误")
        return data

    @classmethod
    def _list_response(
        cls,
        payload: Any,
        action: str,
        page: int = 1,
        page_size: int = 0,
    ) -> Dict[str, Any]:
        result = cls._result(payload, action)
        data = result.get("data")
        if not isinstance(data, list):
            raise ApiError(f"{action}响应中的 result.data 不是数组")
        items: List[Dict[str, Any]] = [item for item in data if isinstance(item, dict)]
        return {
            "page": page,
            "pageSize": page_size,
            "count": result.get("count", len(items)),
            "items": items,
        }
