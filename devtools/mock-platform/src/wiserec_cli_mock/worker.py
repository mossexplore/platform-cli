"""Preserve the explicit provider in the detached keepalive worker."""
import os
import runpy
from .bootstrap import activate

if __name__ == '__main__':
    activate(os.environ['WISEREC_DEMO_WORKSPACE'])
    runpy.run_module('wiserec_cli.ping_worker', run_name='__main__')
