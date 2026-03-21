"""
FastAPI application — routes and request/response schemas. Copy In your FastAPI Project and modify as needed.

TEMPLATE NOTE:
- Routes are thin — they validate input and delegate to services.
- Business logic lives in services/, not here.
- Always define specific routes (e.g. /users/me) BEFORE dynamic routes (/users/{id}).
- Pydantic BaseModel subclasses define request/response shapes for each endpoint.
"""

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.auth import create_access_token, get_current_user
from src.database import Base, engine, get_db
from src.models import TaskPriorityEnum, TierEnum
from src.services import ai_service, flag_service, user_service

# ── App Initialisation ────────────────────────────────────────────────────────
app = FastAPI(
    title="Task Manager API",
    description="Reference app for Python testing template",
    version="1.0.0",
)

# Create tables on startup (for development only — use Alembic migrations in production)
Base.metadata.create_all(bind=engine)


# ── Request / Response Schemas ────────────────────────────────────────────────
class UserCreateRequest(BaseModel):
    username: str
    email: str
    password: str
    tier: str = TierEnum.FREE


class UserResponse(BaseModel):
    id: int
    username: str
    email: str
    tier: str
    is_active: bool


class TaskCreateRequest(BaseModel):
    title: str
    description: str = ""
    priority: str = TaskPriorityEnum.MEDIUM


class TaskResponse(BaseModel):
    id: int
    title: str
    description: str | None
    status: str
    priority: str
    user_id: int


class TaskStatusUpdateRequest(BaseModel):
    status: str


class SummariseRequest(BaseModel):
    title: str
    description: str


class AgentRequest(BaseModel):
    message: str


class FlagResponse(BaseModel):
    id: int
    name: str
    enabled: bool
    allowed_user_ids: list[int]
    description: str | None


class FlagCreateRequest(BaseModel):
    name: str
    description: str = ""
    enabled: bool = False


class FlagToggleRequest(BaseModel):
    enabled: bool


# ── Health Check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["System"])
def health_check():
    """Returns API health status. No auth required."""
    return {"status": "ok", "version": "1.0.0"}


# ── Auth Routes ───────────────────────────────────────────────────────────────
@app.post("/auth/login", tags=["Auth"])
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Authenticates a user and returns a JWT access token.
    Uses OAuth2 password flow (form data, not JSON).
    """
    user = user_service.authenticate_user(form_data.username, form_data.password, db)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    token = create_access_token({"sub": str(user.id)})
    return {"access_token": token, "token_type": "bearer"}


# ── User Routes ───────────────────────────────────────────────────────────────
# IMPORTANT: /users/me must be defined BEFORE /users/{user_id}
# FastAPI matches routes top-to-bottom — "me" would otherwise be treated as an int


@app.get("/users/me", response_model=UserResponse, tags=["Users"])
def get_me(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns the profile of the currently authenticated user."""
    user = user_service.get_user_by_id(current_user["user_id"], db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@app.post("/users", response_model=UserResponse, status_code=201, tags=["Users"])
def create_user(payload: UserCreateRequest, db: Session = Depends(get_db)):
    """Creates a new user account. No auth required (public registration)."""
    try:
        user = user_service.create_user(
            username=payload.username,
            email=payload.email,
            password=payload.password,
            db=db,
        )
        return user
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/users/{user_id}", response_model=UserResponse, tags=["Users"])
def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Returns a user by ID. Requires authentication."""
    user = user_service.get_user_by_id(user_id, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


# ── Task Routes ───────────────────────────────────────────────────────────────
@app.get("/tasks", response_model=list[TaskResponse], tags=["Tasks"])
def list_tasks(
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Returns all tasks for the authenticated user."""
    return user_service.get_tasks_for_user(current_user["user_id"], db)


@app.post("/tasks", response_model=TaskResponse, status_code=201, tags=["Tasks"])
def create_task(
    payload: TaskCreateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Creates a new task for the authenticated user."""
    task = user_service.create_task(
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        user_id=current_user["user_id"],
        db=db,
    )
    return task


@app.patch("/tasks/{task_id}/status", response_model=TaskResponse, tags=["Tasks"])
def update_task_status(
    task_id: int,
    payload: TaskStatusUpdateRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Updates a task's status. Validates that the transition is allowed."""
    try:
        task = user_service.update_task_status(
            task_id=task_id,
            new_status=payload.status,
            user_id=current_user["user_id"],
            db=db,
        )
        return task
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


# ── AI Routes ─────────────────────────────────────────────────────────────────
@app.post("/ai/summarise", tags=["AI"])
def summarise_task(
    payload: SummariseRequest,
    current_user: dict = Depends(get_current_user),
):
    """Generates a summary of a task using Claude. Requires authentication."""
    try:
        result = ai_service.summarise_task(payload.title, payload.description)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@app.post("/ai/agent", tags=["AI"])
def run_agent(
    payload: AgentRequest,
    current_user: dict = Depends(get_current_user),
):
    """Runs the task management agent. Requires authentication."""
    result = ai_service.run_task_agent(payload.message)
    return {"response": result, "user_id": current_user["user_id"]}


# ── Feature Flag Routes (Admin) ───────────────────────────────────────────────
# In production, protect these with an admin role check.
# For this template, authentication is sufficient.


@app.get("/admin/flags", response_model=list[FlagResponse], tags=["Feature Flags"])
def list_flags(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all feature flags. Requires authentication."""
    return flag_service.get_all_flags(db)


@app.post(
    "/admin/flags", response_model=FlagResponse, status_code=201, tags=["Feature Flags"]
)
def create_flag(
    payload: FlagCreateRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Create a new feature flag. Defaults to disabled."""
    return flag_service.create_flag(
        flag_name=payload.name,
        description=payload.description,
        enabled=payload.enabled,
        db=db,
    )


@app.patch(
    "/admin/flags/{flag_name}", response_model=FlagResponse, tags=["Feature Flags"]
)
def toggle_flag(
    flag_name: str,
    payload: FlagToggleRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Toggle a feature flag on or off globally.
    No redeployment needed — takes effect immediately.
    """
    flag = flag_service.set_enabled(flag_name, payload.enabled, db)
    if not flag:
        raise HTTPException(status_code=404, detail=f"Flag '{flag_name}' not found.")
    return flag


# ── Feature Flag Usage Example ────────────────────────────────────────────────
# This route demonstrates how to guard a feature behind a flag.
# The /ai/summarise route above is always accessible.
# This variant is only accessible when the "ai_summary_v2" flag is ON.


@app.post("/ai/summarise/v2", tags=["AI"])
def summarise_task_v2(
    payload: SummariseRequest,
    current_user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    AI summary v2 — only accessible when 'ai_summary_v2' flag is enabled.
    Demonstrates feature flag usage: deploy the code, control visibility via flag.
    """
    if not flag_service.is_enabled(
        "ai_summary_v2",
        user_id=current_user["user_id"],
        db=db,
    ):
        raise HTTPException(
            status_code=404,
            detail="Not found.",  # intentionally vague — don't reveal hidden features
        )
    try:
        result = ai_service.summarise_task(payload.title, payload.description)
        return {**result, "version": "v2"}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
