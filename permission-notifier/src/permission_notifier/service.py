from .transport import client


class ServiceError(RuntimeError):
    def __init__(self, code, status=0):
        self.code, self.status = code, status
        super().__init__(code)


class Service:
    def __init__(self, factory=client):
        self.factory = factory

    def call(self, config, installation, endpoint, body=None):
        base = config['permission_service_url'].rstrip('/')
        if not base.endswith('/cli-permission'):
            base += '/cli-permission'
        payload = {'protocol_version': 1, 'installation_id': installation, **(body or {})}
        try:
            with self.factory(config['service_network'], 10) as http:
                response = http.post(base + '/api/v1/notifications/' + endpoint.lstrip('/'),
                    json=payload, headers={'Authorization': 'Bearer ' + config['assistant_token']})
        except Exception:
            raise ServiceError('SERVICE_UNAVAILABLE') from None
        try:
            result = response.json()
        except ValueError:
            raise ServiceError('INVALID_SERVICE_RESPONSE', response.status_code) from None
        if not response.is_success:
            code = result.get('detail', 'SERVICE_ERROR') if isinstance(result, dict) else 'SERVICE_ERROR'
            # Do not leak arbitrary remote error bodies or request credentials.
            if not isinstance(code, str) or len(code) > 64 or not code.replace('_', '').isalnum():
                code = 'SERVICE_ERROR'
            raise ServiceError(code, response.status_code)
        if not isinstance(result, dict):
            raise ServiceError('INVALID_SERVICE_RESPONSE')
        return result
