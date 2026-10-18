"""State changes share the same SQLite transaction as request dispatch."""
from uuid import uuid4
import time
from .storage import Store


def write(db, scope, path, data):
    if path.endswith('/startScheduleTask'):
        task = Store.get(db, scope, 'train', data['taskId'])
        identifier = str(uuid4())
        clock = int(db.execute("SELECT value FROM meta WHERE key='clock'").fetchone()[0])
        Store.put(db, scope, 'job', identifier, dict(jobId=identifier, taskId=data['taskId'],
            taskName=task['taskName'], jobStatus='running', status='running', startedClock=clock,
            createTime=time.time_ns() // 1000000))
        task.update(jobStatus='running', latestRunTime=time.time_ns() // 1000000)
        Store.put(db, scope, 'train', data['taskId'], task)
        return {'data': {'jobId': identifier}}
    if path.endswith('/cancelMultiInstanceTask'):
        job = Store.get(db, scope, 'job', data['jobId'])
        if job['taskId'] != data['taskId']:
            raise ValueError('实例与任务不匹配')
        job.update(jobStatus='cancelled', status='cancelled')
        Store.put(db, scope, 'job', data['jobId'], job)
        task = Store.get(db, scope, 'train', data['taskId'])
        running = any(j['taskId'] == data['taskId'] and j['status'] == 'running'
                      for j in Store.items(db, scope, 'job'))
        task['jobStatus'] = 'running' if running else 'cancelled'
        Store.put(db, scope, 'train', data['taskId'], task)
        return {}
    if path.endswith('/modelTrain/v2/delete'):
        Store.get(db, scope, 'train', data['taskId'])
        for kind in ('train', 'train_detail'):
            value = Store.get(db, scope, kind, data['taskId'])
            value['_deleted'] = True
            Store.put(db, scope, kind, data['taskId'], value)
        return {}
    if path.endswith('/modelTrain/updateNew'):
        detail = Store.get(db, scope, 'train_detail', data['id'])
        detail.update(name=data['name'], taskInfo=data['taskInfo'])
        Store.put(db, scope, 'train_detail', data['id'], detail)
        return {}
    if path.endswith('/modelTrain/createNew'):
        identifier = str(uuid4())
        Store.put(db, scope, 'train_detail', identifier, data)
        Store.put(db, scope, 'train', identifier, dict(taskId=identifier, taskName=data['name'],
                  businessId=scope, teamId='', taskType='mtp', jobStatus='pending'))
        return {'data': {'id': identifier}}
    if path.endswith('/algorithmWarehouse/copy'):
        value = Store.get(db, scope, 'algorithm', data['srcId'])
        identifier = str(uuid4())
        value.update(id=identifier, algorithmId=identifier, algorithmName=data['tarName'], algorithmVersion=data['tarVersion'])
        Store.put(db, scope, 'algorithm', identifier, value)
        return {'data': {'id': identifier}}
    if path == '/ai/backend/experiment/project':
        identifier = str(uuid4())
        Store.put(db, scope, 'project', identifier, {**data, 'projectId': identifier})
        return {'data': {'projectId': identifier}}
    if path.endswith('/rtcContainer/publish'):
        model = data['modelInfo']
        Store.get(db, scope, 'model', model['modelId'])
        identifier = str(uuid4())
        value = {**data['serviceInfo'], 'serviceId': identifier, 'businessId': scope,
                 'modelId': model['modelId'], 'modelName': model['modelName'],
                 'modelVersion': model['modelVersion'], 'infraType': 'rtc', 'status': 'running'}
        Store.put(db, scope, 'service', identifier, value)
        return {'data': {'serviceId': identifier}}
    if path.endswith(('/dataExplorer/start', '/dataExplorer/stop')):
        value = Store.get(db, scope, 'studio', data['envId'])
        value['status'] = 'online' if path.endswith('/start') else 'stopped'
        Store.put(db, scope, 'studio', data['envId'], value)
        return {}
    return None
