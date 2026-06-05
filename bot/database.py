"""
database.py — Async SQLAlchemy setup + table definitions
"""
from datetime import date, datetime
from typing import Optional
from sqlalchemy import (
    Boolean, Column, DateTime, Date, Integer,
    String, Text, ForeignKey, UniqueConstraint,
    func
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from bot.config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


class Base(DeclarativeBase):
    pass


# ── Models ───────────────────────────────────────────────
class User(Base):
    __tablename__ = "users"

    user_id     = Column(Integer, primary_key=True)   # Telegram user_id
    username    = Column(String(64))
    full_name   = Column(String(128))
    role        = Column(String(16), default="pending")  # dev|admin|staff|pending
    is_active   = Column(Boolean, default=True)
    joined_at   = Column(DateTime, default=func.now())
    approved_by = Column(Integer, nullable=True)


class Task(Base):
    __tablename__ = "tasks"

    task_id         = Column(String(32), primary_key=True)   # TASK-YYYYMMDD-XXX
    title           = Column(String(128), nullable=False)
    description     = Column(Text)
    sheet_tab       = Column(String(64))   # Google Sheet tab name
    quota_total     = Column(Integer, default=0)
    quota_per_staff = Column(Integer, default=0)
    deadline        = Column(DateTime)
    repeat_type     = Column(String(16), default="daily")   # daily|weekly|once
    assigned_to     = Column(Text, default='["all"]')        # JSON array
    status          = Column(String(16), default="active")  # active|paused|completed|archived
    created_by      = Column(Integer)
    created_at      = Column(DateTime, default=func.now())


class SheetURL(Base):
    """
    Cache URL yang sudah di-parse dari Spreadsheet hari ini.
    Reset setiap hari saat bot melakukan sync.
    """
    __tablename__ = "sheet_urls"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    task_id     = Column(String(32), ForeignKey("tasks.task_id"))
    date        = Column(Date, nullable=False)
    account     = Column(String(128))
    payment_url = Column(Text, nullable=False)
    notes       = Column(Text)
    status      = Column(String(16), default="PENDING")   # PENDING|OK|HTTP_ERR|TIMEOUT|DOMAIN_ERR
    http_code   = Column(Integer)
    error_msg   = Column(Text)
    verified_by = Column(Integer)   # user_id staff yang klik verif
    verified_at = Column(DateTime)
    created_at  = Column(DateTime, default=func.now())

    __table_args__ = (
        UniqueConstraint("task_id", "date", "payment_url", name="uq_task_date_url"),
    )


class TaskProgress(Base):
    __tablename__ = "task_progress"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    task_id       = Column(String(32))
    user_id       = Column(Integer)
    date          = Column(Date)
    submitted     = Column(Integer, default=0)
    verified_ok   = Column(Integer, default=0)
    verified_fail = Column(Integer, default=0)
    completed_at  = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("task_id", "user_id", "date", name="uq_progress"),
    )


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    actor_id    = Column(Integer)
    action      = Column(String(64))
    target_type = Column(String(32))
    target_id   = Column(String(64))
    detail      = Column(Text)
    timestamp   = Column(DateTime, default=func.now())


# ── Helpers ──────────────────────────────────────────────
async def init_db():
    """Create all tables if not exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session
