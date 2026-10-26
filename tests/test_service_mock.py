"""服务模拟调用的请求契约、完整展示及失败边界。"""

import json
import unittest
from unittest.mock import patch

import httpx

import test_service
from wiserec_cli.commands.service_mock import render_mock
from wiserec_cli.services.service_mock import normalize_response


PREFIX = '/ai/backend/mep/services/'
BASE = PREFIX + 'rtcContainer/queryServiceBaseInfoDetail'
DOC = PREFIX + 'queryServiceDoc'
MOCK = PREFIX + 'serviceMock'
SAMPLE = ' {\n "data": {"queryTexts": ["测试"]}, "version": "request-version"\n} '


class ServiceMockCommandTest(unittest.TestCase):
    setUp = test_service.ServiceCommandTest.setUp
    invoke = test_service.ServiceCommandTest.invoke

    def handler(self, *, base=None, document=None, nodes=None, responses=None):
        self.calls = []
        base = base if base is not None else {'code': 0, 'modelInfo': {
            'modelName': 'wrong-model', 'modelVersion': 'wrong-version',
            'businessId': 'service-tenant', 'unknown': True}, 'serviceInfo': {
            'serviceName': 'target-service', 'serviceVersion': 'service-version'}}
        document = document if document is not None else {'code': 0, 'serviceDocument': {
            'serviceId': 's', 'businessId': 'service-tenant', 'requestContent': SAMPLE}}
        nodes = nodes if nodes is not None else [self.node()]
        defaults = {BASE: {'version': 'protocol-version', 'result': base},
                    DOC: {'result': document}, MOCK: {'version': '1.0',
                    'meta': {'uuid': 'trace'}, 'extra': {'keep': True},
                    'result': {'code': 0, 'nodeList': nodes, 'unknown': [1]}}}

        def handle(request):
            self.calls.append(request)
            self.assertEqual(request.method, 'POST')
            self.assertEqual(request.url.host, 'dev.example.com')
            self.assertEqual(request.headers['businessid'], 'mep')
            path = request.url.path
            if path in (BASE, DOC):
                self.assertEqual(json.loads(request.content), {'serviceId': 's'})
            elif path == MOCK:
                self.assertEqual(json.loads(request.content), {'data': {
                    'serviceId': 's', 'serviceName': 'target-service',
                    'serviceVersion': 'service-version', 'businessId': 'service-tenant',
                    'requestSample': SAMPLE, 'lmsServiceId': '',
                    'algoType': 'field-npy', 'transmissionTag': 0}})
            else:
                self.fail(f'Unexpected request: {path}')
            override = (responses or {}).get(path)
            if isinstance(override, Exception):
                raise override
            return override or httpx.Response(200, json=defaults[path])
        return handle

    @staticmethod
    def node(**changes):
        return {'hostName': 'host-[red]-1', 'scope': '15C57G', 'domain': 'runze',
                'retCode': 0, 'mockResponse': '{"result":{"code":0,"文本":"中文"}}',
                'cost': 0, 'extra': [1, 2], **changes}

    def test_three_calls_and_json_preserves_unknown_fields(self):
        handler = self.handler(nodes=[self.node(), self.node(hostName='host-2')])
        result = self.invoke(['mock', ' s ', '-o', 'json'], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual([r.url.path for r in self.calls], [BASE, DOC, MOCK])
        payload = json.loads(result.stdout)
        self.assertEqual(payload['extra'], {'keep': True})
        self.assertEqual(payload['meta']['uuid'], 'trace')
        self.assertEqual(payload['result']['unknown'], [1])
        nodes = payload['result']['nodeList']
        self.assertEqual(len(nodes), 2)
        self.assertEqual(nodes[0]['mockResponse']['result']['文本'], '中文')
        self.assertEqual(nodes[0]['mockResponseRaw'], self.node()['mockResponse'])
        self.assertEqual(nodes[0]['extra'], [1, 2])
        self.assertEqual(nodes[0]['cost'], 0)

    def test_table_has_six_columns_and_full_pretty_json(self):
        raw = json.dumps({'embedding': list(range(200)), '文本': '[red]中文'}, ensure_ascii=False)
        handler = self.handler(nodes=[self.node(mockResponse=raw)])
        with patch('wiserec_cli.commands.service_mock.console.print') as printed:
            result = self.invoke(['mock', 's', '-o', 'table'], handler)
        self.assertEqual(result.exit_code, 0, result.output)
        table = printed.call_args.args[0]
        self.assertEqual([c.header for c in table.columns],
                         ['主机名称', '机器规格', '站点', '结果码', '结果报文', '耗时(ms)'])
        self.assertEqual(table.columns[0]._cells[0].plain, 'host-[red]-1')
        text = table.columns[4]._cells[0].plain
        self.assertEqual(text, json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
        self.assertEqual(table.columns[5]._cells[0].plain, '0')
        self.assertTrue(table.show_lines)

    def test_preconditions_stop_before_mock(self):
        for options, count in [
            ({'base': {'code': 3, 'des': 'denied'}}, 1),
            ({'base': {'code': 0, 'modelInfo': {}, 'serviceInfo': {}}}, 1),
            ({'document': {'code': 0}}, 2),
            ({'document': {'code': 0, 'serviceDocument': {'requestContent': ''}}}, 2),
            ({'document': {'code': 0, 'serviceDocument': {'requestContent': '{bad'}}}, 2),
            ({'document': {'code': 0, 'serviceDocument': {'requestContent': 'NaN'}}}, 2),
            ({'document': {'code': 0, 'serviceDocument': {'requestContent': '1e999'}}}, 2),
            ({'document': {'code': 0, 'serviceDocument': {
                'requestContent': SAMPLE, 'serviceId': 'other'}}}, 2),
            ({'document': {'code': 0, 'serviceDocument': {
                'requestContent': SAMPLE, 'businessId': 'other'}}}, 2),
        ]:
            with self.subTest(options=options):
                result = self.invoke(['mock', 's', '-o', 'json'], self.handler(**options))
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertEqual(result.stdout, '')
                self.assertEqual(len(self.calls), count)

    def test_bad_nodes_still_emit_all_results_and_exit_one(self):
        for nodes in ([], [self.node(retCode=3)], [self.node(retCode=None)],
                      [self.node(mockResponse='not JSON'), self.node(hostName='good')],
                      [self.node(mockResponse='NaN')], [self.node(mockResponse='')]):
            with self.subTest(nodes=nodes):
                result = self.invoke(['mock', 's', '-o', 'json'], self.handler(nodes=nodes))
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertEqual(len(json.loads(result.stdout)['result']['nodeList']), len(nodes))
                self.assertEqual(len(self.calls), 3)

    def test_mock_failures_are_never_replayed(self):
        for response in (httpx.ReadTimeout('timeout'), httpx.Response(401),
                         httpx.Response(500), httpx.Response(200, text='invalid'),
                         httpx.Response(200, json={'result': {'code': 3, 'des': 'denied'}}),
                         httpx.Response(200, json={'result': {'code': 0}}),
                         httpx.Response(200, json={'result': {'code': 0, 'nodeList': [None]}})):
            with self.subTest(response=response):
                result = self.invoke(['mock', 's'], self.handler(responses={MOCK: response}))
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertEqual(len(self.calls), 3)
                self.assertEqual(result.stdout, '')

    def test_validation_happens_before_requests(self):
        for args in (['mock', ' '], ['mock', 's', '-o', 'bad']):
            calls = []
            result = self.invoke(args, lambda r: calls.append(r))
            self.assertEqual(result.exit_code, 1)
            self.assertEqual(calls, [])
        data = json.loads(self.fixture.business_path.read_text())
        data['profiles']['dev']['selected']['businessId'] = 'stale'
        self.fixture.business_path.write_text(json.dumps(data))
        calls = []
        result = self.invoke(['mock', 's'], lambda r: calls.append(r))
        self.assertEqual(result.exit_code, 1)
        self.assertEqual(calls, [])

    def test_valid_json_values_and_invalid_plain_text_are_displayed(self):
        for raw in ('null', 'false', '0', '"text"', '[1,2]', 'plain [red] text'):
            payload = {'result': {'nodeList': [self.node(mockResponse=raw)]}}
            normalized, issues = normalize_response(payload)
            with patch('wiserec_cli.commands.service_mock.console.print') as printed:
                render_mock(normalized, 'table')
            text = printed.call_args.args[0].columns[4]._cells[0].plain
            self.assertEqual(text, raw if issues else json.dumps(json.loads(raw), indent=2))
            self.assertEqual(payload['result']['nodeList'][0]['mockResponse'], raw)
