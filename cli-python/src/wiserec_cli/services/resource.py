"""当前业务的容器资源模板查询。"""
from ..errors import ApiError, BusinessError

PREFIX = '/ai/backend/mep/resourcetemp/'


class ResourceTemplateService:
    def __init__(self, client):
        self.client = client

    def _call(self, endpoint, body):
        if not self.client.business_id:
            raise BusinessError('尚未选择业务，请运行 ml business use')
        payload = self.client.request('POST', endpoint, json_body=body,
                                      headers={'businessid': self.client.business_id})
        result = payload.get('result') if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError('资源模板查询响应缺少有效的 result')
        if type(result.get('code')) is not int or result['code'] != 0:
            raise ApiError(f"资源模板查询失败：code={result.get('code')}，des={result.get('des', '')}")
        return payload

    def list_templates(self, page=1, page_size=10, name='', env=None, framework_name='',
                       framework_type=None, resource_type='docker', template_type='docker'):
        if page < 1 or page_size < 1:
            raise ValueError('page 和 page-size 必须为正整数')
        body = {
            'pageIndex': page, 'pageSize': page_size, 'quotaType': None, 'env': env,
            'frameworkType': framework_type, 'frameworkPkgId': '',
            'frameworkPkgName': framework_name, 'gatewayName': '', 'resourceType': resource_type,
            'dockerResourceTemplateName': name, 'clusterName': None,
            'businessId': self.client.business_id, 'dockerType': None, 'containerSpec': None,
            'appImageName': None, 'imageTag': None, 'domain': None, 'templateType': template_type,
        }
        payload = self._call(PREFIX + 'queryList', body)
        result = payload['result']
        if type(result.get('count')) is not int or result['count'] < 0:
            raise ApiError('资源模板列表缺少有效的 result.count')
        items = result.get('resourceTemplateInfoList')
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiError('资源模板列表缺少有效的 result.resourceTemplateInfoList')
        return payload

    def detail(self, template_id):
        if not template_id.strip():
            raise ValueError('资源模板 ID 不能为空')
        return self._call(PREFIX + 'queryDetail', {'dockerId': template_id.strip()})

    def framework(self, package_id):
        payload = self._call('/ai/backend/mep/scm/frameworkPkg/queryFrameworkPkgDetail',
                             {'frameworkPkgId': package_id})
        data = payload['result'].get('data')
        if not isinstance(data, dict) or not all(
                isinstance(data.get(key), str) and data[key].strip() for key in ('name', 'version')):
            raise ApiError('推理框架详情缺少有效的 result.data.name 或 version')
        return payload
