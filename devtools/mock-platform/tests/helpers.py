import os
from wiserec_cli_mock.workspace import initialize as create_workspace


def initialize(root, scenario='standard', *, permission_url=None, username='demo'):
    return create_workspace(root, scenario, permission_url=permission_url or os.environ['TEST_DEMO_PERMISSION_URL'], username=username)
