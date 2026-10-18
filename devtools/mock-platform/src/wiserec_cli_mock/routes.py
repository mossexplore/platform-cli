"""Explicit read contracts for the current platform API."""
import json
from .storage import Store


def page(items, data):
    for key in ('taskName', 'algorithmName', 'bucketName', 'dataSetName', 'createUser', 'updateUser',
                'modelName', 'serviceName', 'modelVersion', 'setName', 'setType', 'projectName',
                'dockerResourceTemplateName', 'deployTemplateName', 'labelName', 'envId'):
        if data.get(key):
            items = [item for item in items if str(data[key]).lower() in str(item.get(key, '')).lower()]
    total = len(items)
    size = int(data.get('pageSize', max(total, 1)))
    index = int(data.get('pageIndex', data.get('pageNum', 1)))
    if size < 1 or index < 1:
        raise ValueError('分页参数必须为正整数')
    return items[(index-1)*size:index*size], total


LISTS = {
    '/ai/backend/modelDev/modelTrain/list': ('train', 'taskInfos', 'count', True),
    '/ai/backend/modelDev/algorithmWarehouse/list': ('algorithm', 'list', 'total', True),
    '/ai/backend/mtp/dataSet/queryList': ('dataset', 'data', 'totalSize', False),
    '/ai/backend/mep/models/queryList': ('model', 'models', 'count', False),
    '/ai/backend/mep/services/queryList': ('service', 'services', 'count', False),
    '/ai/backend/dpp/proxy/featureStore/featureset/names': ('feature', 'featureSetInfoList', 'totalCount', False),
    '/ai/backend/mep/resourcetemp/queryList': ('resource', 'resourceTemplateInfoList', 'count', False),
    '/ai/backend/mep/scm/deploytemplate/queryList': ('deployment', 'deployTemplates', 'count', False),
    '/ai/backend/webstudio/dataExplorer/queryEnvList': ('studio', 'envs', 'count', False),
    '/ai/backend/experiment/project/list': ('project', 'data', 'total', False),
    '/ai/backend/mtp/swanboard/project/list': ('swanproject', 'data', 'total', False),
}
DETAILS = {
    '/ai/backend/mtp/dataSet/queryDetail': ('dataset', 'dataSetId', 'data'),
    '/ai/backend/mep/models/queryDetail': ('model', 'modelId', None),
    '/ai/backend/mtp/offlinemodel/version/queryDetail': ('source', 'versionId', None),
    '/ai/backend/modelDev/modelTrain/detailNew': ('train_detail', 'id', 'data'),
    '/ai/backend/mep/resourcetemp/queryDetail': ('resource', 'dockerId', None),
    '/ai/backend/mep/scm/deploytemplate/queryDetail': ('deployment', 'deployTemplateId', 'template'),
    '/ai/backend/mep/scm/frameworkPkg/queryFrameworkPkgDetail': ('framework', 'frameworkPkgId', 'data'),
}


