"""在服务器本地初始化数据库和管理账号，无默认密码。"""
import argparse
import getpass
from dotenv import load_dotenv
from sqlalchemy import select, delete
from sqlalchemy.exc import SQLAlchemyError
from .models import Admin, Audit, Base, SchemaVersion, Session, CallLog, database
from .security import password_hash
from .settings import Settings


def migrate(engine, sessions):
    # 版本 2 新增调用日志表。MySQL DDL 可能自动提交，checkfirst 允许中断后重跑。
    SchemaVersion.__table__.create(engine, checkfirst=True)
    with sessions() as db:
        versions = db.scalars(select(SchemaVersion.version)).all()
        if versions not in ([], [1], [2]):
            raise RuntimeError('数据库版本不兼容，不能自动迁移')
        if not versions:
            Base.metadata.create_all(engine)
            db.add(SchemaVersion(version=2))
        elif versions == [1]:
            CallLog.__table__.create(engine, checkfirst=True)
            db.get(SchemaVersion, 1).version = 2
        db.commit()


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
            print('数据库初始化完成（版本 2）')
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
                admin = Admin(username=username, password_hash=encoded)
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
