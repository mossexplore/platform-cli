"""显式数据库结构迁移；启动前执行，可重复运行。"""
from sqlalchemy import inspect, select, text
from .models import Base, CallLog, SchemaVersion

SCHEMA_VERSION = 6


def migrate(engine, sessions):
    SchemaVersion.__table__.create(engine, checkfirst=True)
    with sessions() as db:
        versions = db.scalars(select(SchemaVersion.version)).all()
        if versions not in ([], [1], [2], [3], [4], [5], [6]):
            raise RuntimeError('数据库版本不兼容，不能自动迁移')
        if not versions:
            Base.metadata.create_all(engine)
            db.add(SchemaVersion(version=SCHEMA_VERSION))
            db.commit()
            return
        version = versions[0]
    if version == 1:
        CallLog.__table__.create(engine, checkfirst=True)
    if version < 3:
        # MySQL DDL 自动提交；列检查允许 ALTER 完成后中断的迁移重跑。
        # 旧账号原本拥有全部管理权限，新增列时原子保留为超级管理员。
        columns = {column['name'] for column in inspect(engine).get_columns('admins')}
        if 'role' not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE admins ADD COLUMN role VARCHAR(32) NOT NULL DEFAULT 'super_admin'"))
    if version < 4:
        columns = {column['name'] for column in inspect(engine).get_columns('cli_call_logs')}
        if 'full_command' not in columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE cli_call_logs ADD COLUMN full_command TEXT NULL"))
    if version < 5:
        for table in ('users', 'environments'):
            columns = {column['name'] for column in inspect(engine).get_columns(table)}
            for name, kind in (('created_at', 'DATETIME'), ('updated_at', 'DATETIME'), ('updated_by', 'VARCHAR(128)')):
                if name not in columns:
                    with engine.begin() as connection:
                        connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {kind} NULL'))
    if version < 6:
        columns = {column['name'] for column in inspect(engine).get_columns('admins')}
        for name in ('created_at', 'updated_at'):
            if name not in columns:
                with engine.begin() as connection:
                    connection.execute(text(f'ALTER TABLE admins ADD COLUMN {name} DATETIME NULL'))
        with sessions() as db:
            db.get(SchemaVersion, version).version = SCHEMA_VERSION
            db.commit()
