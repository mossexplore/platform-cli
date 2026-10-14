"""模型部署查询编排与单次发布，不自动重放发布请求。"""
from ..errors import ApiError, AuthenticationError
from .deployment import DeploymentTemplateService
from .resource import ResourceTemplateService
from .model import ModelService
from .deploy_payload import build_payload, required, resource_block, resolve_service_fields

PUBLISH_PATH = '/ai/backend/mep/services/rtcContainer/publish'


class ModelDeployService:
    def __init__(self, client):
        self.client = client

    def prepare(self, model_id, template_id, tenant_id, **options):
        model = ModelService(self.client).detail(model_id)['result']
        if model.get('modelId') != model_id:
            raise ApiError('模型详情 ID 与请求不一致')
        resolved = DeploymentTemplateService(self.client).detail(template_id)
        template = resolved['deploymentTemplate']['result']['template']
        if template.get('deployTemplateId') != template_id:
            raise ApiError('部署模板详情 ID 与请求不一致')
        resolve_service_fields(model, template, options.get('service_timeout'), options.get('execute_limit'))
        resources = resolved['resourceTemplates']
        if not resources or any(item['error'] or len(item['exactMatches']) != 1 for item in resources):
            raise ApiError('部署模板关联资源缺失、查询失败或名称不唯一，无法部署')
        blocks, frameworks = [], {}
        service = ResourceTemplateService(self.client)
        for entry in resources:
            resource_id = required(entry['exactMatches'][0], 'dockerId')
            resource = service.detail(resource_id)['result']
            if resource.get('dockerResourceTemplateName') != entry['requestedName']:
                raise ApiError('资源模板详情名称与部署模板关联名称不一致')
            package_id = required(resource, 'frameworkPkgId')
            if package_id not in frameworks:
                frameworks[package_id] = service.framework(package_id)['result']['data']
            blocks.append(resource_block(resource_id, resource, frameworks[package_id]))
        tenant = self.client.request('GET', '/ai/user/queryTenantDetail', params={'businessId': tenant_id},
                                     headers={'businessid': self.client.business_id})
        result = tenant.get('result') if isinstance(tenant, dict) else None
        if not isinstance(result, dict) or type(result.get('code')) is not int or result['code'] != 0:
            raise ApiError('租户详情查询失败或响应缺少有效的 code')
        data = result.get('data')
        entries = data.get('tenantServiceEntityList') if isinstance(data, dict) else None
        if not isinstance(entries, list) or not entries or not isinstance(entries[0], dict):
            raise ApiError('真实租户没有可用的 tenantServiceEntityList')
        scope = required(entries[0], 'serviceGroup')
        if not isinstance(scope, str) or not scope.strip():
            raise ApiError('真实租户首个 serviceGroup 无效')
        return (build_payload(model, template, blocks, scope, **options), template,
                {key: f"{item['name']}@{item['version']}" for key, item in frameworks.items()})

    def publish(self, payload):
        try:
            response = self.client.request('POST', PUBLISH_PATH, json_body=payload,
                                            headers={'businessid': self.client.business_id})
        except (ApiError, AuthenticationError) as exc:
            raise ApiError(f'部署提交结果未确认，请先查询服务状态再决定是否重试；{exc}') from exc
        result = response.get('result') if isinstance(response, dict) else None
        if not isinstance(result, dict) or type(result.get('code')) is not int:
            raise ApiError('部署响应缺少有效的 result.code，提交结果未确认，请先查询服务状态')
        return response
