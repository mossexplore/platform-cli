"""Exactly one POST per invocation; never infer business success by default."""
import json
import httpx
from .transport import client


class Sender:
    def __init__(self, factory=client):
        self.factory = factory

    def send(self, config, route, receiver, content):
        message = config['message']
        data = {'content': content, 'receiver': receiver, 'auth': message['auth']}
        if route.get('sender'):
            data['sender'] = route['sender']
        try:
            with self.factory(message['network'], config['message_timeout_seconds']) as http:
                response = http.post(route['url'], json=data)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout):
            return {'state': 'retry_wait', 'error_code': 'NOT_CONNECTED'}
        except (httpx.HTTPError, OSError, ValueError):
            return {'state': 'uncertain', 'error_code': 'TRANSPORT_UNCERTAIN'}
        status = response.status_code
        if status in (401, 403):
            return {'state': 'failed', 'error_code': 'MESSAGE_AUTH_REJECTED', 'http_status': status}
        if 300 <= status < 400:
            return {'state': 'failed', 'error_code': 'REDIRECT_REFUSED', 'http_status': status}
        if not 200 <= status < 300:
            return {'state': 'uncertain', 'error_code': 'HTTP_OUTCOME_UNCONFIRMED', 'http_status': status}
        mode = message['success_mode']
        accepted = mode == 'http_2xx'
        if mode == 'json_equals':
            try:
                value = response.json()
                for key in message['success_field'].split('.'):
                    value = value[key]
                expected = json.loads(message['success_value'])
                accepted = type(value) is type(expected) and value == expected
            except (ValueError, KeyError, TypeError):
                accepted = False
        return {'state': 'accepted' if accepted else 'uncertain', 'http_status': status,
                'error_code': '' if accepted else 'BUSINESS_OUTCOME_UNCONFIRMED'}
