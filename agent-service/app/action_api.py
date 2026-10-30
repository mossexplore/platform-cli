"""Browser-only confirmation and attachment endpoints, protected by session/CSRF."""
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, StrictBool
from .sessions import request_session, valid, protect
from .chat_api import run_owned
from .artifacts import Artifacts, MAX_BYTES
from .errors import AppError

router = APIRouter(prefix='/api')


class Decision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    approved: StrictBool


@router.post('/runs/{run_id}/actions/{key}')
async def decide(run_id: str, key: str, body: Decision, request: Request):
    with request.app.state.db() as db:
        s = request_session(request, db)
        protect(request, s)
        valid(db, request.app.state.config, s.id)
        run = run_owned(db, s, run_id)
        if run.status != 'running':
            raise AppError('RUN_CANCELLED', '运行已停止', 409)
        request.app.state.runs.approvals.decide(key, s.id, run_id, body.approved)
    return {'accepted': True}


def scope(request, write=False):
    with request.app.state.db() as db:
        s = request_session(request, db)
        if write: protect(request, s)
        valid(db, request.app.state.config, s.id)
        if not s.business:
            raise AppError('BUSINESS_REQUIRED', '请先选择业务')
        return Artifacts(request.app.state.config, s.id, s.business)


@router.post('/artifacts')
async def upload(request: Request, name: str = 'attachment.bin'):
    store = scope(request, True)
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_BYTES:
            raise AppError('FILE_TOO_LARGE', '附件超过 20 MiB 限制', 413)
        data.extend(chunk)
    # Revalidate expiry/logout after receiving the body.
    scope(request, True)
    return store.put(name, bytes(data))


@router.get('/artifacts/{key}')
def download(key: str, request: Request):
    store = scope(request)
    path = store.path(key)
    return FileResponse(path, filename=path.name, media_type='application/octet-stream',
                        headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})
