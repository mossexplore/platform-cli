import ssl
import httpx


def client(network, timeout):
    verify = ssl.create_default_context(cafile=network['ca_file']) if network.get('ca_file') else True
    return httpx.Client(timeout=httpx.Timeout(timeout, connect=min(5, timeout)),
                        follow_redirects=False, trust_env=network.get('trust_env', True),
                        proxy=network.get('proxy') or None, verify=verify)
