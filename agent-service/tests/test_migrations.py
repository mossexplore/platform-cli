import pytest
from sqlalchemy import create_engine, event, inspect, select, text
from sqlalchemy.orm import sessionmaker
from app.db import migrate, verify_schema, SchemaError
from app.models import Base, SchemaVersion, User


@pytest.fixture
def engine(tmp_path):
    engine = create_engine("sqlite:///" + str(tmp_path / "schema.db"))
    yield engine
    engine.dispose()


def test_fresh_initialization_creates_version_last_and_is_repeatable(engine):
    created = []

    def record(table, connection, **kwargs):
        created.append(table.name)

    for table in Base.metadata.tables.values():
        event.listen(table, "after_create", record)
    try:
        migrate(engine)
        assert created[-1] == "agent_schema_version"
        assert set(created) == set(Base.metadata.tables)
        migrate(engine)
        assert len(created) == len(Base.metadata.tables)
        verify_schema(sessionmaker(engine))
        with engine.connect() as connection:
            assert list(connection.execute(select(SchemaVersion.id)).scalars()) == [1]
    finally:
        for table in Base.metadata.tables.values():
            event.remove(table, "after_create", record)


def test_failed_ddl_leaves_no_success_marker_and_retry_does_not_modify(engine):
    def fail(table, connection, **kwargs):
        raise RuntimeError("simulate DDL failure")

    event.listen(User.__table__, "after_create", fail)
    try:
        with pytest.raises(RuntimeError, match="simulate"):
            migrate(engine)
    finally:
        event.remove(User.__table__, "after_create", fail)
    before = set(inspect(engine).get_table_names())
    assert before == {"agent_users"}
    with pytest.raises(SchemaError, match="非空"):
        migrate(engine)
    assert set(inspect(engine).get_table_names()) == before


def test_legacy_two_empty_tables_are_not_silently_repaired(engine):
    SchemaVersion.__table__.create(engine)
    User.__table__.create(engine)
    with pytest.raises(SchemaError, match="版本为空"):
        migrate(engine)
    assert set(inspect(engine).get_table_names()) == {
        "agent_schema_version",
        "agent_users",
    }


def test_version_marker_alone_cannot_pass_validation(engine):
    SchemaVersion.__table__.create(engine)
    with engine.begin() as connection:
        connection.execute(SchemaVersion.__table__.insert().values(id=1))
    with pytest.raises(SchemaError, match="缺少 Agent 表"):
        migrate(engine)
    with pytest.raises(SchemaError, match="缺少 Agent 表"):
        verify_schema(sessionmaker(engine))


def test_unrelated_database_is_not_modified(engine):
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE important_data (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO important_data VALUES (7)"))
    with pytest.raises(SchemaError, match="独立空库"):
        migrate(engine)
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT id FROM important_data")) == 7
    assert inspect(engine).get_table_names() == ["important_data"]
