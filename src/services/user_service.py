"""
User and Task business logic.

TEMPLATE NOTE:
- Services contain pure business logic — no HTTP concepts (no Request/Response).
- Services are the primary target of unit tests (fast, no DB, no HTTP).
- Functions that need the DB accept a `db: Session` parameter.
- Functions that don't need the DB (pure logic) are the easiest to unit test.
"""

from sqlalchemy.orm import Session

from src.auth import hash_password, verify_password
from src.models import Task, TaskPriorityEnum, TaskStatusEnum, TierEnum, User

# ── Pure Logic (no DB) — Easiest to unit test ─────────────────────────────────


def calculate_discount(price: float, tier: str) -> float:
    """
    Returns the discounted price based on the user's subscription tier.

    Args:
        price:  The original price.
        tier:   The user's tier (free, pro, enterprise).

    Returns:
        The price after applying the tier discount.

    Raises:
        ValueError: If the tier is not recognised.

    TESTING NOTE:
        Pure function — no mocking needed. Test with AAA pattern directly.
    """
    discounts = {
        TierEnum.FREE: 0.0,
        TierEnum.PRO: 0.10,
        TierEnum.ENTERPRISE: 0.25,
    }
    if tier not in discounts:
        raise ValueError(f"Unknown tier: {tier}. Valid tiers: {list(discounts.keys())}")
    return round(price * (1 - discounts[tier]), 2)


def validate_task_status_transition(current_status: str, new_status: str) -> bool:
    """
    Validates that a task status transition is allowed.

    Allowed transitions:
        todo → in_progress
        in_progress → done
        in_progress → todo (undo)
        done → in_progress (reopen)

    Args:
        current_status: The task's current status.
        new_status:     The desired new status.

    Returns:
        True if the transition is valid.

    Raises:
        ValueError: If the transition is not allowed.

    TESTING NOTE:
        Pure function — great candidate for @pytest.mark.parametrize.
    """
    allowed_transitions = {
        TaskStatusEnum.TODO: [TaskStatusEnum.IN_PROGRESS],
        TaskStatusEnum.IN_PROGRESS: [TaskStatusEnum.DONE, TaskStatusEnum.TODO],
        TaskStatusEnum.DONE: [TaskStatusEnum.IN_PROGRESS],
    }
    if new_status not in allowed_transitions.get(current_status, []):
        raise ValueError(
            f"Cannot transition task from '{current_status}' to '{new_status}'."
        )
    return True


# ── DB-dependent Logic — Requires mocking or real DB in tests ─────────────────


def get_user_by_email(email: str, db: Session) -> User | None:
    """Returns a User matching the email, or None if not found."""
    return db.query(User).filter(User.email == email).first()


def get_user_by_id(user_id: int, db: Session) -> User | None:
    """Returns a User matching the id, or None if not found."""
    return db.query(User).filter(User.id == user_id).first()


def create_user(username: str, email: str, password: str, db: Session) -> User:
    """
    Creates and persists a new user.

    Args:
        username: The desired username.
        email:    The user's email address.
        password: Plain text password — will be hashed before storage.
        db:       The database session.

    Returns:
        The newly created User object.

    Raises:
        ValueError: If the email is already registered.

    TESTING NOTE:
        Requires a db session. Use the db_session fixture or user_factory
        from conftest.py for integration tests.
    """
    if get_user_by_email(email, db):
        raise ValueError(f"Email already registered: {email}")
    user = User(
        username=username,
        email=email,
        hashed_password=hash_password(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_user(email: str, password: str, db: Session) -> User | None:
    """
    Verifies credentials and returns the User if valid, None otherwise.

    TESTING NOTE:
        In integration tests, create a user first with user_factory, then
        call this with the known password to get a token.
    """
    user = get_user_by_email(email, db)
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


def get_tasks_for_user(user_id: int, db: Session) -> list[Task]:
    """Returns all tasks belonging to the given user."""
    return db.query(Task).filter(Task.user_id == user_id).all()


def create_task(
    title: str,
    user_id: int,
    db: Session,
    description: str = "",
    priority: str = TaskPriorityEnum.MEDIUM,
) -> Task:
    """
    Creates and persists a new task for the given user.

    Args:
        title:       The task title (required).
        user_id:     The owning user's ID.
        db:          The database session.
        description: Optional task description.
        priority:    Task priority (low, medium, high).

    Returns:
        The newly created Task object.
    """
    task = Task(
        title=title,
        description=description,
        priority=priority,
        user_id=user_id,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def update_task_status(
    task_id: int, new_status: str, user_id: int, db: Session
) -> Task:
    """
    Updates a task's status after validating the transition is allowed.

    Args:
        task_id:    The task to update.
        new_status: The desired new status.
        user_id:    The requesting user's ID (for ownership check).
        db:         The database session.

    Returns:
        The updated Task object.

    Raises:
        ValueError: If task not found, user doesn't own it, or transition invalid.
    """
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise ValueError(f"Task {task_id} not found or not owned by user {user_id}.")
    validate_task_status_transition(task.status, new_status)
    task.status = new_status
    db.commit()
    db.refresh(task)
    return task
