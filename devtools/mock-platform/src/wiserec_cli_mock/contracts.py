"""Method/path allowlist; suffix similarities never enable an unknown API."""
import re
from .routes import LISTS, DETAILS

POST = set(LISTS) | set(DETAILS) | {
    '/ai/backend/mtp/traintask/queryJobInstanceByTaskId',
    '/ai/backend/mtp/traintask/queryScheduleTaskList',
    '/ai/backend/mtp/traintask/queryModelTaskDetail',
    '/ai/backend/dpp/proxy/featureStore/featureset/config',
    '/ai/backend/modelDev/modelTrain/startScheduleTask',
    '/ai/backend/modelDev/modelTrain/v2/delete',
    '/ai/backend/modelDev/modelTrain/updateNew',
    '/ai/backend/modelDev/modelTrain/createNew',
    '/ai/backend/mtp/train/cancelMultiInstanceTask',
    '/ai/backend/modelDev/algorithmWarehouse/copy',
    '/ai/backend/experiment/project',
    '/ai/backend/mep/services/rtcContainer/publish',
    '/ai/backend/mep/services/rtcContainer/queryServiceHostList',
    '/ai/backend/mep/services/rtcContainer/queryDetail',
    '/ai/backend/mep/services/rtcContainer/queryPodAdvanceLogFileList',
    '/ai/backend/mep/services/rtcContainer/queryPodAdvanceLog',
    '/ai/backend/mep/tenant/queryTeamList',
    '/ai/backend/mep/config/queryConfig',
    '/ai/backend/mtp/dataSet/file/queryList',
    '/ai/backend/mtp/dataSet/file/upload',
    '/ai/backend/webstudio/dataExplorer/start',
    '/ai/backend/webstudio/dataExplorer/stop',
    '/ai/backend/webstudio/dataExplorer/accessUrl',
    '/ai/backend/mtp/swanboard/experiment/page',
}
POST.discard('/ai/backend/experiment/project/list')
GET = {'/ai/user/info', '/ai/user/queryTenantDetail', '/ai/backend/experiment/project/list',
       '/ai/backend/experiment', '/ai/backend/mtp/algorithm/downloadurl',
       '/ai/backend/mtp/traintask/downloadLogUrl', '/ai/backend/mtp/traintask/export',
       '/ai/backend/dpp/proxy/featureStore/featureset/exportFeatures'}
PATTERNS = [r'/ai/backend/experiment/project/[^/]+',
            r'/ai/backend/mtp/swanboard/namespace/query/[^/]+',
            r'/ai/backend/mtp/swanboard/experiment/[^/]+/(feature|config)',
            r'/ai/backend/mtp/swanboard/label/experiment/[^/]+',
            r'/ai/backend/mtp/swanboard/tag/experiment/[^/]+/[^/]+/stats']


def supported(method, path):
    if method == 'POST':
        return path in POST
    if method == 'GET':
        return path in GET or any(re.fullmatch(pattern, path) for pattern in PATTERNS)
    return False
