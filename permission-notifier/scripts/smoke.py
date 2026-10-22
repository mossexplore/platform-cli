import os, re, subprocess, tempfile, time, sys
import httpx
python=sys.executable
env=os.environ.copy()
with tempfile.TemporaryDirectory(prefix='notifier-smoke-') as directory:
    process=subprocess.Popen([python,'-m','permission_notifier.main','--headless','--data-dir',directory],env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        with httpx.Client(base_url='http://127.0.0.1:18765',trust_env=False,timeout=3) as client:
            for _ in range(100):
                if process.poll() is not None: raise RuntimeError('Assistant exited during startup')
                try:
                    page=client.get('/')
                    break
                except httpx.ConnectError: time.sleep(.1)
            else: raise RuntimeError('Local server did not start')
            assert page.status_code==200 and '权限通知助手' in page.text
            token=re.search('name="csrf-token" content="([^"]+)"',page.text)[1]
            headers={'Origin':'http://127.0.0.1:18765','X-CSRF-Token':token}
            assert client.get('/static/app.js').status_code==200
            assert client.get('/static/app.css').status_code==200
            assert client.get('/api/config').json()['config']['message']['success_mode']=='unconfirmed'
            assert client.post('/api/pause',json={},headers=headers).status_code==200
            assert client.post('/api/resume',json={},headers=headers).status_code==400
            assert client.post('/api/pause',json={},headers={**headers,'Origin':'https://foreign.example'}).status_code==403
            assert client.post('/api/shutdown',json={},headers=headers).status_code==200
        assert process.wait(timeout=15)==0
        print('Real loopback HTTP smoke passed: startup, assets, state, CSRF, safe unconfigured pause, graceful shutdown')
    finally:
        if process.poll() is None:
            process.terminate();process.wait(timeout=10)
