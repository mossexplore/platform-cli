"""Single-worker, one-shot approvals bound to immutable validated arguments.

Requests are persisted as audit events. Pending permits deliberately do not survive
restart: startup already interrupts runs. Models cannot call the decision endpoint.
"""
import asyncio
import copy
import json
from uuid import uuid4
from .errors import AppError


class Approvals:
    def __init__(self):
        self.pending = {}
        self.permits = {}

    async def request(self, sid, run_id, business, name, args, emit, details=None):
        key = str(uuid4())
        snapshot = copy.deepcopy(args)
        future = asyncio.get_running_loop().create_future()
        record = {'session_id': sid, 'run_id': run_id, 'name': name,
                  'arguments': snapshot, 'business': copy.deepcopy(business), 'future': future}
        self.pending[key] = record
        try:
            await emit('action.required', {'action_id': key, 'name': name,
                'arguments': snapshot, 'business': business, 'details': details})
            accepted = await future
            await emit('action.decided', {'action_id': key, 'approved': accepted})
            if not accepted:
                raise AppError('ACTION_REJECTED', '用户拒绝执行操作', 409)
            token = str(uuid4())
            self.permits[token] = self.fingerprint(sid, run_id, business, name, snapshot)
            return token
        finally:
            self.pending.pop(key, None)

    def decide(self, key, sid, run_id, approved):
        record = self.pending.get(key)
        if not record or record['session_id'] != sid or record['run_id'] != run_id:
            raise AppError('ACTION_NOT_FOUND', '确认请求已过期或不属于本次会话', 404)
        if record['future'].done():
            raise AppError('ACTION_DECIDED', '该请求已经处理', 409)
        record['future'].set_result(approved)

    @staticmethod
    def fingerprint(sid, run_id, business, name, args):
        return json.dumps([sid, run_id, business, name, args], sort_keys=True, ensure_ascii=False)

    def consume(self, token, sid, run_id, business, name, args):
        expected = self.permits.pop(token, None)
        if expected != self.fingerprint(sid, run_id, business, name, args):
            raise AppError('CONFIRMATION_REQUIRED', '此操作需要网页确认具体参数', 403)

    def clear(self, run_id):
        for key, value in list(self.permits.items()):
            if json.loads(value)[1] == run_id:
                self.permits.pop(key, None)
