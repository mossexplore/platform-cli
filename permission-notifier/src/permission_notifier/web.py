"""Loopback-only configuration UI with host, origin, cookie and CSRF checks."""
import copy
import secrets
import threading
import time
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool
from pydantic import ValidationError
from .config import Config, ready
from .records import query as query_records, TEST_CONTENT
from .service import ServiceError
from .store import Conflict, StoreError, effective


def create_app(store, worker, shutdown=None, port=18765):
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    root = Path(__file__).parent
    templates = Jinja2Templates(directory=str(root / 'templates'))
    app.mount('/static', StaticFiles(directory=root / 'static'), name='static')
    csrf, session = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    host, origin = f'127.0.0.1:{port}', f'http://127.0.0.1:{port}'

    @app.middleware('http')
    async def boundary(request, call_next):
        if request.headers.get('host') != host:
            return JSONResponse({'detail': '仅允许通过本机回环地址访问'}, status_code=403)
        if request.method not in ('GET', 'HEAD'):
            if (request.headers.get('origin') != origin or
                    not secrets.compare_digest(request.cookies.get('notifier_session', ''), session) or
                    not secrets.compare_digest(request.headers.get('x-csrf-token', ''), csrf)):
                return JSONResponse({'detail': '请求验证失败，请刷新本地页面'}, status_code=403)
            try:
                size = int(request.headers.get('content-length', '0') or '0')
            except ValueError:
                return JSONResponse({'detail': '无效请求长度'}, status_code=400)
            if size > 131072:
                return JSONResponse({'detail': '请求过大'}, status_code=413)
        response = await call_next(request)
        response.headers.update({'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer', 'Content-Security-Policy':
            "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; form-action 'self'"})
        return response

    @app.exception_handler(Exception)
    async def unexpected(request, exc):
        return JSONResponse({'detail': '操作失败，请查看助手状态（未显示敏感异常内容）'}, status_code=500)

    async def known_error(request, exc):
        if isinstance(exc, ValidationError):
            detail = '配置字段无效，请检查 URL、UID、间隔'
        elif isinstance(exc, ServiceError):
            detail = exc.code
        else:
            detail = str(exc)
        return JSONResponse({'detail': detail}, status_code=409 if isinstance(exc, Conflict) else 400)
    for error in (ValueError, ValidationError, ServiceError, StoreError, Conflict):
        app.add_exception_handler(error, known_error)

    @app.get('/')
    def home(request: Request):
        response = templates.TemplateResponse(request=request, name='index.html', context={'csrf': csrf})
        response.set_cookie('notifier_session', session, httponly=True, samesite='strict', path='/')
        return response

    @app.get('/api/status')
    def status():
        data = store.snapshot()
        unresolved = sum(i['state'] in ('failed', 'uncertain') for t in data['state']['tasks'].values()
                         for i in t['deliveries'].values())
        active = effective(data)
        signature = (active['permission_service_url'], active['assistant_token'])
        configured = all(signature)
        connected = (worker.bound_signature == signature and worker.last_heartbeat > 0
                     and time.time() - worker.last_heartbeat < 120 and not worker.error)
        connection = ('unconfigured' if not configured else 'connected' if connected else
                      'disconnected' if worker.error or worker.last_heartbeat else 'pending')
        return {'connection_state': connection, 'config_ready': ready(active),
                'paused': data['state']['paused'], 'stopping': worker.stop.is_set(),
                'worker_alive': bool(worker.thread and worker.thread.is_alive() and time.time() - worker.last_loop < 120),
                'sending': worker.sending, 'last_loop': worker.last_loop, 'last_poll': worker.last_poll,
                'last_heartbeat': worker.last_heartbeat, 'error': store.fault or worker.error,
                'last_success_at': data['state']['last_success_at'], 'pending_reports': len(data['state']['pending_reports']),
                'needs_attention': unresolved, 'pending_fields': data['state']['config_apply']['pending_fields'],
                'token_expires_at': worker.client_info.get('expires_at'),
                'test_results': worker.test_results, 'tests_waiting': len(worker.tests)}

    @app.get('/api/config')
    def config():
        return store.public_config()

    @app.put('/api/config')
    async def save_config(request: Request):
        body = await request.json()
        result = store.configure(body['config_revision'], body['config'], body.get('secrets', {}))
        if worker.sending and result['apply_state'] == 'applied':
            result['apply_state'] = 'waiting_request'
        worker.wake.set()
        return result

    def candidate(body):
        data = store.snapshot()
        values = copy.deepcopy(body.get('config', data['config']))
        for key, dest in (('assistant_token', values), ('auth', values['message'])):
            original = data['config'][key] if key == 'assistant_token' else data['config']['message'][key]
            action = body.get('secrets', {}).get(key, {'action': 'retain'})
            dest[key] = action.get('value', '') if action['action'] == 'replace' else (
                '' if action['action'] == 'clear' else original)
        return Config.model_validate(values).model_dump()

    @app.post('/api/secrets/reveal')
    async def reveal(request: Request):
        body = await request.json()
        key = body.get('field')
        if key not in ('assistant_token', 'auth'):
            raise ValueError('无效凭据字段')
        config = store.snapshot()['config']
        value = config['assistant_token'] if key == 'assistant_token' else config['message']['auth']
        return {'value': value}

    @app.get('/api/records')
    def records(start: str = '', end: str = '', source: str = '', page: int = 1, page_size: int = 10):
        return query_records(store.snapshot(), start, end, source, page, page_size)

    @app.post('/api/check')
    async def check(request: Request):
        values = candidate(await request.json())
        # Checks never claim work, send messages, or overwrite the live heartbeat.
        result = await run_in_threadpool(worker.service.call, values,
                                        store.snapshot()['state']['installation_id'], 'check')
        return {**result, 'message': '权限系统连接成功。消息接口需主动发送测试消息验证。'}

    @app.post('/api/bind')
    def bind():
        with worker.operation:
            return worker.bind()

    @app.post('/api/test-message')
    async def test(request: Request):
        body = await request.json()
        await run_in_threadpool(worker.queue_test, candidate(body), body['uids'], body.get('content', TEST_CONTENT))
        return {'queued': True}

    @app.post('/api/pause')
    def pause():
        store.change(lambda d: d['state'].update(paused=True))
        worker.wake.set()
        return {'paused': True}

    @app.post('/api/resume')
    def resume():
        if not ready(effective(store.snapshot())):
            raise ValueError('请填写地址、凭据、启用对象，并保存配置')
        store.change(lambda d: d['state'].update(paused=False))
        worker.wake.set()
        return {'paused': False}

    @app.post('/api/shutdown')
    def stop():
        worker.shutdown()
        if shutdown:
            threading.Thread(target=shutdown, daemon=True).start()
        return {'stopping': True}

    @app.get('/api/tasks')
    def tasks():
        values = store.snapshot()['state']['tasks']
        return [{'id': key, 'closed': t['closed'], 'source': t['source'], 'route': t['route'],
                 'status': t['remote']['status'], 'deliveries': {
                     key: {field: value for field, value in item.items() if field != 'rejected_auth_digest'}
                     for key, item in t['deliveries'].items()}} for key, t in values.items()]

    @app.post('/api/tasks/{task_id}/resolve')
    async def resolve(task_id: str, request: Request):
        body = await request.json()
        if body.get('confirmation') != 'confirm':
            raise ValueError('请确认已核对消息结果')
        await run_in_threadpool(worker.resolve, task_id, body.get('delivery_id', ''), body['action'])
        return {'ok': True}

    return app
