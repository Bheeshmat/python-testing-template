"""
SQLAlchemy models — the database table definitions.

TEMPLATE NOTE:
- Replace User and Task with your own domain models.
- All models must inherit from Base (imported from database.py).
- IMPORTANT: All model files must be imported in tests/conftest.py
  before Base.metadata.create_all() is called, otherwise tables won't be created.
  See the import comment in conftest.py.
"""

import enum
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from src.database import Base


# ── Enums ─────────────────────────────────────────────────────────────────────
# Using Python enums + SQLAlchemy String columns (more portable than DB-level enums)
class TierEnum(enum.StrEnum):
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class TaskStatusEnum(enum.StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriorityEnum(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ── User Model ────────────────────────────────────────────────────────────────
class User(Base):
    """
    Represents a registered user.

    Relationships:
        user.tasks  → list of Task objects belonging to this user
    """

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    tier = Column(String(20), default=TierEnum.FREE, nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # One-to-many: one User has many Tasks
    # cascade="all, delete-orphan": deleting a user also deletes their tasks
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")


# ── Task Model ────────────────────────────────────────────────────────────────
class Task(Base):
    """
    Represents a task belonging to a user.

    Relationships:
        task.user  → the User object who owns this task
    """

    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(String(2000), nullable=True)
    status = Column(String(20), default=TaskStatusEnum.TODO, nullable=False)
    priority = Column(String(20), default=TaskPriorityEnum.MEDIUM, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Many-to-one: many Tasks belong to one User
    user = relationship("User", back_populates="tasks")


# ── Feature Flag Model ────────────────────────────────────────────────────────
class FeatureFlag(Base):
    """
    Controls feature visibility without redeploying.

    Usage:
        - enabled=True              → feature on for ALL users
        - enabled=False             → feature off for all users
        - enabled=False +
          allowed_user_ids=[1,2,3] → off globally, on for specific users only
                                     (useful for internal testing in production)

    Example flags:
        "ai_summary"       → AI task summary feature
        "new_dashboard"    → redesigned dashboard
        "bulk_import"      → CSV bulk task import
    """

    __tablename__ = "feature_flags"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False, index=True)
    enabled = Column(Boolean, default=False, nullable=False)

    # JSON list of user IDs who can see this feature even when globally disabled.
    # e.g. [1, 5, 23]  → these users see the feature regardless of `enabled`
    # Stored as JSON so no separate join table is needed (simple use case).
    allowed_user_ids = Column(JSON, default=list, nullable=False)

    description = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
