"""服务模拟调用的请求契约、完整展示及失败边界。"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

import test_service
from wiserec_cli.commands.service_mock import render_mock
from wiserec_cli.services.service_mock import normalize_response


PREFIX = '/ai/backend/mep/services/'
BASE = PREFIX + 'rtcContainer/queryServiceBaseInfoDetail'
DOC = PREFIX + 'queryServiceDoc'
MOCK = PREFIX + 'serviceMock'
HOST = PREFIX + 'rtcContainer/queryServiceHostList'
SAMPLE = ' {\n "data": {"queryTexts": ["测试"]}, "version": "request-version"\n} '


class ServiceMockCommandTest(unittest.TestCase):
    setUp = test_service.ServiceCommandTest.setUp
    invoke = test_service.ServiceCommandTest.invoke

    def handler(self, *, base=None, document=None, nodes=None, responses=None,
                transmission_tag=0, host_address=None, node_id='178885833284959',
                pod_ip='10.1.1.1', hosts=None, host_count=None, request_sample=SAMPLE):
        self.calls = []
        base = base if base is not None else {'code': 0, 'modelInfo': {
            'modelName': 'wrong-model', 'modelVersion': 'wrong-version',
            'businessId': 'service-tenant', 'unknown': True}, 'serviceInfo': {
            'serviceName': 'target-service', 'serviceVersion': 'service-version'}}
        document = document if document is not None else {'code': 0, 'serviceDocument': {
            'serviceId': 's', 'businessId': 'service-tenant', 'requestContent': SAMPLE}}
        nodes = nodes if nodes is not None else [self.node()]
        hosts = hosts if hosts is not None else [{'nodeId': node_id, 'nodeHost': host_address}]
        defaults = {HOST: {'result': {'code': 0, 'count': len(hosts) if host_count is None else host_count,
                                      'data': hosts}}, BASE: {'version': 'protocol-version', 'result': base},
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
            elif path == HOST:
                self.assertEqual(json.loads(request.content), {
                    'businessId': 'mep', 'serviceId': 's', 'status': '', 'hostIp': pod_ip,
                    'clusterName': '', 'preheatStatus': 'ALL', 'quotaType': None,
                    'pageIndex': 1, 'pageSize': 10})
            elif path == MOCK:
                data = {
                    'serviceId': 's', 'serviceName': 'target-service',
                    'serviceVersion': 'service-version', 'businessId': 'service-tenant',
                    'requestSample': request_sample, 'lmsServiceId': '',
                    'algoType': 'field-npy', 'transmissionTag': transmission_tag}
                if host_address is not None:
                    data['node'] = {'hostId': node_id, 'hostAddress': host_address}
                self.assertEqual(json.loads(request.content), {'data': data})
                self.assertIs(type(json.loads(request.content)['data']['transmissionTag']), int)
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

    def test_explicit_transmission_tag_is_sent_as_integer(self):
        for tag in (0, 1):
            with self.subTest(tag=tag):
                result = self.invoke(['mock', 's', '--transmission-tag', str(tag), '-o', 'json'],
                                     self.handler(transmission_tag=tag))
                self.assertEqual(result.exit_code, 0, result.output)
                self.assertEqual([r.url.path for r in self.calls], [BASE, DOC, MOCK])

    def test_invalid_transmission_tag_stops_before_requests(self):
        for tag in ('-1', '2', 'true', '0.5', ''):
            with self.subTest(tag=tag):
                calls = []
                result = self.invoke(['mock', 's', '--transmission-tag', tag],
                                     lambda r: calls.append(r))
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertEqual(calls, [])

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

    def test_host_mock_looks_up_node_and_preserves_all_results(self):
        for pod_ip, address in (('10.1.1.1', '10.1.1.1:18090'),
                                ('10.1.1.1:18090', 'returned-node-host'),
                                ('2001:db8::1', '[2001:db8::1]:18090')):
            for tag in (0, 1):
                with self.subTest(pod_ip=pod_ip, tag=tag):
                    args = ['host', 'mock', 's', '--pod-ip', f' {pod_ip} ', '-o', 'json']
                    if tag:
                        args += ['--transmission-tag', str(tag)]
                    result = self.invoke(args, self.handler(host_address=address, pod_ip=pod_ip,
                        transmission_tag=tag, nodes=[self.node(), self.node(hostName='second')]))
                    self.assertEqual(result.exit_code, 0, result.output)
                    self.assertEqual([r.url.path for r in self.calls], [HOST, BASE, DOC, MOCK])
                    nodes = json.loads(result.stdout)['result']['nodeList']
                    self.assertEqual(len(nodes), 2)
                    self.assertEqual(nodes[0]['mockResponse']['result']['文本'], '中文')
                    self.assertIn(pod_ip, result.stderr)
                    self.assertNotIn('目标主机', result.stdout)

    def test_host_mock_requires_pod_ip_and_removes_node_id(self):
        for args in (['host', 'mock', 's'], ['host', 'mock', 's', '--pod-ip', ''],
                     ['host', 'mock', 's', '--pod-ip', '   '],
                     ['host', 'mock', 's', '--pod-ip', '10.1.1.1', '--node-id', 'old-id']):
            with self.subTest(args=args):
                calls = []
                result = self.invoke(args, lambda r: calls.append(r))
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertEqual(calls, [])

    def test_host_mock_uses_two_column_tables_with_response_last_and_preserves_failures(self):
        args = ['host', 'mock', 's', '--pod-ip', '10.1.1.1']
        raw = json.dumps({'文本': '[red]中文', 'embedding': list(range(200))}, ensure_ascii=False)
        with patch('wiserec_cli.commands.service_mock.console.print') as printed:
            result = self.invoke(args, self.handler(host_address='10.1.1.1:18090', nodes=[
                self.node(mockResponse=raw), self.node(hostName='second', mockResponse='bad [red] text')]))
        # 无效节点报文仍须完整展示，命令报告失败。
        self.assertEqual(result.exit_code, 1, result.output)
        tables = [call.args[0] for call in printed.call_args_list]
        self.assertEqual(len(tables), 2)
        for table in tables:
            self.assertEqual([column.header for column in table.columns], ['字段', '值'])
            self.assertEqual([cell.plain for cell in table.columns[0]._cells],
                ['主机名称', '机器规格', '站点', '结果码', '耗时(ms)', '结果报文'])
        self.assertEqual(tables[0].columns[1]._cells[-1].plain,
                         json.dumps(json.loads(raw), ensure_ascii=False, indent=2))
        self.assertEqual(tables[0].columns[1]._cells[4].plain, '0')
        self.assertEqual(tables[1].columns[1]._cells[0].plain, 'second')
        self.assertEqual(tables[1].columns[1]._cells[-1].plain, 'bad [red] text')
        result = self.invoke(args, self.handler(host_address='10.1.1.1:18090'))
        self.assertEqual(result.exit_code, 0, result.output)
        for nodes in ([], [self.node(retCode=1)], [self.node(mockResponse='bad')]):
            with self.subTest(nodes=nodes):
                result = self.invoke(args + ['-o', 'json'], self.handler(
                    host_address='10.1.1.1:18090', nodes=nodes))
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertEqual(len(json.loads(result.stdout)['result']['nodeList']), len(nodes))

    def test_host_mock_never_replays_and_stops_on_precondition_errors(self):
        args = ['host', 'mock', 's', '--pod-ip', '10.1.1.1', '-o', 'json']
        for options, count in (({'base': {'code': 3, 'des': 'denied'}}, 2),
                               ({'document': {'code': 0}}, 3),
                               ({'responses': {MOCK: httpx.ReadTimeout('timeout')}}, 4),
                               ({'responses': {MOCK: httpx.Response(401)}}, 4),
                               ({'responses': {HOST: httpx.Response(401)}}, 1)):
            with self.subTest(options=options):
                result = self.invoke(args, self.handler(host_address='10.1.1.1:18090', **options))
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertEqual(result.stdout, '')
                self.assertEqual(len(self.calls), count)
        calls = []
        result = self.invoke(args + ['--transmission-tag', '2'], lambda r: calls.append(r))
        self.assertEqual(result.exit_code, 2, result.output)
        self.assertEqual(calls, [])

    def test_host_mock_rejects_stale_business_before_requests(self):
        data = json.loads(self.fixture.business_path.read_text())
        data['profiles']['dev']['selected']['businessId'] = 'stale'
        self.fixture.business_path.write_text(json.dumps(data))
        calls = []
        result = self.invoke(['host', 'mock', 's', '--pod-ip', '10.1.1.1'],
                             lambda r: calls.append(r))
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertEqual(calls, [])

    def test_host_mock_missing_host_stops_before_other_requests(self):
        result = self.invoke(['host', 'mock', 's', '--pod-ip', '10.1.1.1', '-o', 'json'],
                             self.handler(hosts=[]))
        self.assertEqual(result.exit_code, 1, result.output)
        self.assertIn('目前主机不存在，请检查！', result.stderr)
        self.assertEqual(result.stdout, '')
        self.assertEqual([r.url.path for r in self.calls], [HOST])

    def test_host_mock_preserves_returned_node_id_as_string(self):
        for node_id in ('178885833284959', '000178885833284959', '90071992547409931234', 178885833284959):
            with self.subTest(node_id=node_id):
                host = {'nodeId': node_id, 'nodeHost': 'address-from-host-view'}
                result = self.invoke(['host', 'mock', 's', '--pod-ip', '10.1.1.1', '-o', 'json'],
                    self.handler(host_address=host['nodeHost'], node_id=str(node_id), hosts=[host]))
                self.assertEqual(result.exit_code, 0, result.output)
                node = json.loads(self.calls[-1].content)['data']['node']
                self.assertEqual(node, {'hostId': str(node_id), 'hostAddress': host['nodeHost']})

    def test_host_mock_rejects_ambiguous_and_incomplete_host_info(self):
        for options in ({'hosts': [{'nodeId': 'a', 'nodeHost': 'ip'}, {'nodeId': 'b', 'nodeHost': 'ip'}]},
                        {'hosts': [{'nodeId': 'a', 'nodeHost': 'ip'}], 'host_count': 2},
                        {'hosts': [{'nodeHost': 'ip'}]}, {'hosts': [{'nodeId': 'a'}]},
                        {'hosts': [{'nodeId': '', 'nodeHost': 'ip'}]},
                        {'hosts': [{'nodeId': 'a', 'nodeHost': None}]},
                        {'responses': {HOST: httpx.Response(200, json={'result': {'code': 3, 'des': 'denied'}})}},
                        {'responses': {HOST: httpx.Response(200, json={'result': {'code': 0, 'count': 0}})}}):
            with self.subTest(options=options):
                result = self.invoke(['host', 'mock', 's', '--pod-ip', '10.1.1.1'], self.handler(**options))
                self.assertEqual(result.exit_code, 1, result.output)
                self.assertEqual([r.url.path for r in self.calls], [HOST])
                self.assertNotIn('目前主机不存在，请检查！', result.stderr)

    def test_sample_file_json_values_override_document_without_querying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.json'
            for host in (False, True):
                for sample in (' {\n "data":{"queryTexts":["自定义样例"]}, "value":1.25\n} ',
                               '[1,true,null]', 'null', 'false', '0'):
                    with self.subTest(host=host, sample=sample):
                        path.write_text(sample, encoding='utf-8')
                        args = ['host', 'mock', 's', '--pod-ip', '10.1.1.1'] if host else ['mock', 's']
                        args += ['--request-sample-file', str(path), '--transmission-tag', '1', '-o', 'json']
                        result = self.invoke(args, self.handler(
                            host_address='from-host-view' if host else None, request_sample=sample,
                            transmission_tag=1, document={'code': 3, 'des': 'no document'}))
                        self.assertEqual(result.exit_code, 0, result.output)
                        self.assertEqual([r.url.path for r in self.calls],
                                         ([HOST] if host else []) + [BASE, MOCK])
                        sent = json.loads(self.calls[-1].content)['data']['requestSample']
                        self.assertEqual(sent, sample)
                        self.assertIsInstance(sent, str)
                        self.assertEqual(json.loads(result.stdout)['result']['code'], 0)

    def test_inline_sample_option_is_removed_before_any_platform_request(self):
        for host in (False, True):
            args = ['host', 'mock', 's', '--pod-ip', '10.1.1.1'] if host else ['mock', 's']
            calls = []
            result = self.invoke(args + ['--request-sample', '{}'], lambda r: calls.append(r))
            self.assertEqual(result.exit_code, 2, result.output)
            self.assertEqual(calls, [])

    def test_sample_file_does_not_bypass_host_lookup(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.json'
            path.write_text('{}', encoding='utf-8')
            result = self.invoke(['host', 'mock', 's', '--pod-ip', '10.1.1.1',
                                  '--request-sample-file', str(path)], self.handler(hosts=[]))
            self.assertEqual(result.exit_code, 1, result.output)
            self.assertIn('目前主机不存在，请检查！', result.stderr)
            self.assertEqual([r.url.path for r in self.calls], [HOST])

    def test_sample_file_preserves_utf8_content_and_skips_document_query(self):
        sample = ' {\r\n "version":"1.2", "data":{"queryTexts":["中文测试"]}\r\n} '
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '样例 报文.json'
            for host in (False, True):
                for bom in (b'', b'\xef\xbb\xbf'):
                    with self.subTest(host=host, bom=bom):
                        content = bom + sample.encode('utf-8')
                        path.write_bytes(content)
                        args = ['host', 'mock', 's', '--pod-ip', '10.1.1.1'] if host else ['mock', 's']
                        args += ['--request-sample-file', str(path), '--transmission-tag', '1', '-o', 'json']
                        result = self.invoke(args, self.handler(request_sample=sample, transmission_tag=1,
                            host_address='from-host-view' if host else None,
                            document={'code': 3, 'des': 'no document'}))
                        self.assertEqual(result.exit_code, 0, result.output)
                        self.assertEqual([r.url.path for r in self.calls],
                                         ([HOST] if host else []) + [BASE, MOCK])
                        self.assertEqual(path.read_bytes(), content)
                        self.assertEqual(json.loads(self.calls[-1].content)['data']['requestSample'], sample)
                        self.assertEqual(json.loads(result.stdout)['result']['code'], 0)

    def test_removed_inline_option_is_rejected_even_with_sample_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.json'
            path.write_text('{}', encoding='utf-8')
            for host in (False, True):
                args = ['host', 'mock', 's', '--pod-ip', '10.1.1.1'] if host else ['mock', 's']
                calls = []
                result = self.invoke(args + ['--request-sample', '{}', '--request-sample-file', str(path)],
                                     lambda r: calls.append(r))
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertEqual(calls, [])

    def test_invalid_sample_files_fail_before_any_platform_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'sample.json'
            for host in (False, True):
                args = ['host', 'mock', 's', '--pod-ip', '10.1.1.1'] if host else ['mock', 's']
                for content in (b'', b'  ', b'{bad}', b'{"a":1,}', b'NaN', b'{"a":Infinity}', b'1e999', b'{} extra'):
                    with self.subTest(host=host, content=content):
                        path.write_bytes(content)
                        calls = []
                        result = self.invoke(args + ['--request-sample-file', str(path)],
                                             lambda r: calls.append(r))
                        self.assertEqual(result.exit_code, 2, result.output)
                        self.assertIn('样例报文不是标准的JSON格式，请检查！', result.stderr)
                        self.assertEqual(calls, [])
                for value in (str(Path(directory) / 'missing.json'), directory):
                    calls = []
                    result = self.invoke(args + ['--request-sample-file', value], lambda r: calls.append(r))
                    self.assertEqual(result.exit_code, 2, result.output)
                    self.assertEqual(calls, [])
                path.write_bytes(b'\xff\xfe{\x00}\x00')
                calls = []
                result = self.invoke(args + ['--request-sample-file', str(path)], lambda r: calls.append(r))
                self.assertEqual(result.exit_code, 2, result.output)
                self.assertIn('UTF-8', result.stderr)
                self.assertEqual(calls, [])
