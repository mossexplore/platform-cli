"""Exactly one POST per invocation; success requires a 2xx JSON response with status=ok."""
import time
import httpx
from .diagnostics import target, failure, response_summary
from .transport import client


class Sender:
    def __init__(self, factory=client):
        self.factory = factory

    def send(self, config, route, receiver, content):
        message = config['message']
        data = {'content': content, 'receiver': receiver, 'auth': message['auth']}
        if route.get('sender'):
            data['sender'] = route['sender']
        started = time.monotonic()
        diagnostic = {"target_origin": target(route["url"]), "method": "POST"}
        try:
            with self.factory(message['network'], config['message_timeout_seconds']) as http:
                response = http.post(route['url'], json=data)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as exc:
            return {'state': 'retry_wait', 'error_code': 'NOT_CONNECTED', 'diagnostic': {**diagnostic, 'reason': failure(exc)}}
        except (httpx.HTTPError, OSError, ValueError) as exc:
            return {'state': 'uncertain', 'error_code': 'TRANSPORT_UNCERTAIN', 'diagnostic': {**diagnostic, 'reason': failure(exc)}}
        diagnostic.update(elapsed_ms=round((time.monotonic()-started)*1000),
                          response_summary=response_summary(response,
                              [message["auth"], config.get("assistant_token", "")]))
        status = response.status_code
        if status in (401, 403):
            return {'state': 'failed', 'error_code': 'MESSAGE_AUTH_REJECTED', 'http_status': status, 'diagnostic': diagnostic}
        if 300 <= status < 400:
            return {'state': 'failed', 'error_code': 'REDIRECT_REFUSED', 'http_status': status, 'diagnostic': diagnostic}
        if not 200 <= status < 300:
            return {'state': 'uncertain', 'error_code': 'HTTP_OUTCOME_UNCONFIRMED', 'http_status': status, 'diagnostic': diagnostic}
        try:
            body = response.json()
            accepted = isinstance(body, dict) and body.get('status') == 'ok'
        except ValueError:
            accepted = False
        return {'state': 'accepted' if accepted else 'uncertain', 'http_status': status,
                'error_code': '' if accepted else 'BUSINESS_OUTCOME_UNCONFIRMED',
                'diagnostic': diagnostic}
