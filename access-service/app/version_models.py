"""版本策略及临时例外；策略编辑前后值保存在操作审计中。"""
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, String, Text, func, or_, select
from sqlalchemy.orm import Mapped, mapped_column
from .models import Base, now


class VersionPolicy(Base):
    __tablename__ = 'cli_version_policies'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    # An empty environment still denotes global scope for existing policies.
    environment: Mapped[str] = mapped_column(String(64), default='')
    additional_environments: Mapped[list[str] | None] = mapped_column(JSON(none_as_null=True), nullable=True)
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

    @property
    def environments(self):
        return [self.environment, *(self.additional_environments or [])] if self.environment else []

    def matches_scope(self, environment, business_id):
        return (not self.environment or environment in self.environments) and (
            not self.business_id or self.business_id == business_id)

    @classmethod
    def in_environment(cls, db, environment):
        if db.get_bind().dialect.name == 'sqlite':
            entries = func.json_each(cls.additional_environments).table_valued('value')
            additional_match = select(1).select_from(entries).where(entries.c.value == environment).correlate(cls).exists()
        else:
            additional_match = func.json_contains(cls.additional_environments, func.json_quote(environment)) == 1
        return or_(cls.environment == environment, additional_match)


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
