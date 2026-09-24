"""版本策略采用追加修订，历史规则和审计可追溯。"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, now


class VersionPolicy(Base):
    __tablename__ = 'cli_version_policies'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    environment: Mapped[str] = mapped_column(String(64), default='')
    business_id: Mapped[str] = mapped_column(String(256), default='')
    mode: Mapped[str] = mapped_column(String(16), default='observe')
    minimum_version: Mapped[str] = mapped_column(String(64), default='1.0.0')
    recommended_version: Mapped[str] = mapped_column(String(64), default='')
    blocked_versions: Mapped[str] = mapped_column(Text, default='[]')
    upgrade_url: Mapped[str] = mapped_column(String(1024), default='')
    effective_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_by: Mapped[str] = mapped_column(String(128))


class VersionException(Base):
    __tablename__ = 'cli_version_exceptions'
    id: Mapped[int] = mapped_column(primary_key=True)
    policy_id: Mapped[int] = mapped_column(ForeignKey('cli_version_policies.id'))
    environment: Mapped[str] = mapped_column(String(64))
    business_id: Mapped[str] = mapped_column(String(256))
    username: Mapped[str] = mapped_column(String(128))
    minimum_version: Mapped[str] = mapped_column(String(64))
    maximum_version: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(String(1000))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    created_by: Mapped[str] = mapped_column(String(128))
