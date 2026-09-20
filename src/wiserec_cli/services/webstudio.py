"""Web Studio 管理台接口；不重放登录请求，不输出访问凭据。"""
import re

from ..errors import ApiError

PREFIX = '/ai/backend/webstudio/dataExplorer/'


class WebStudioService:
    def __init__(self, client):
        self.client = client

    def _call(self, endpoint, body):
        try:
            payload = self.client.request('POST', PREFIX + endpoint, json_body=body)
        except Exception as exc:
            # 通用客户端的异常可能包含响应正文，accessUrl 正文可能含 Token。
            status = re.search(r'HTTP[ :]*(\d{3})', str(exc))
            detail = f'（HTTP {status[1]}）' if status else ''
            raise ApiError(f'Web Studio {endpoint} 请求失败{detail}；请检查管理台登录和接口权限（未自动重试）') from None
        result = payload.get('result') if isinstance(payload, dict) else None
        if not isinstance(result, dict) or type(result.get('code')) is not int or result['code'] != 0:
            raise ApiError(f'Web Studio {endpoint} 业务响应失败；请检查实例和业务权限')
        return payload

    def list(self, page=1, page_size=10, name='', status='', relator='', env_id='', business_id=None):
        if page < 1 or page_size < 1:
            raise ValueError('page 和 page-size 必须为正整数')
        if business_id is not None and business_id != self.client.business_id:
            raise ValueError('business-id 必须与当前选择一致，请先运行 ml business use')
        body = dict.fromkeys(('beginTime', 'endTime', 'labelName', 'region', 'scene', 'subScene',
                              'teamId', 'status', 'clusterType', 'relator', 'clusterName', 'envId'), '')
        body.update(pageIndex=page, pageSize=page_size, businessId=self.client.business_id,
                    labelName=name, status=status, relator=relator, envId=env_id)
        payload = self._call('queryEnvList', body)
        result = payload['result']
        if (not isinstance(result.get('envs'), list) or
                not all(isinstance(item, dict) for item in result['envs']) or
                type(result.get('count')) is not int or result['count'] < 0):
            raise ApiError('Web Studio 列表响应结构无效')
        return payload

    def get(self, env_id):
        result = self.list(env_id=env_id)['result']
        matches = [item for item in result['envs'] if item.get('envId') == env_id]
        if len(matches) != 1:
            raise ApiError('当前业务下未找到唯一匹配的 Web Studio，请检查实例 ID 和权限')
        item = matches[0]
        if 'businessId' in item and item['businessId'] != self.client.business_id:
            raise ApiError('Web Studio 不属于当前业务')
        return item

    def access(self, env_id):
        if not self.client.username:
            raise ApiError('当前登录账号为空，请重新登录管理台')
        result = self._call('accessUrl', {'businessId': self.client.business_id,
                           'envId': env_id, 'operator': self.client.username})['result']
        if not isinstance(result.get('accessUrl'), str) or not result['accessUrl']:
            raise ApiError('Web Studio 响应缺少 accessUrl')
        return result['accessUrl']
