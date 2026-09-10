"""可直接提供 HTTP 或 HTTPS，内网无需另外安装 Nginx。"""
import os
import uvicorn


def main():
    certificate = os.environ.get('TLS_CERT_FILE') or None
    key = os.environ.get('TLS_KEY_FILE') or None
    host = os.environ.get('LISTEN_HOST', '127.0.0.1')
    if bool(certificate) != bool(key):
        raise RuntimeError('TLS_CERT_FILE 和 TLS_KEY_FILE 必须同时配置')
    uvicorn.run('app.main:create_app', factory=True, host=host,
                port=int(os.environ.get('LISTEN_PORT', '8008')),
                ssl_certfile=certificate, ssl_keyfile=key, access_log=False,
                proxy_headers=True, forwarded_allow_ips=os.environ.get('FORWARDED_ALLOW_IPS', '127.0.0.1'))


if __name__ == '__main__':
    main()
