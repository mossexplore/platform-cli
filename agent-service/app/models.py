"""Agent-owned schema. Timestamps are UTC naive at the database boundary."""

from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import (
    String,
    Text,
    Integer,
    DateTime,
    JSON,
    UniqueConstraint,
    ForeignKey,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.dialects.mysql import MEDIUMTEXT

CONTENT_TEXT = Text().with_variant(MEDIUMTEXT(), "mysql")


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def uid():
    return str(uuid4())


MYSQL_TABLE_OPTIONS = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_bin",
}


class Base(DeclarativeBase):
    # String foreign keys must use the same charset/collation on both sides.
    __table_args__ = MYSQL_TABLE_OPTIONS


class SchemaVersion(Base):
    __tablename__ = "agent_schema_version"
    id: Mapped[int] = mapped_column(primary_key=True)


class User(Base):
    __tablename__ = "agent_users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    environment_id: Mapped[str] = mapped_column(String(32))
    username: Mapped[str] = mapped_column(String(128))
    display_name: Mapped[str] = mapped_column(String(256), default="")
    department: Mapped[str] = mapped_column(String(256), default="")
    __table_args__ = (
        UniqueConstraint("environment_id", "username"),
        MYSQL_TABLE_OPTIONS,
    )


class Session(Base):
    __tablename__ = "web_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("agent_users.id"))
    environment_id: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="anonymous")
    business: Mapped[dict | None] = mapped_column(JSON)
    catalog: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    last_activity: Mapped[datetime] = mapped_column(DateTime, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class Credential(Base):
    __tablename__ = "platform_credentials"
    session_id: Mapped[str] = mapped_column(
        ForeignKey("web_sessions.id"), primary_key=True
    )
    cookie: Mapped[str] = mapped_column(Text)
    csrftoken: Mapped[str] = mapped_column(Text)
    acquired_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class Attempt(Base):
    __tablename__ = "login_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("web_sessions.id"), index=True)
    environment_id: Mapped[str] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(24), default="pending")
    error: Mapped[str] = mapped_column(String(256), default="")
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    user_id: Mapped[str] = mapped_column(ForeignKey("agent_users.id"), index=True)
    environment_id: Mapped[str] = mapped_column(String(32))
    business: Mapped[dict] = mapped_column(JSON)
    title: Mapped[str] = mapped_column(String(100), default="新对话")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class Run(Base):
    __tablename__ = "agent_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    session_id: Mapped[str] = mapped_column(ForeignKey("web_sessions.id"), index=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    client_message_id: Mapped[str] = mapped_column(String(36))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    answer: Mapped[str] = mapped_column(CONTENT_TEXT, default="")
    error: Mapped[str] = mapped_column(String(256), default="")
    history: Mapped[list] = mapped_column(JSON, default=list)
    usage: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    __table_args__ = (
        UniqueConstraint("conversation_id", "client_message_id"),
        MYSQL_TABLE_OPTIONS,
    )


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), index=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"))
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(CONTENT_TEXT)
    status: Mapped[str] = mapped_column(String(24), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Event(Base):
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
    kind: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now, index=True)


class ToolCall(Base):
    __tablename__ = "tool_calls"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    run_id: Mapped[str] = mapped_column(ForeignKey("agent_runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24))
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    request_id: Mapped[str] = mapped_column(String(36), default="")
