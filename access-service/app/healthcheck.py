"""Probe the running HTTP service, including its database/schema health."""
import json
import os
import sys
import urllib.request


def main():
    url = os.environ.get('HEALTHCHECK_URL', 'http://127.0.0.1:8008/cli-permission/healthz')
    try:
        # A local health probe must not follow environment HTTP proxies.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=3) as response:
            return 0 if response.status == 200 and json.load(response) == {'status': 'ok'} else 1
    except (OSError, ValueError):
        return 1


if __name__ == '__main__':
    sys.exit(main())
