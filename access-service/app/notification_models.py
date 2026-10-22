"""Notification data is service-only; no message credentials or receiver UIDs."""
from datetime import datetime
from uuid import uuid4
from sqlalchemy import Boolean, DateTime, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, now


class NotificationClient(Base):
    __tablename__ = 'notification_clients'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    owner_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    token_hash: Mapped[str] = mapped_column(String(64), default='')
    credential_generation: Mapped[int] = mapped_column(Integer, default=0)
    bind_deadline: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    installation_id: Mapped[str] = mapped_column(String(64), default='')
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    agent_version: Mapped[str] = mapped_column(String(32), default='')
    health_code: Mapped[str] = mapped_column(String(64), default='unknown')
    revision: Mapped[int] = mapped_column(Integer, default=0)


class NotificationTask(Base):
    __tablename__ = 'notification_tasks'
    __table_args__ = (Index('ix_notification_ready', 'status', 'created_at'),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    event_key: Mapped[str] = mapped_column(String(128), unique=True)
    application_id: Mapped[int] = mapped_column(Integer, index=True)
    status: Mapped[str] = mapped_column(String(24), default='pending')
    installation_id: Mapped[str] = mapped_column(String(64), default='')
    lease_generation: Mapped[int] = mapped_column(Integer, default=0)
    lease_token_hash: Mapped[str] = mapped_column(String(64), default='')
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    snapshot_id: Mapped[str] = mapped_column(String(64), default='')
    data: Mapped[str] = mapped_column(Text, default='{"deliveries":{},"reports":{},"actions":{}}')
    report_seq: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now)


def enqueue(db, application):
    client = db.get(NotificationClient, 1)
    if client and client.enabled:
        db.flush()
        db.add(NotificationTask(application_id=application.id,
                                event_key=f'application_submitted:{application.id}'))
