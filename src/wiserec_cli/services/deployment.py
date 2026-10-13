"""部署模板及其关联资源模板的只读查询。"""
from ..errors import ApiError, AuthenticationError, BusinessError

PREFIX = '/ai/backend/mep/scm/deploytemplate/'


class DeploymentTemplateService:
    def __init__(self, client):
        self.client = client

    def _call(self, endpoint, body):
        if not self.client.business_id:
            raise BusinessError('尚未选择业务，请运行 ml business use')
        payload = self.client.request('POST', endpoint, json_body=body,
                                      headers={'businessid': self.client.business_id})
        result = payload.get('result') if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            raise ApiError('部署模板查询响应缺少有效的 result')
        if type(result.get('code')) is not int or result['code'] != 0:
            raise ApiError(f"部署模板查询失败：code={result.get('code')}，des={result.get('des', '')}")
        return payload

    def list_templates(self, page=1, page_size=10, framework_name='', env=None, framework_type=None):
        if page < 1 or page_size < 1:
            raise ValueError('page 和 page-size 必须为正整数')
        payload = self._call(PREFIX + 'queryList', {
            'pageIndex': page, 'pageSize': page_size, 'inferenceType': None,
            'env': env, 'frameworkType': framework_type, 'gatewayName': None,
            'isSystem': None, 'frameworkPkgId': '', 'frameworkPkgName': framework_name,
            'deployTemplateType': None, 'deployTemplateName': None,
            'businessId': self.client.business_id, 'componentName': None, 'componentVersion': None,
        })
        result = payload['result']
        if type(result.get('count')) is not int or result['count'] < 0:
            raise ApiError('部署模板列表缺少有效的 result.count')
        items = result.get('deployTemplates')
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ApiError('部署模板列表缺少有效的 result.deployTemplates')
        return payload

    def detail(self, template_id):
        if not template_id.strip():
            raise ValueError('部署模板 ID 不能为空')
        payload = self._call(PREFIX + 'queryDetail', {'deployTemplateId': template_id.strip()})
        template = payload['result'].get('template')
        if not isinstance(template, dict):
            raise ApiError('部署模板详情缺少有效的 result.template')
        names = template.get('dockerResourceTemplate', [])
        if not isinstance(names, list) or not all(isinstance(name, str) and name.strip() for name in names):
            raise ApiError('dockerResourceTemplate 应为有效名称列表')
        if names and not all(isinstance(template.get(key), str) and template[key].strip()
                             for key in ('deployTemplateType', 'businessId')):
            raise ApiError('关联资源查询缺少有效的 deployTemplateType 或 businessId')
        resources = []
        for name in names:
            entry = {'requestedName': name, 'response': None, 'exactMatches': [], 'error': None}
            try:
                response = self._call('/ai/backend/mep/resourcetemp/queryList', {
                    'templateType': template['deployTemplateType'],
                    'businessId': template['businessId'], 'dockerResourceTemplateName': name,
                })
                entry['response'] = response
                items = response['result'].get('resourceTemplateInfoList')
                if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
                    raise ApiError('关联资源查询缺少有效的 resourceTemplateInfoList')
                entry['exactMatches'] = [item for item in items if item.get('dockerResourceTemplateName') == name]
                if not entry['exactMatches']:
                    entry['error'] = '未找到名称完全相同的资源模板'
                elif len(entry['exactMatches']) > 1:
                    entry['error'] = '名称不唯一，找到多个同名资源模板'
            except (AuthenticationError, BusinessError):
                raise
            except Exception as exc:
                entry['error'] = str(exc)
            resources.append(entry)
        return {'deploymentTemplate': payload, 'resourceTemplates': resources}
