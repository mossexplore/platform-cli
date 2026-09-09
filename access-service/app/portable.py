"""解压运行入口：加载本地配置、迁移数据库、首次创建管理员。"""
import os
from pathlib import Path
import subprocess
import sys
from dotenv import load_dotenv
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from .manage import migrate
from .models import Admin, database
from .settings import Settings
from .serve import main as serve


def prepare():
    load_dotenv(Path('.env'))
    settings = Settings.load()
    if 'CHANGE_ME' in settings.database_url:
        raise ValueError('请先修改当前目录 .env 中的 DATABASE_URL，填写实际 MySQL 连接信息。')
    engine, sessions = database(settings.database_url)
    try:
        migrate(engine, sessions)
        with sessions() as db:
            needs_admin = db.scalar(select(Admin.id).where(Admin.enabled.is_(True)).limit(1)) is None
    finally:
        engine.dispose()
    return needs_admin


def main():
    try:
        needs_admin = prepare()
        if needs_admin:
            if not sys.stdin.isatty():
                raise ValueError('尚无启用的管理员。请在交互终端执行 bash manage.sh create-admin，再启动服务。')
            print('数据库已就绪，首次启动请创建管理员（密码不会回显）。', flush=True)
            subprocess.run([sys.executable, '-m', 'app.manage', '--env-file', '.env', 'create-admin'], check=True)
    except SQLAlchemyError:
        print('数据库初始化失败，请检查 .env 中的 MySQL 地址、账号权限和网络连接。', file=sys.stderr)
        return 1
    except (ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc) if not isinstance(exc, subprocess.CalledProcessError) else '管理员创建未完成，请重新启动并重试。', file=sys.stderr)
        return 1
    protocol = 'https' if os.environ.get('TLS_CERT_FILE') else 'http'
    port = os.environ.get('LISTEN_PORT', '8008')
    print(f'管理页面：{protocol}://服务器IP:{port}；按 Ctrl+C 停止。', flush=True)
    serve()
    return 0


if __name__ == '__main__':
    sys.exit(main())
