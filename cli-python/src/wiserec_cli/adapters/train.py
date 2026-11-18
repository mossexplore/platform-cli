"""MLOps 训练列表协议。"""
from ..errors import ApiError, BusinessError


def list_mlops(client, page_index=1, page_size=10, task_name=None):
    if not 1 <= page_size <= 200 or page_index < 1:
        raise ValueError("page 必须大于等于 1，page-size 必须为 1 到 200")
    if not client.business_id:
        raise BusinessError("尚未选择租户或团队，请运行 ml business use")
    body = dict.fromkeys((
        "cronFlag", "depTask", "scene", "subScene", "teamId", "noRunDays",
        "createUser", "updateUser", "trainEngine", "trainMode", "distFramework",
        "isDeleted", "region", "scope", "inputName", "algorithmName", "algoInputName",
        "algorithmVersion", "taskOwner", "imagePackageId", "bucketName", "inputTaskId",
        "taskStr", "inputJobId", "jobStr", "customLabels", "taskId", "jobId",
    ), "")
    body.update(taskName=task_name or "", taskType=None, taskType1="mtp-all",
                businessId=client.business_id, category="mtp-all", tags=None,
                pageIndex=page_index, pageSize=page_size)
    for key in ("noticeTime", "updateNoticeTime", "jobStatus", "taskTags"):
        body[key] = []
    for key in ("private", "baseInfo", "external", "sharing", "running", "excludeSpecFlag"):
        body[key] = False
    for key in ("beginTime", "endTime", "updateBeginTime", "updateEndTime"):
        body[key] = None
    payload = client.request("POST", "/ai/backend/mtp/traintask/queryList", json_body=body)
    result = payload.get("result") if isinstance(payload, dict) else None
    if not isinstance(result, dict) or type(result.get("code")) is not int or result["code"] != 0:
        raise ApiError("查询训练任务失败：" + str(result))
    if type(result.get("count")) is not int or result["count"] < 0:
        raise ApiError("训练列表响应缺少有效的 count")
    # 成功且总数为零即为空结果，服务端可省略 taskInfos 或返回 null。
    if result["count"] == 0:
        return dict(count=0, pageIndex=page_index, pageSize=page_size, items=[])
    items = result.get("taskInfos")
    if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
        raise ApiError("训练列表响应缺少有效的 taskInfos")
    return dict(count=result["count"], pageIndex=page_index, pageSize=page_size, items=items)
