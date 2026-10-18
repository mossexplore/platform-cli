"""Synthetic deterministic entities, without copied platform data."""
import json
from uuid import uuid5, NAMESPACE_URL
from .storage import Store

PROFILES = ('demo-dev', 'demo-test')
SCENARIOS = ('standard', 'empty', 'large', 'expired-session',
             'partial-failure', 'malformed-response')


def uid(kind, n=1):
    return str(uuid5(NAMESPACE_URL, f'wiserec-demo/{kind}/{n}'))


def business_ids(profile):
    return [uid(profile + '/tenant'), uid(profile + '/team', 1), uid(profile + '/team', 2),
            uid(profile + '/tenant', 2), uid(profile + '/team', 3), uid(profile + '/team', 4)]


def populate(root, scenario):
    store = Store(root)
    with store.transaction() as db:
        for profile in PROFILES:
            for scope in business_ids(profile):
                count = 0 if scenario == 'empty' else 105 if scenario == 'large' else 25
                for n in range(1, count + 1):
                    base = dict(businessId=scope, teamId='', createUser='demo' if n % 2 else 'analyst', updateUser='demo',
                                createTime=1790820000000, updateTime=1790820000000)
                    name = f'recommendation-{n:03d}'
                    values = {
                        'train': dict(taskId=uid('train', n), taskName=name, taskType='mtp',
                                      jobStatus='success', teamId='', algorithmId=uid('algorithm', n),
                                      dataSetId=uid('dataset', n)),
                        'dataset': dict(dataSetId=uid('dataset', n), dataSetName=f'clicks-{n:03d}',
                                        bucketName='demo-data', dataSetType='csv'),
                        'algorithm': dict(id=uid('algorithm', n), algorithmId=uid('algorithm', n),
                                          algorithmName=f'ranker-{n:03d}', algorithmVersion='1.0', bucketName='demo-code'),
                        'model': dict(modelId=uid('model', n), name=name, version='1.0', modelName=name,
                                      modelVersion='1.0', source='mtp', sourceId=uid('source', n),
                                      sourceEnv=profile, modelTag='', pkgId=uid('pkg', n), pkgSize=1024,
                                      pkgLocation='demo/models', storeType='obs', modelType='tensorflow',
                                      tags=[], modelHistoryList=[]),
                        'source': dict(versionId=uid('source', n), jobId=uid('job', n)),
                        'job': dict(jobId=uid('job', n), taskId=uid('train', n), taskName=name,
                                    jobStatus='success', status='success', duration=120),
                        'service': dict(serviceId=uid('service', n), serviceName=name, serviceVersion='1.0',
                                        modelName=name, modelVersion='1.0', infraType='rtc', status='running'),
                        'project': dict(projectId=uid('project', n), projectName=f'offline-{n:03d}',
                                        description='Synthetic ranking evaluation', configName='ranking'),
                        'trial': dict(experimentId=uid('trial', n), projectId=uid('project', n),
                                      experimentName='baseline', experimentType='train', creator='demo', updater='demo'),
                        'swanproject': dict(projectId=uid('swanproject', n), projectName=name, creator='demo'),
                        'namespace': dict(namespaceId=uid('namespace', n), projectId=uid('swanproject', n), namespaceName='default'),
                        'experiment': dict(experimentId=uid('experiment', n), namespaceId=uid('namespace', n),
                                           projectId=uid('swanproject', n), experimentName=name, status='finished'),
                        'studio': dict(envId=uid('studio', n), labelName=f'notebook-{n:03d}', status='stopped',
                                       region='local', operator='demo'),
                    }
                    for kind, value in values.items():
                        Store.put(db, scope, kind, uid(kind, n), {**base, **value})
                    import base64
                    Store.put(db, scope, 'file', uid('dataset', n)+'/clicks.csv', dict(
                        name='clicks.csv', path='/clicks.csv', dir=False, parent='/',
                        dataSetId=uid('dataset', n), content=base64.b64encode(b'user_id,clicks\nu001,12\nu002,7\n').decode()))
                    Store.put(db, scope, 'train_detail', uid('train', n), dict(
                        name=name, taskInfo={'baseInfo': {'taskName': name}, 'parameter': {
                        'customizeConfig': json.dumps({'epochs': 10, 'learning_rate': 0.01})},
                        'createUser': 'demo', 'algorithmId': uid('algorithm', n), 'dataSetId': uid('dataset', n)}))
                if count:
                    for n, kind in enumerate(('wide', 'model'), 1):
                        Store.put(db, scope, 'feature', uid('feature', n), dict(
                            setId=uid('feature', n), setName=f'{kind}-features', setType=kind,
                            createTime='2026-10-01T02:00:00Z', businessId=scope))
                    resource = dict(dockerId=uid('resource'), dockerResourceTemplateName='cpu-inference',
                        frameworkPkgId=uid('framework'), frameworkConfiguration='{"workers": 1}',
                        memory='2G', cpu='1', gpu='0', npu='0', quotaType='shared', containerSpec='cpu-small',
                        clusterName='demo-cluster', appImageName='demo-inference', imageTag='stable', businessId=scope)
                    Store.put(db, scope, 'resource', uid('resource'), resource)
                    Store.put(db, scope, 'framework', uid('framework'), dict(name='Python', version='3.12',
                              pkgStorageId=uid('framework'), pkgStorageLocation='demo/framework', storageType='obs'))
                    Store.put(db, scope, 'deployment', uid('deployment'), dict(deployTemplateId=uid('deployment'),
                        deployTemplateName='cpu-serving', dockerResourceTemplate=['cpu-inference'],
                        deployTemplateType='docker', businessId=scope, inferenceType='online', env='dev',
                        serviceTimeout=30000, executeLimit=10))
