"""当前业务下的特征任务分页查询。"""
from ..errors import ApiError, BusinessError

TASK_TYPES = {
    "dpp-all": "全部",
    "feature_preprocess_realtime": "特征预处理(实时)",
    "train_fi": "FI直连任务",
    "data_sync": "数据同步任务",
    "data-preproc": "数据预处理任务",
    "feature_generate": "特征生成任务",
    "feature_evaluation": "特征评估任务",
    "feature_improve": "特征加工任务",
    "work_flow": "特征工作流任务",
    "feature-push": "特征同步任务",
    "train_spark": "Spark训练任务",
    "train_fi_sync_hdfs": "FI直连同步HDFS任务",
    "train_fi_data_monitor": "FI直连数据监控任务",
    "generate_samples": "样本生成任务",
    "sample-monitor": "样本监控任务",
    "online_storage": "在线存储任务",
    "streaming_feature": "流特征任务",
}


class FeatureTaskService:
    def __init__(self, client):
        self.client = client

    def list_tasks(self, page_index=1, page_size=10, name=None,
                   category="dpp-all", create_user=None):
        if any(type(v) is not int or v < 1 for v in (page_index, page_size)):
            raise ValueError("page 和 page-size 必须为正整数")
        if category not in TASK_TYPES:
            raise ValueError("category 仅支持: " + ", ".join(TASK_TYPES))
        if not self.client.business_id.strip():
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        payload = self.client.request(
            "POST", "/ai/backend/mtp/traintask/queryList", json_body={
                "taskName": name if name is not None else "",
                "taskType": "", "taskType1": "ALL",
                "businessId": self.client.business_id,
                "scene": "", "subScene": "", "cronFlag": "",
                "noticeTime": [], "jobStatus": [], "depTask": "", "teamId": "",
                "noRunDays": "", "createUser": create_user if create_user is not None else "",
                "updateUser": "", "taskTags": [], "trainEngine": "", "tags": [],
                "category": category, "trainMode": "", "distFramework": "",
                "private": False, "reverseTaskTags": [], "reverseTags": [],
                "region": "", "scope": "", "subDataZoneId": "",
                "pageIndex": page_index, "pageSize": page_size, "running": False,
            },
        )
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError("特征任务查询响应缺少有效的 result")
        if type(result.get("code")) is not int or result["code"] != 0:
            raise ApiError(f"特征任务查询失败: {result.get('des') or '未知错误'} (code={result.get('code')})")
        items, count = result.get("taskInfos"), result.get("count")
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiError("特征任务查询响应缺少有效的 taskInfos 数组")
        if type(count) is not int or count < 0:
            raise ApiError("特征任务查询响应缺少有效的 count")
        return {"items": items, "count": count, "pageIndex": page_index, "pageSize": page_size}
