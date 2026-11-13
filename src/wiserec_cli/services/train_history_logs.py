"""执行记录查找及普通、分布式训练日志协议。"""
from uuid import uuid4

from ..downloads import https_url
from ..errors import ApiError, BusinessError


class LogNotReady(ApiError):
    """接口明确返回日志尚不存在。"""


def role_records(record):
    roles = record.get('roleJobInfo')
    if not isinstance(roles, list) or not all(isinstance(role, dict) for role in roles):
        raise ApiError('分布式执行记录缺少有效的 roleJobInfo 数组')
    return roles


def require_ids(record, distributed=False):
    fields = ('taskId', 'jobId', 'roleJobId') if distributed else ('taskId', 'jobId')
    for field in fields:
        if not isinstance(record.get(field), str) or not record[field].strip():
            raise ApiError(f'执行记录缺少有效的 {field}')


class HistoryLogService:
    def __init__(self, client):
        self.client = client

    def find_record(self, task_id, job_id):
        from .train import TrainService

        if not task_id.strip() or not job_id.strip():
            raise ValueError('taskId 和 jobId 不能为空')
        page = 1
        seen = set()
        while True:
            result = TrainService(self.client).list_history(task_id, page, 200)
            for item in result['items']:
                if item.get('jobId') == job_id:
                    return item
            if not result['items'] or page * 200 >= result['count']:
                break
            # 防止服务端忽略页码而一直返回相同记录。
            ids = tuple(str(item.get('jobId')) for item in result['items'])
            if ids in seen:
                raise ApiError('执行记录分页重复，无法确认目标记录，请稍后重试')
            seen.add(ids)
            page += 1
        raise ApiError(f'训练任务 {task_id} 中未找到执行记录 {job_id}')

    def request(self, method, action, **kwargs):
        business_id = self.client.business_id
        if not business_id:
            raise BusinessError('尚未选择租户或团队，请运行 ml business use')
        payload = self.client.request(
            method, '/ai/backend/mtp/traintask/' + action,
            headers={'businessid': business_id}, **kwargs,
        )
        result = payload.get('result') if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError(f'{action} 响应缺少 result')
        if type(result.get('code')) is not int or result['code'] != 0:
            raise ApiError(f'{action} 失败：code={result.get("code")}，des={result.get("des")}')
        return result

    def exists(self, job_id, role_job_id=None):
        params = {'businessId': self.client.business_id, 'jobId': job_id}
        if role_job_id is not None:
            params['roleJobId'] = role_job_id
        result = self.request('GET', 'queryJobLogIsExist', params=params)
        if result.get('isExistLog') is True:
            return True
        if result.get('isExistLog') is False or result.get('failedUploadSwitch') is False:
            return False
        raise ApiError('日志状态未明确：isExistLog 和 failedUploadSwitch 未返回可识别状态')

    def archive(self, job_id):
        self.request('POST', 'manualArchiveLog', json_body={
            'version': '1.0', 'meta': {'uuid': str(uuid4())},
            'data': {'businessId': self.client.business_id, 'jobId': job_id},
        })

    def download_url(self, task_id, job_id, role_job_id=None, *, on_stage=None):
        report = on_stage or (lambda stage, message: None)
        # 每次获取链接（含认证重试）均重新检查，调用方不能绕过此门禁。
        report('check_log', '开始查询日志是否存在')
        if not self.exists(job_id, role_job_id):
            raise LogNotReady('日志尚未就绪')
        params = {'businessId': self.client.business_id, 'taskId': task_id,
                  'jobId': job_id, 'isApplicantPromise': 'true'}
        if role_job_id is not None:
            params['roleJobId'] = role_job_id
        report('get_download_url', '日志已就绪，开始获取日志下载地址')
        result = self.request('GET', 'downloadLogUrl', params=params)
        report('validate_download_url', '开始校验下载地址')
        https_url(result.get('url'))
        return result['url']
