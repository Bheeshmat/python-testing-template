"""
conftest.py — Shared test fixtures for the entire test suite.

HOW pytest USES THIS FILE:
    pytest automatically discovers conftest.py files. Fixtures defined here
    are available to every test in the same directory and all subdirectories.
    No import needed in test files — pytest injects them by parameter name.

WHAT'S IN THIS FILE:
    1. Test database setup (SQLite in-memory)
    2. DB session fixture (isolated per test via rollback)
    3. FastAPI TestClient fixtures (plain + authenticated)
    4. Data factory fixtures (user_factory, task_factory)
    5. LLM mock fixtures (mock_llm_response, mock_tool_use_response)

HOW TO ADAPT FOR YOUR PROJECT:
    - Replace User/Task imports with your own models
    - Add factory fixtures for your own models
    - Keep the db_session / client / authenticated_client fixtures as-is
    - Add LLM response helpers that match your LLM's response structure
"""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# ── CRITICAL: Import all models before create_all() ──────────────────────────
# SQLAlchemy's Base.metadata only knows about models that have been imported.
# If a model isn't imported here, its table won't be created in the test DB.
# Add an import here for every new model file you create.
from src import models  # noqa: F401 — registers User, Task with Base.metadata
from src.auth import get_current_user, hash_password
from src.database import Base, get_db
from src.main import app
from src.models import Task, User  # noqa: F401 — available for type hints in factories

# ═════════════════════════════════════════════════════════════════════════════
# DATABASE SETUP
# ═════════════════════════════════════════════════════════════════════════════

# SQLite in-memory database — fast, isolated, wiped after the test run
# TEMPLATE NOTE: For PostgreSQL, use a dedicated test DB URL instead:
#   TEST_DATABASE_URL = "postgresql://user:password@localhost:5432/test_db"
TEST_DATABASE_URL = "sqlite:///:memory:"

test_engine = create_engine(
    TEST_DATABASE_URL,
    # Required for SQLite when used with FastAPI's thread pool
    # Remove this for PostgreSQL
    connect_args={"check_same_thread": False},
)

# Session factory bound to the test engine (not the production engine)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def create_test_tables():
    """
    Creates all database tables once before the test session starts,
    and drops them after the session ends.

    scope="session": Runs once for the ENTIRE test run (not per test).
                     Creating tables is slow — do it once, use rollbacks
                     in db_session to keep tests isolated.

    autouse=True:    Applies automatically to all tests — no need to add
                     it as a parameter to test functions.
    """
    Base.metadata.create_all(bind=test_engine)
    yield  # ← test session runs here
    Base.metadata.drop_all(bind=test_engine)


