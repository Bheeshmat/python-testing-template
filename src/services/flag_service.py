"""
Feature flag service — controls feature visibility at runtime.

Why this exists:
    Decouples feature deployment from feature release.
    Code can be deployed to production with a flag OFF,
    tested internally, then turned ON without redeploying.

Usage in a route:
    from src.services import flag_service

    @app.get("/tasks/{id}/summary")
    def get_summary(task_id: int, user=Depends(get_current_user), db=Depends(get_db)):
        if not flag_service.is_enabled("ai_summary", user_id=user["user_id"], db=db):
            raise HTTPException(status_code=404)
        return ai_service.summarise(task_id)
"""

from sqlalchemy.orm import Session

from src.models import FeatureFlag


def is_enabled(flag_name: str, db: Session, user_id: int | None = None) -> bool:
    """
    Check if a feature flag is enabled for the given user.

    Logic:
        1. Flag not found       → False (safe default, unknown flags are off)
        2. flag.enabled = True  → True for everyone
        3. flag.enabled = False → check allowed_user_ids
            - user_id in list   → True (per-user override, useful for internal testing)
            - user_id not in list or user_id is None → False

    Args:
        flag_name: The flag identifier, e.g. "ai_summary"
        db:        SQLAlchemy session
        user_id:   Optional. The current user's ID for per-user overrides.

    Returns:
        bool: True if the feature should be shown, False otherwise.
    """
    flag = db.query(FeatureFlag).filter(FeatureFlag.name == flag_name).first()

    # Unknown flag → off by default (fail safe)
    if flag is None:
        return False

    # Globally enabled → on for everyone
    if flag.enabled:
        return True

    # Globally disabled but check per-user override
    if user_id is not None and user_id in (flag.allowed_user_ids or []):
        return True

    return False


def get_flag(flag_name: str, db: Session) -> FeatureFlag | None:
    """Retrieve a flag by name. Returns None if not found."""
    return db.query(FeatureFlag).filter(FeatureFlag.name == flag_name).first()


def get_all_flags(db: Session) -> list[FeatureFlag]:
    """Retrieve all feature flags. Used by the admin endpoint."""
    return db.query(FeatureFlag).order_by(FeatureFlag.name).all()


def create_flag(
    flag_name: str,
    db: Session,
    description: str = "",
    enabled: bool = False,
) -> FeatureFlag:
    """
    Create a new feature flag (defaults to disabled).

    New flags are off by default — safe to deploy before the feature is ready.
    """
    flag = FeatureFlag(
        name=flag_name,
        enabled=enabled,
        allowed_user_ids=[],
        description=description,
    )
    db.add(flag)
    db.commit()
    db.refresh(flag)
    return flag


def set_enabled(flag_name: str, enabled: bool, db: Session) -> FeatureFlag | None:
    """
    Toggle a flag on or off globally.

    Returns the updated flag, or None if the flag doesn't exist.
    This is what the admin endpoint calls.
    """
    flag = db.query(FeatureFlag).filter(FeatureFlag.name == flag_name).first()
    if flag is None:
        return None

    flag.enabled = enabled
    db.commit()
    db.refresh(flag)
    return flag


def add_allowed_user(flag_name: str, user_id: int, db: Session) -> FeatureFlag | None:
    """
    Add a user to the per-user allowlist for a disabled flag.

    Use case: flag is globally OFF but you want to test it
    with your own account in production before full rollout.
    """
    flag = db.query(FeatureFlag).filter(FeatureFlag.name == flag_name).first()
    if flag is None:
        return None

    allowed = list(flag.allowed_user_ids or [])
    if user_id not in allowed:
        allowed.append(user_id)
        flag.allowed_user_ids = allowed
        db.commit()
        db.refresh(flag)

    return flag
