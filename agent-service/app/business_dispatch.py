"""CLI orchestration shared with the agent, with identities supplied by the server."""
import json
import tempfile
from pathlib import Path
from uuid import uuid4
import httpx
from wiserec_cli.services.train import TrainService
from wiserec_cli.services.experiment import ExperimentService
from wiserec_cli.services.model_deploy import ModelDeployService
from wiserec_cli.services.algorithm import AlgorithmService
from wiserec_cli.services.dataset_files import DatasetFilesService
from wiserec_cli.services.train_export import export_config
from wiserec_cli.featureset_export import export_features
from wiserec_cli.downloads import https_url
from wiserec_cli.access_transport import tls_verify
from .business_tools import OPERATIONS
from .artifacts import MAX_BYTES
from .errors import AppError
from .quality_tools import null_rates_page


def dispatch(owner, client, name, args):
    spec = OPERATIONS[name]
    a = spec.schema.model_validate(args).model_dump()
    if a.get('page_size', 1) > owner.config.runtime.max_page_size:
        raise ValueError('分页超出服务端限制')
    if name == 'run_service_mock' and a.get('pod_ip') is not None:
        raise ValueError('指定主机请使用 run_service_host_mock')
    if name == 'run_service_host_mock' and not a.get('pod_ip'):
        raise ValueError('主机测试必须提供 pod_ip')
    if name in ('list_featuresets', 'list_model_featuresets'):
        a['set_type'] = 'model' if name == 'list_model_featuresets' else 'wide'
    if spec.service:
        result = getattr(spec.service(client), spec.method)(**a)
        return null_rates_page(result) if name == 'list_feature_null_rates' else result
    if name == 'export_model_featureset': name = 'export_featureset'
    store = client.agent_artifacts
    if name.startswith('jupyter_') or name == 'login_webstudio':
        from .jupyter_tools import dispatch as jupyter
        return jupyter(client, name, a)
    if name == 'upload_dataset_file':
        path = store.path(a.pop('artifact_id'))
        return DatasetFilesService(client).upload(file_path=path, timeout=60, **a)
    if name in ('clone_offline_project', 'preview_offline_clone'):
        svc = ExperimentService(client)
        detail = svc.get_project(a['project_id'])
        body = svc.build_clone_request(detail, a['name'], str(uuid4()))
        return body if name == 'preview_offline_clone' else svc.create_project(body)
    if name == 'preview_model_deployment':
        a['request_content'] = a.pop('request_sample') or ''
        a['response_content'] = a.pop('response_sample') or ''
        payload, template, frameworks = ModelDeployService(client).prepare(
            tenant_id=client.agent_business['tenant_id'], **a)
        artifact = store.put('deployment-plan.json', json.dumps(payload, ensure_ascii=False).encode(), 'deployment_plan')
        return {'plan': artifact, 'service': payload.get('data', {}).get('serviceInfo', {}),
                'frameworks': frameworks, 'message': '完整发布内容见计划附件及网页确认卡片'}
    if name == 'publish_model_deployment':
        payload = json.loads(store.path(a['artifact_id'], 'deployment_plan').read_text())
        return ModelDeployService(client).publish(payload)
    train = TrainService(client)
    if name == 'preview_train_cancellation':
        task = owner.find_task(train, a['task_id'])
        items, seen = [], set()
        for page in range(1, owner.config.runtime.max_auto_pages + 1):
            result = train.list_instances(task, page, owner.config.runtime.max_page_size)
            for item in result['items']:
                if not item.get('jobId') or not item.get('taskName') or item['jobId'] in seen:
                    raise ValueError('实例缺失标识或分页重复')
                seen.add(item['jobId'])
                items.append({'job_id': item['jobId'], 'task_name': item['taskName']})
            if len(items) >= result['count']: break
            if not result['items']: raise ValueError('实例分页提前结束')
        else:
            raise AppError('PAGE_LIMIT', '实例超出分页限制，未生成取消计划')
        plan = {'task_id': a['task_id'], 'instances': items}
        return {'plan': store.put('cancel-plan.json', json.dumps(plan).encode(), 'cancellation_plan'),
                'task_id': a['task_id'], 'instance_count': len(items), 'message': '完整实例列表见计划附件和确认卡片'}
    if name == 'cancel_train_task':
        plan = json.loads(store.path(a['artifact_id'], 'cancellation_plan').read_text())
        task = owner.find_task(train, plan['task_id'])
        completed = []
        for item in plan['instances']:
            job = find_instance(owner, train, task, item['job_id'])
            try:
                train.cancel_instance(plan['task_id'], item['job_id'], job['taskName'])
            except AppError:
                raise
            except Exception:
                return {'completed': completed, 'uncertain_job_id': item['job_id'],
                        'status': 'partial_or_unknown', 'message': '已停止，未自动重试，请查询实例状态'}
            completed.append(item['job_id'])
        return {'completed': completed, 'status': 'completed'}
    if name in ('start_train_task', 'cancel_train_instance', 'delete_train_task',
                'clone_train_task', 'update_train_config', 'export_train_config', 'download_train_logs'):
        task = owner.find_task(train, a['task_id'])
        if name == 'start_train_task': return {'job_id': train.start(a['task_id'])}
        if name == 'delete_train_task':
            train.delete_task(task)
            return {'deleted': True}
        if name == 'clone_train_task':
            return {'task_id': train.clone_task(train.clone_detail(task), a['name'], a['customize_config'], client.username)}
        if name == 'update_train_config':
            train.update_config(a['task_id'], a['customize_config'], client.username)
            return {'updated': True}
        if name in ('cancel_train_instance', 'download_train_logs'):
            job = find_instance(owner, train, task, a['job_id'])
            if name == 'cancel_train_instance':
                return {'result': train.cancel_instance(a['task_id'], a['job_id'], job['taskName'])}
    if name in ('export_train_config', 'export_featureset'):
        with tempfile.TemporaryDirectory() as temp:
            if name == 'export_train_config':
                path, _ = export_config(client, a['task_id'], Path(temp) / 'train.yaml')
            else:
                result = export_features(client, a['set_id'], a.get('lang', 'zh_cn'), Path(temp) / 'features.csv')
                path = Path(result['file'])
            return store.put(path.name, path.read_bytes())
    if name in ('download_algorithm', 'download_train_logs'):
        url = (AlgorithmService(client).download_url(a['algorithm_id']) if name == 'download_algorithm'
               else train.get_log_url(a['task_id'], a['job_id']))
        return external_download(client, url)
    raise ValueError('未实现的业务操作')


