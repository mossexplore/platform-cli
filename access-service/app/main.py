from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from . import access, admin, admin_auth, call_logs
from .models import SchemaVersion, database
from .security import display_time
from .settings import Settings


def create_app(settings=None):
    app = FastAPI(title='CLI 权限管理', docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings or Settings.load()
    app.state.engine, app.state.sessions = database(app.state.settings.database_url)
    directory = Path(__file__).parent
    app.state.templates = Jinja2Templates(directory=str(directory / 'templates'))
    app.state.templates.env.filters['beijing'] = display_time
    app.mount('/static', StaticFiles(directory=directory / 'static'), name='static')
    app.include_router(admin_auth.router)
    app.include_router(admin.router)
    app.include_router(access.router)
    app.include_router(call_logs.router)

    @app.middleware('http')
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    def error_response(request, message, status):
        if request.url.path.startswith('/api/') or request.url.path == '/healthz':
            return JSONResponse({'detail': message}, status_code=status)
        return app.state.templates.TemplateResponse(request=request, name='error.html',
            context={'message': message}, status_code=status)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc):
        return error_response(request, str(exc.detail), exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        return error_response(request, '请求字段缺失或格式错误，请检查后重试', 422)

    @app.exception_handler(IntegrityError)
    async def duplicate(request: Request, exc):
        return error_response(request, '账号、环境或授权已存在，请返回页面编辑已有记录', 409)

    @app.exception_handler(SQLAlchemyError)
    async def unavailable(request: Request, exc):
        # 不返回或记录含数据库连接信息、参数的原始异常。
        return error_response(request, '数据库不可用或未初始化，请检查服务配置和数据库迁移', 503)

    @app.get('/')
    def index():
        return RedirectResponse('/admin', status_code=303)

    @app.get('/healthz')
    def health():
        with app.state.sessions() as db:
            if db.scalar(select(SchemaVersion.version)) != 2:
                return JSONResponse({'status': 'schema_not_ready'}, status_code=503)
        return {'status': 'ok'}

    return app
