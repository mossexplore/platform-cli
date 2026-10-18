import os
import pytest
from permission_server import PermissionServer


@pytest.fixture(scope='session', autouse=True)
def permission_service(tmp_path_factory):
    service = PermissionServer(tmp_path_factory.mktemp('permission-service'))
    os.environ['TEST_DEMO_PERMISSION_URL'] = service.url
    yield service
    os.environ.pop('TEST_DEMO_PERMISSION_URL', None)
    service.close()
