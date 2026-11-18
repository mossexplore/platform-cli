"""执行实例日志归档和下载地址协议。"""
from uuid import uuid4

from ..downloads import https_url
from ..errors import ApiError, BusinessError
from .train import TrainService


class RunningLogService:
    def __init__(self, client):
        self.client = client

    def _fields(self, record, names):
        for name in names:
            value = record.get(name)
            if not isinstance(value, str) or not value.strip():
                raise ApiError(f"日志记录缺少有效的 {name}")
        if not self.client.business_id:
            raise BusinessError("尚未选择租户或团队，请运行 ml business use")
        if record['businessId'] != self.client.business_id:
            raise BusinessError("执行实例或日志记录与当前业务不一致，请重新选择业务")

    def _request(self, path, record, names, extra=None):
        self._fields(record, (*names, 'taskName'))
        data = {name: record[name] for name in names}
        data.update(extra or {})
        payload = self.client.request(
            'POST', '/ai/backend/mtp/train/' + path,
            headers={'businessid': self.client.business_id},
            json_body={'version': '1.0', 'meta': {'uuid': str(uuid4())},
                       'data': data, 'eventTarget': record['taskName']},
        )
        result = payload.get('result') if isinstance(payload, dict) else None
        if not isinstance(result, dict) or type(result.get('code')) is not int or result['code'] != 0:
            raise ApiError(f"日志接口失败：{result}")
        return result

    def archive(self, task_id, job_id):
        service = TrainService(self.client)
        task = service.find_task(task_id)
        # 查询全部实例，避免第一个页面之外的实例无法下载。
        instance = next((item for item in service.all_instances(task)
                         if item['jobId'] == job_id), None)
        if instance is None:
            raise BusinessError(f"当前任务下未找到执行实例 {job_id}")
        self._fields(instance, ('businessId', 'taskId', 'jobId', 'taskName'))
        if instance['taskId'] != task_id:
            raise ApiError('执行实例的 taskId 与请求任务不一致')
        result = self._request('getRunJobLogArchiveList', instance,
                               ('businessId', 'jobId', 'taskId'))
        count, items = result.get('count'), result.get('logInfoList')
        if (type(count) is not int or count < 0 or not isinstance(items, list)
                or not all(isinstance(item, dict) for item in items) or count != len(items)):
            raise ApiError('归档日志列表或数量异常，无法确认完整列表')
        for item in items:
            self._fields(item, ('businessId', 'taskId', 'jobId', 'taskName'))
            if item['taskId'] != task_id or item['jobId'] != job_id:
                raise ApiError('归档日志记录与执行实例不一致')
        return result

    def download_url(self, record):
        if type(record.get('status')) is not int or record['status'] != 1:
            raise BusinessError('日志尚未归档成功，不能下载')
        result = self._request('getRunningJobLogUrl', record,
                               ('businessId', 'taskId', 'jobId', 'roleJobId', 'archiveId', 'createUser'),
                               {'isApplicantPromise': True, 'isUpload': False})
        https_url(result.get('downloadUrl'))
        return result['downloadUrl']