def find_instance(owner, train, task, job_id):
    for page in range(1, owner.config.runtime.max_auto_pages + 1):
        result = train.list_instances(task, page, owner.config.runtime.max_page_size)
        for item in result['items']:
            if item.get('jobId') == job_id: return item
        if not result['items'] or page * result['pageSize'] >= result['count']: break
    raise AppError('INSTANCE_NOT_FOUND', '未在当前任务分页范围内找到实例', 404)


def external_download(client, url):
    url = https_url(url)
    # Explicit administrator allowlist, no redirects, no platform cookies on file hosts.
    if url.host not in client.agent_environment.download_hosts:
        raise AppError('DOWNLOAD_HOST_DENIED', '管理员须在当前环境 download_hosts 配置文件下载主机', 403)
    client.agent_guard()
    with httpx.Client(verify=tls_verify(), transport=client.agent_transport,
                      trust_env=False, follow_redirects=False, timeout=30) as http:
        with http.stream('GET', url) as response:
            if response.status_code != 200:
                raise AppError('DOWNLOAD_FAILED', '文件服务器未返回成功响应')
            data = bytearray()
            for chunk in response.iter_bytes():
                client.agent_check()
                if len(data) + len(chunk) > MAX_BYTES:
                    raise AppError('FILE_TOO_LARGE', '下载超过 20 MiB 限制', 413)
                data.extend(chunk)
    return client.agent_artifacts.put('download.zip', bytes(data))
