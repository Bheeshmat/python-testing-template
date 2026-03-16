"""
Database setup using SQLAlchemy.

TEMPLATE NOTE:
- This file handles the DB connection only. Models live in models.py.
- get_db() is the FastAPI dependency injected into routes via Depends(get_db).
- In tests, get_db is overridden via app.dependency_overrides to use the test DB.
- For PostgreSQL in production, change DATABASE_URL in .env and remove connect_args.
"""

import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()

# ── Connection URL ────────────────────────────────────────────────────────────
# Reads from .env — falls back to SQLite for development
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")

# ── Engine ────────────────────────────────────────────────────────────────────
# check_same_thread=False is required for SQLite when used with FastAPI's
# thread pool. Not needed for PostgreSQL — guarded by the conditional below.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

# ── Session Factory ───────────────────────────────────────────────────────────
# autocommit=False: changes are not saved until you explicitly call db.commit()
# autoflush=False:  SQLAlchemy won't auto-flush pending changes before queries
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ── Base Class ────────────────────────────────────────────────────────────────
# All SQLAlchemy models inherit from this Base.
# Base.metadata knows about every model that has been imported.
# create_all(Base.metadata) creates all tables — used in tests and startup.
class Base(DeclarativeBase):
    pass


# ── FastAPI Dependency ────────────────────────────────────────────────────────
def get_db():
    """
    Yields a database session for the duration of a single request.

    Usage in routes:
        @app.get("/users")
        def list_users(db: Session = Depends(get_db)):
            ...

    The `yield` makes this a generator — code after yield runs after the
    response is sent, ensuring the session is always closed even on errors.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