def read(db, scope, path, data):
    if path in LISTS:
        kind, field, count, nested = LISTS[path]
        items, total = page(Store.items(db, scope, kind), data)
        result = {field: items, count: total}
        return {'data': result} if nested else result
    if path in DETAILS:
        kind, key, field = DETAILS[path]
        value = Store.get(db, scope, kind, data[key])
        return {field: value} if field else value
    if path.endswith(('/queryJobInstanceByTaskId', '/queryScheduleTaskList')):
        Store.get(db, scope, 'train', data['taskId'])
        jobs = [j for j in Store.items(db, scope, 'job') if j['taskId'] == data['taskId']]
        if data.get('sortOrder') == 'descend':
            jobs.reverse()
        items, total = page(jobs, data)
        return {'jobs': items, 'count': total}
    if path == '/ai/backend/mtp/traintask/queryModelTaskDetail':
        job = Store.get(db, scope, 'job', data['jobId'])
        return {'jobHistoryDetail': {**job, **Store.get(db, scope, 'train_detail', job['taskId'])}}
    if path == '/ai/backend/dpp/proxy/featureStore/featureset/config':
        feature = Store.get(db, scope, 'feature', data['setId'])
        return {'featureJson': json.dumps({**feature, 'features': [
            {'name': 'user_id', 'type': 'string'}, {'name': 'clicks', 'type': 'int'}]})}
    if path.startswith('/ai/backend/experiment/project/'):
        return {'data': Store.get(db, scope, 'project', path.rsplit('/', 1)[1])}
    if path == '/ai/backend/experiment':
        Store.get(db, scope, 'project', data['projectId'])
        items = [i for i in Store.items(db, scope, 'trial') if i['projectId'] == data['projectId']]
        items, total = page(items, data)
        return {'data': items, 'count': total, 'total': total}
    if path.startswith('/ai/backend/mtp/swanboard/'):
        return swan(db, scope, path, data)
    if path.endswith('/queryServiceHostList'):
        service = Store.get(db, scope, 'service', data['serviceId'])
        hosts = [{'podName': f"{service['serviceId']}-{i}", 'nodeName': f"{service['serviceId']}-{i}", 'hostIp': f'192.0.2.{i}',
                  'clusterName': 'demo-cluster', 'status': 0, 'infraType': 'rtc'} for i in range(1, 13)]
        items, total = page(hosts, data)
        return {'data': items, 'count': total}
    if path == '/ai/backend/mep/services/rtcContainer/queryDetail':
        value = Store.get(db, scope, 'service', data['serviceId'])
        return {'data': [value], 'count': 1}
    if path.endswith(('/queryPodAdvanceLogFileList', '/queryPodAdvanceLog')):
        service_id, number = data['podName'].rsplit('-', 1)
        Store.get(db, scope, 'service', service_id)
        if data['clusterName'] != 'demo-cluster' or not number.isdigit() or not 1 <= int(number) <= 12:
            raise ValueError('Pod 或集群不存在')
    if path.endswith('/queryPodAdvanceLogFileList'):
        return {'podLogFiles': [{'fileName': 'application.log', 'name': 'application.log', 'size': 128}]}
    if path.endswith('/queryPodAdvanceLog'):
        lines = ['2026-10-01 10:00:00 INFO Service started', '2026-10-01 10:00:01 INFO Request completed']
        search = data.get('serviceLogSearch', {})
        if search.get('logFileName') != 'application.log':
            raise ValueError('日志文件不存在')
        lines = [line for line in lines if all(k in line for k in search.get('keywords', []))]
        return {'data': {'content': '\n'.join(lines[:int(search.get('line', 100))])}}
    if path == '/ai/user/queryTenantDetail':
        return {'data': {'tenantServiceEntityList': [{'serviceGroup': 'demo-recommendation'}]}}
    if path == '/ai/backend/mep/tenant/queryTeamList':
        return {'data': []}
    if path == '/ai/backend/mep/config/queryConfig':
        return {'data': {'key': data.get('key'), 'value': 'demo'}}
    return None


def swan(db, scope, path, data):
    suffix = path.removeprefix('/ai/backend/mtp/swanboard/')
    if suffix.startswith('namespace/query/'):
        identifier = suffix.rsplit('/', 1)[1]
        Store.get(db, scope, 'swanproject', identifier)
        return {'data': [i for i in Store.items(db, scope, 'namespace') if i['projectId'] == identifier]}
    if suffix == 'experiment/page':
        Store.get(db, scope, 'namespace', data['namespaceId'])
        items = [i for i in Store.items(db, scope, 'experiment') if i['namespaceId'] == data['namespaceId']]
        return {'data': {'list': items, 'total': len(items), 'totalPages': 1, 'pageNum': 1, 'pageSize': len(items)}}
    parts = suffix.split('/')
    if parts[0] in {'label', 'tag'}:
        identifier = parts[2]
    elif parts[0] == 'experiment' and len(parts) == 3:
        identifier = parts[1]
    else:
        return None
    Store.get(db, scope, 'experiment', identifier)
    if parts[-1] == 'feature':
        return {'data': [{'name': 'loss', 'type': 'scalar'}, {'name': 'accuracy', 'type': 'scalar'}], 'total': 2}
    if parts[-1] == 'config':
        return {'data': {'epochs': 10, 'learning_rate': 0.01}}
    if parts[-1] == 'stats':
        return {'data': {'tagName': parts[-2], 'min': 0.1, 'max': 0.95, 'avg': 0.65, 'count': 10}}
    if parts[0] == 'label':
        return {'data': {'python': '3.12', 'cpu': {'brand': 'Demo CPU'}, 'memory': '8 GiB', 'requirements': ['torch', 'numpy']}}
    return None
