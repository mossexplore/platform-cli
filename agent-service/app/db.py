from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from .models import Base, SchemaVersion

SCHEMA_VERSION = 1


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


def migrate(engine):
    # Explicit initial schema creation only; future changes require ordered migrations.
    from sqlalchemy import inspect

    if inspect(engine).has_table("agent_schema_version"):
        with engine.connect() as conn:
            versions = list(conn.execute(select(SchemaVersion.id)).scalars())
        if versions != [SCHEMA_VERSION]:
            raise RuntimeError("数据库结构版本不匹配，禁止自动修改")
        return
    existing = set(inspect(engine).get_table_names()) & set(Base.metadata.tables)
    if existing:
        raise RuntimeError("发现不完整 Agent 表，请检查初始迁移，禁止自动覆盖")
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(SchemaVersion.__table__.insert().values(id=SCHEMA_VERSION))


def verify_schema(factory):
    with factory() as db:
        if list(db.scalars(select(SchemaVersion.id))) != [SCHEMA_VERSION]:
            raise RuntimeError("请先执行 python -m app.manage migrate")
