"""All affected table renderers omit the redundant timezone footer."""

from io import StringIO
from unittest.mock import patch

import pytest
from rich.console import Console

from wiserec_cli.commands import algorithm, dataset, dataset_files, featureset, model, service, train

PAGE = {'items': [], 'pageIndex': 1, 'pageSize': 10, 'total': 0, 'count': 0}


@pytest.mark.parametrize('module,renderer,args', [
    (algorithm, algorithm._render_list, (PAGE, 'table')),
    (dataset, dataset.render_list, (PAGE, 'table')),
    (dataset, dataset.render_detail, ({}, 'table')),
    (dataset_files, dataset_files.render_files,
     ({'result': {'fileInfos': {'files': [], 'hasMore': False}}}, '/', 'table')),
    (featureset, featureset.render_page, (PAGE, 'table')),
    (model, model.render_list, ({'result': {'models': [], 'count': 0}}, 1, 10, 'table')),
    (service, service.render_page, ('list', PAGE, 'table')),
    (service, service.render_page, ('host', PAGE, 'table')),
    (service, service.render_page, ('deployment', PAGE, 'table')),
    (train, train.render_page, (PAGE, 'table')),
])
def test_tables_omit_timezone_footer(module, renderer, args):
    output = StringIO()
    with patch.object(module, 'console', Console(file=output, width=240)):
        renderer(*args)
    text = output.getvalue()
    assert text.strip()
    assert 'Asia/Shanghai' not in text
    assert 'UTC+08:00' not in text
