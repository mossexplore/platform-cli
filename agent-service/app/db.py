"""Explicit initialization; a version marker is written only after all tables exist."""

import hashlib
from sqlalchemy import create_engine, select, inspect, text
from sqlalchemy.orm import sessionmaker
from .models import Base, SchemaVersion

SCHEMA_VERSION = 1


class SchemaError(RuntimeError):
    """Only application-owned, non-secret schema diagnostics may use this type."""


def connect(config, test_url=None):
    engine = create_engine(
        test_url or config.database.url(),
        pool_pre_ping=True,
        **(
            {"connect_args": {"check_same_thread": False}}
            if test_url and test_url.startswith("sqlite")
            else {"pool_recycle": 1800}
        ),
    )
    return engine, sessionmaker(engine, expire_on_commit=False)


def verify_tables(connection):
    inspector = inspect(connection)
    existing = set(inspector.get_table_names())
    missing = set(Base.metadata.tables) - existing
    if missing:
        raise SchemaError("数据库缺少 Agent 表：" + ", ".join(sorted(missing)))
    for name, table in Base.metadata.tables.items():
        columns = {c["name"] for c in inspector.get_columns(name)}
        if columns != set(table.columns.keys()):
            raise SchemaError(f"表 {name} 的字段与当前结构不一致，禁止自动覆盖")
        expected = {
            ((fk.parent.name,), fk.column.table.name, (fk.column.name,))
            for fk in table.foreign_keys
        }
        actual = {
            (
                tuple(fk["constrained_columns"]),
                fk["referred_table"],
                tuple(fk["referred_columns"]),
            )
            for fk in inspector.get_foreign_keys(name)
        }
        if expected != actual:
            raise SchemaError(f"表 {name} 的外键与当前结构不一致，禁止自动覆盖")


def _initialize(connection):
    existing = set(inspect(connection).get_table_names())
    if SchemaVersion.__tablename__ in existing:
        versions = list(connection.execute(select(SchemaVersion.id)).scalars())
        if versions != [SCHEMA_VERSION]:
            raise SchemaError(
                "结构版本为空或不匹配，可能存在未完成初始化；请核查，禁止手动写入版本号"
            )
        verify_tables(connection)
        return
    if existing:
        raise SchemaError(
            "目标数据库非空且没有有效 Agent 版本；请使用独立空库，禁止自动覆盖或补建"
        )
    # MySQL DDL cannot be rolled back. Never create the version table first.
    for table in Base.metadata.sorted_tables:
        if table is not SchemaVersion.__table__:
            table.create(connection, checkfirst=False)
    SchemaVersion.__table__.create(connection, checkfirst=False)
    verify_tables(connection)
    connection.execute(SchemaVersion.__table__.insert().values(id=SCHEMA_VERSION))


def migrate(engine):
    # Keep the MySQL advisory lock on the same connection across implicit DDL commits.
    with engine.connect() as connection:
        lock = None
        try:
            if connection.dialect.name == "mysql":
                database = connection.scalar(text("SELECT DATABASE()"))
                candidate = (
                    "wiserec-agent-init:"
                    + hashlib.sha256(str(database).encode()).hexdigest()[:32]
                )
                if (
                    connection.scalar(
                        text("SELECT GET_LOCK(:name, 0)"), {"name": candidate}
                    )
                    != 1
                ):
                    raise SchemaError("另一个初始化进程正在运行，请等待其结束")
                lock = candidate
            _initialize(connection)
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            if lock:
                connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": lock})
                connection.commit()


def verify_schema(factory):
    with factory() as db:
        if list(db.scalars(select(SchemaVersion.id))) != [SCHEMA_VERSION]:
            raise SchemaError("请先执行 python -m app.manage migrate")
        verify_tables(db.connection())
