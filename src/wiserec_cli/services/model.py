"""当前业务的模型列表与详情查询，保留服务端扩展字段。"""
from typing import Optional

from ..errors import ApiError, BusinessError

PREFIX = '/ai/backend/mep/models/'


class ModelService:
    def __init__(self, client):
        self.client = client

    def _call(self, endpoint, body):
        if not self.client.business_id:
            raise BusinessError('尚未选择业务，请运行 ml business use')
        payload = self.client.request('POST', PREFIX + endpoint, json_body=body,
                                      headers={'businessid': self.client.business_id})
        result = payload.get('result') if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError('模型查询响应缺少有效的 result')
        # 详情示例未包含 code；只在服务端实际返回该字段时校验。
        if 'code' in result and (type(result['code']) is not int or result['code'] != 0):
            raise ApiError(f"模型查询失败：code={result['code']}，des={result.get('des', '')}")
        return payload

    def list_models(self, page: int = 1, page_size: int = 10, name: str = '',
                    model_type: Optional[str] = None, owner: Optional[str] = None,
                    team_id: str = ''):
        if page < 1 or page_size < 1:
            raise ValueError('page 和 page-size 必须为正整数')
        body = {
            'pageIndex': page, 'pageSize': page_size, 'sfsId': '',
            'modelStatus': None, 'sourceEnv': None, 'tags': [],
            'modelUsage': 'cloud', 'modelName': name, 'selectModel': '',
            'businessId': self.client.business_id, 'scene': '', 'subScene': '',
            'source': None, 'modelType': model_type, 'teamId': team_id,
            'owner': owner, 'noticeTime': [], 'approvalStrategy': None,
        }
        payload = self._call('queryList', body)
        result = payload['result']
        if type(result.get('count')) is not int or result['count'] < 0:
            raise ApiError('模型列表缺少有效的 result.count')
        if not isinstance(result.get('models'), list) or not all(
                isinstance(item, dict) for item in result['models']):
            raise ApiError('模型列表缺少有效的 result.models')
        return payload

    def detail(self, model_id: str):
        model_id = model_id.strip()
        if not model_id:
            raise ValueError('模型 ID 不能为空')
        return self._call('queryDetail', {'modelId': model_id})
