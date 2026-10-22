import io
import runpy
from pathlib import Path
from zipfile import ZipFile
import pytest


@pytest.mark.parametrize('path', ['wiserec_cli/notification_api.py', 'permission_notifier/worker.py',
                                'assistant.json', 'docs/权限申请通知与独立本地助手设计.md'])
def test_notification_artifact_is_rejected_even_inside_windows_zip(tmp_path, path):
    check=runpy.run_path(str(Path(__file__).parents[1]/'scripts/releasing/check-cli-package.py'))['check']
    wheel=io.BytesIO()
    with ZipFile(wheel,'w') as archive: archive.writestr(path,'not distributable')
    bundle=tmp_path/'windows.zip'
    with ZipFile(bundle,'w') as archive: archive.writestr('package/wiserec_cli-test.whl',wheel.getvalue())
    with pytest.raises(ValueError): check(bundle)