# ═════════════════════════════════════════════════════════════════════════════
# DB SESSION — Isolated per test via transaction rollback
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def db_session():
    """
    Provides a clean database session for each test.

    HOW ISOLATION WORKS:
        1. Opens a real connection to the in-memory DB
        2. Begins a transaction (like a savepoint)
        3. Yields the session to the test
        4. After the test, ROLLS BACK the transaction
        → Every test starts with an empty database

    WHY ROLLBACK INSTEAD OF TRUNCATE:
        Rollback is faster and atomic — it undoes ALL changes in one operation
        without needing to know which tables were modified.

    USAGE:
        def test_something(db_session):
            user = User(username="alice", ...)
            db_session.add(user)
            db_session.commit()
            # Changes are ONLY visible within this test — rolled back after
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    yield session  # ← test runs here

    # Teardown — always runs, even if the test fails
    session.close()
    transaction.rollback()  # ← undo ALL changes made during the test
    connection.close()


# ═════════════════════════════════════════════════════════════════════════════
# FASTAPI TEST CLIENTS
# ═════════════════════════════════════════════════════════════════════════════


@pytest.fixture
def client(db_session):
    """
    Provides a FastAPI TestClient with the test database injected.

    HOW IT WORKS:
        Overrides the get_db dependency so every route uses the test DB session
        (which rolls back after each test) instead of the real database.

    USAGE (unauthenticated routes):
        def test_create_user(client):
            response = client.post("/users", json={...})
            assert response.status_code == 201
    """

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    # Always clear overrides after the test to prevent leaking into other tests
    app.dependency_overrides.clear()


@pytest.fixture
def authenticated_client(client):
    """
    Provides a TestClient pre-configured with a fake authenticated user.

    HOW IT WORKS:
        Overrides get_current_user to return a fake user dict — skips JWT
        validation entirely. This is the right approach for testing routes
        that just need a logged-in user — no token generation overhead.

    CUSTOMISE:
        Change the returned dict to match your user structure.
        If your routes use current_user["role"] or current_user["tier"],
        add those fields here.

    USAGE:
        def test_list_tasks(authenticated_client):
            response = authenticated_client.get("/tasks")
            assert response.status_code == 200

    NOTE:
        Use create_access_token() + real headers when testing the
        auth flow itself (login, token expiry, invalid tokens).
        See tests/integration/test_auth_api.py for examples.
    """

    def override_get_current_user():
        # TEMPLATE NOTE: Return whatever shape your routes expect from current_user
        return {"user_id": 1}

    app.dependency_overrides[get_current_user] = override_get_current_user
    yield client
    app.dependency_overrides.clear()


# ═════════════════════════════════════════════════════════════════════════════
# DATA FACTORIES — Create test objects with sensible defaults
# ═════════════════════════════════════════════════════════════════════════════
#
# TWO PATTERNS:
#   make_user(**overrides)      → Creates a User object (NOT saved to DB)
#                                  Use in unit tests that just need an object
#   user_factory(**overrides)   → Creates AND saves a User to the test DB
#                                  Use in integration tests that need real records
#
# WHY UUID FOR DEFAULT VALUES:
#   Unique fields (username, email) would cause IntegrityError if multiple
#   tests use the same defaults. UUID generates a unique value each time.
#
# THE ** PATTERN:
#   make_user(tier="pro") works because:
#   1. **overrides collects {"tier": "pro"} from the caller
#   2. {**defaults, **overrides} merges dicts — overrides wins on conflict
#   3. User(**merged) unpacks the dict as keyword arguments


def make_user(**overrides) -> User:
    """
    Creates a User object with sensible defaults. Does NOT save to DB.

    Use in unit tests where you need a User object but no DB.

    Examples:
        make_user()                           # default free tier user
        make_user(tier="pro")                 # override just the tier
        make_user(email="alice@example.com")  # specific email for duplicate tests
    """
    defaults = {
        "username": f"user_{uuid.uuid4().hex[:8]}",  # unique username
        "email": f"{uuid.uuid4().hex[:8]}@example.com",  # unique email
        "hashed_password": hash_password("testpassword123"),
        "tier": "free",
        "is_active": True,
    }
    return User(**{**defaults, **overrides})


@pytest.fixture
def user_factory(db_session):
    """
    Factory fixture — creates AND persists a User to the test DB.

    Returns a factory function (not a User directly) so you can create
    multiple users with different properties in one test.

    Examples:
        def test_something(user_factory):
            alice = user_factory(tier="pro")
            bob   = user_factory(tier="enterprise")
    """

    def _create(**overrides) -> User:
        user = make_user(**overrides)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)  # loads the auto-generated id
        return user

    return _create


def make_task(user_id: int, **overrides) -> Task:
    """
    Creates a Task object with sensible defaults. Does NOT save to DB.

    Args:
        user_id:   Required — the owning user's ID.
        overrides: Optional field overrides.

    Examples:
        make_task(user_id=1)
        make_task(user_id=1, priority="high", status="in_progress")
    """
    defaults = {
        "title": f"Task {uuid.uuid4().hex[:6]}",
        "description": "Default task description.",
        "status": "todo",
        "priority": "medium",
        "user_id": user_id,
    }
    return Task(**{**defaults, **overrides})


@pytest.fixture
def task_factory(db_session):
    """
    Factory fixture — creates AND persists a Task to the test DB.

    Examples:
        def test_something(user_factory, task_factory):
            user = user_factory()
            task = task_factory(user_id=user.id, priority="high")
    """

    def _create(user_id: int, **overrides) -> Task:
        task = make_task(user_id=user_id, **overrides)
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)
        return task

    return _create


# ═════════════════════════════════════════════════════════════════════════════
# LLM MOCK HELPERS — For testing AI service functions
# ═════════════════════════════════════════════════════════════════════════════
#
# WHY MOCK LLM CALLS:
#   - Real LLM calls are slow (2-10s), expensive, and non-deterministic
#   - Mocked calls run in milliseconds and return exactly what you specify
#   - Use @patch("src.services.ai_service.client.messages.create") in tests
#
# ANTHROPIC RESPONSE STRUCTURE:
#   response.content[0].text            → the LLM's reply text
#   response.content[0].type            → "text" | "tool_use"
#   response.content[0].name            → tool name (if tool_use)
#   response.content[0].input           → tool arguments (if tool_use)
#   response.content[0].id              → tool use ID (if tool_use)
#   response.stop_reason                → "end_turn" | "tool_use" | "max_tokens"
#   response.usage.input_tokens         → tokens in the prompt
#   response.usage.output_tokens        → tokens in the response


@pytest.fixture
def mock_llm_response():
    """
    Factory fixture — builds a realistic mock Anthropic text response.

    Returns a factory function so you can customise the text per test.

    Usage:
        @patch("src.services.ai_service.client.messages.create")
        def test_something(mock_create, mock_llm_response):
            mock_create.return_value = mock_llm_response("The summary text.")
            result = summarise_task("Title", "Description")
            assert result["summary"] == "The summary text."
    """

    def _make(text: str, input_tokens: int = 100, output_tokens: int = 50):
        mock = MagicMock()
        mock.stop_reason = "end_turn"
        mock.content[0].text = text
        mock.content[0].type = "text"
        mock.usage.input_tokens = input_tokens
        mock.usage.output_tokens = output_tokens
        return mock

    return _make


@pytest.fixture
def mock_tool_use_response():
    """
    Factory fixture — builds a mock Anthropic response where the model
    requests a tool call (stop_reason="tool_use").

    Usage:
        @patch("src.services.ai_service.client.messages.create")
        def test_agent(mock_create, mock_tool_use_response, mock_llm_response):
            mock_create.side_effect = [
                mock_tool_use_response("get_task_details", {"task_id": 1}),
                mock_llm_response("The task is high priority."),
            ]
            result = run_task_agent("What are the details of task 1?")
            assert mock_create.call_count == 2
    """

    def _make(tool_name: str, tool_input: dict, tool_id: str = "toolu_test123"):
        mock = MagicMock()
        mock.stop_reason = "tool_use"
        mock.content[0].type = "tool_use"
        mock.content[0].name = tool_name
        mock.content[0].input = tool_input
        mock.content[0].id = tool_id
        return mock

    return _make


@pytest.fixture
def mock_structured_response():
    """
    Factory fixture — builds a mock response where the model used tool_choice
    to return structured data (as in analyse_task).

    The content[0].input dict is what gets passed to Pydantic for validation.

    Usage:
        @patch("src.services.ai_service.client.messages.create")
        def test_analyse(mock_create, mock_structured_response):
            mock_create.return_value = mock_structured_response({
                "summary": "Fix the login bug.",
                "suggested_priority": "high",
                "estimated_hours": 2.0,
                "key_actions": ["Reproduce bug", "Write failing test", "Fix code"],
            })
            result = analyse_task("Fix bug", "Login fails on mobile")
            assert result.suggested_priority == "high"
    """

    def _make(tool_input: dict):
        mock = MagicMock()
        mock.stop_reason = "tool_use"
        mock.content[0].type = "tool_use"
        mock.content[0].input = tool_input
        return mock

    return _make
