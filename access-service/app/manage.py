"""在服务器本地初始化数据库和管理账号，无默认密码。"""
import argparse
import getpass
from dotenv import load_dotenv
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError
from .models import Admin, Audit, Session, database
from .migrations import migrate, SCHEMA_VERSION
from .security import password_hash
from .settings import Settings


def main():
    parser = argparse.ArgumentParser(description='CLI 权限服务管理')
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('command', choices=['migrate', 'create-admin', 'reset-password'])
    args = parser.parse_args()
    load_dotenv(args.env_file)
    engine, sessions = database(Settings.load().database_url)
    try:
        if args.command == 'migrate':
            migrate(engine, sessions)
            print(f'数据库初始化完成（版本 {SCHEMA_VERSION}）')
            return
        username = input('管理员账号: ').strip()
        if not username or len(username) > 128:
            raise ValueError('账号须为 1–128 个字符')
        password = getpass.getpass('管理员密码（至少 12 个字符）: ')
        if password != getpass.getpass('再次输入密码: '):
            raise ValueError('两次输入的密码不一致')
        encoded = password_hash(password)
        with sessions() as db:
            admin = db.scalar(select(Admin).where(Admin.username == username))
            if args.command == 'create-admin':
                if admin:
                    raise ValueError('管理员已存在，请使用 reset-password 重置密码')
                admin = Admin(username=username, password_hash=encoded, role="super_admin")
                db.add(admin)
            else:
                if not admin:
                    raise ValueError('管理员不存在')
                admin.password_hash = encoded
                db.execute(delete(Session).where(Session.admin_id == admin.id))
            db.add(Audit(actor=username, action=args.command, detail='服务器本地管理操作'))
            db.commit()
        print('管理员配置成功')
    except SQLAlchemyError:
        parser.exit(1, '数据库操作失败，请检查 MySQL 连接及迁移状态\n')
    except (ValueError, RuntimeError) as exc:
        parser.exit(1, str(exc) + '\n')
    finally:
        engine.dispose()


if __name__ == '__main__':
    main()
