"""Numeric projection preserves statistical inputs and runs before Agent output limits."""
import json
from decimal import Decimal

import httpx
import pytest
from sqlalchemy import select

from conftest import BUSINESS, ready
from app.models import Session
from app.quality_tools import null_rates_page
from wiserec_cli.errors import ApiError
from wiserec_cli.services.quality import PREFIX


def test_numeric_projection_and_actual_json_serialization():
    items = [{'nullValueRate': value, 'featureId': 'excluded', 'extra': 'excluded'}
             for value in (0, 0.125, 1, 0.125, None, Decimal('0.25'), Decimal('1'))]
    items.append({'featureId': 'missing-rate'})
    page = {'items': items, 'count': 300, 'pageIndex': 2, 'pageSize': 10}
    result = null_rates_page(page)
    assert json.loads(json.dumps(result, allow_nan=False)) == {
        'nullValueRates': [0, 0.125, 1, 0.125, None, 0.25, 1, None],
        'count': 300, 'pageIndex': 2, 'pageSize': 10,
    }
    assert isinstance(result['nullValueRates'][5], float)
    assert isinstance(result['nullValueRates'][6], int)
    assert 'featureId' not in result and 'extra' not in json.dumps(result)
    assert page['items'] == items  # The full quality-list tool still retains all its fields.


@pytest.mark.parametrize('value', [True, False, '0.125', '', -0.1, 1.1, float('nan'),
    float('inf'), float('-inf'), {}, [], Decimal('NaN'), Decimal('sNaN'),
    Decimal('Infinity'), 10 ** 1000])
def test_invalid_statistical_inputs_are_not_silently_counted(value):
    with pytest.raises(ApiError, match='nullValueRate'):
        null_rates_page({'items': [{'nullValueRate': value}], 'count': 1,
                         'pageIndex': 1, 'pageSize': 10})


def test_empty_rates():
    assert null_rates_page({'items': [], 'count': 0, 'pageIndex': 1, 'pageSize': 10}) == {
        'nullValueRates': [], 'count': 0, 'pageIndex': 1, 'pageSize': 10,
    }


def test_projection_precedes_output_budget_and_never_fetches_other_pages(client, app):
    ready(client)
    with app.state.db() as db:
        session_id = db.scalar(select(Session.id).where(Session.status == 'ready'))
    app.state.platform.config.runtime.max_tool_output_chars = 1000
    original = app.state.platform.transport.handler
    calls = []
    def upstream(request):
        if request.url.path == PREFIX:
            calls.append(request)
            assert request.headers['businessid'] == 'b1'
            return httpx.Response(200, json={'result': {'code': 0, 'totalCount': 300,
                'pageIndex': 2, 'pageSize': 10, 'featureList': [
                    {'nullValueRate': 0.125, 'featureName': 'large' * 10000},
                    {'nullValueRate': 0}, {'nullValueRate': 1},
                    {'nullValueRate': None}, {'featureId': 'missing'}]}})
        return original(request)
    app.state.platform.transport = httpx.MockTransport(upstream)
    result = app.state.platform.execute(session_id, None, BUSINESS,
        'list_feature_null_rates', {'page': 2}, 'rates-call')
    assert len(calls) == 1
    assert json.loads(calls[0].content)['pageIndex'] == 2
    assert result['ok'] and not result['truncated']
    assert result['data'] == {'nullValueRates': [0.125, 0, 1, None, None],
                               'count': 300, 'pageIndex': 2, 'pageSize': 10}
