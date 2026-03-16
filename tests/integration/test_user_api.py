"""
Integration tests for user and task API routes.

WHAT WE TEST HERE:
    - HTTP endpoints (status codes + response bodies)
    - Database persistence (records actually saved)
    - Business rules enforced at the API level
    - Auth protection (routes return 401 without a token)

FIXTURES USED (from conftest.py):
    client               → TestClient with test DB, no auth
    authenticated_client → TestClient with fake logged-in user (user_id=1)
    user_factory         → creates real DB users for test data
    task_factory         → creates real DB tasks for test data
    db_session           → direct DB access for setup/verification

PATTERNS DEMONSTRATED:
    - Always assert status code first, then body
    - Create test data with factories, not hardcoded values
    - Test that data actually persists (check id is not None)
    - Test ownership rules (users can only access their own data)
"""


# ═════════════════════════════════════════════════════════════════════════════
# Health Check
# ═════════════════════════════════════════════════════════════════════════════


class TestHealthCheck:
    def test_returns_200_with_status_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


# ═════════════════════════════════════════════════════════════════════════════
# POST /users — create a new user
# ═════════════════════════════════════════════════════════════════════════════


class TestCreateUser:
    def test_returns_201_and_user_data_for_valid_payload(self, client):
        payload = {
            "username": "alice",
            "email": "alice@example.com",
            "password": "securepassword123",
        }

        response = client.post("/users", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["username"] == "alice"
        assert data["email"] == "alice@example.com"
        assert data["tier"] == "free"  # default tier
        assert data["is_active"] is True
        assert data["id"] is not None  # DB assigned a real ID
        assert "password" not in data  # password is never returned
        assert "hashed_password" not in data

    def test_returns_409_for_duplicate_email(self, client, user_factory):
        # Create a user with a known email first
        user_factory(email="taken@example.com")

        # Try to register with the same email
        response = client.post(
            "/users",
            json={
                "username": "newuser",
                "email": "taken@example.com",
                "password": "password123",
            },
        )

        assert response.status_code == 409
        assert "already registered" in response.json()["detail"].lower()

    def test_returns_422_when_required_field_missing(self, client):
        # Missing password
        response = client.post(
            "/users",
            json={
                "username": "alice",
                "email": "alice@example.com",
            },
        )
        # FastAPI automatically returns 422 for missing required Pydantic fields
        assert response.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# GET /users/me — get current user's profile
# ═════════════════════════════════════════════════════════════════════════════


class TestGetMe:
    def test_returns_401_when_not_authenticated(self, client):
        """No auth token provided — must return 401."""
        response = client.get("/users/me")
        assert response.status_code == 401

    def test_returns_current_user_profile_when_authenticated(
        self, authenticated_client, user_factory, db_session
    ):
        """
        authenticated_client injects user_id=1 (from conftest.py override).
        We must create a user with that ID in the test DB.
        """
        # Create a user — the factory assigns an auto-incremented ID
        user = user_factory(username="testuser", email="test@example.com")

        # Update the auth override to return this user's actual ID
        from src.auth import get_current_user
        from src.main import app

        app.dependency_overrides[get_current_user] = lambda: {"user_id": user.id}

        response = authenticated_client.get("/users/me")

        assert response.status_code == 200
        assert response.json()["username"] == "testuser"
        assert response.json()["email"] == "test@example.com"


# ═════════════════════════════════════════════════════════════════════════════
# GET /users/{user_id} — get user by ID
# ═════════════════════════════════════════════════════════════════════════════


class TestGetUser:
    def test_returns_401_when_not_authenticated(self, client):
        response = client.get("/users/1")
        assert response.status_code == 401

    def test_returns_user_for_valid_id(self, authenticated_client, user_factory):
        user = user_factory(username="bob", email="bob@example.com", tier="pro")

        response = authenticated_client.get(f"/users/{user.id}")

        assert response.status_code == 200
        assert response.json()["username"] == "bob"
        assert response.json()["tier"] == "pro"

    def test_returns_404_for_nonexistent_user(self, authenticated_client):
        response = authenticated_client.get("/users/99999")
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()


# ═════════════════════════════════════════════════════════════════════════════
# POST /tasks — create a new task
# ═════════════════════════════════════════════════════════════════════════════


class TestCreateTask:
    def test_returns_401_when_not_authenticated(self, client):
        response = client.post("/tasks", json={"title": "My Task"})
        assert response.status_code == 401

    def test_returns_201_and_task_data_for_valid_payload(self, authenticated_client):
        payload = {
            "title": "Write unit tests",
            "description": "Add tests for the user service",
            "priority": "high",
        }

        response = authenticated_client.post("/tasks", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "Write unit tests"
        assert data["priority"] == "high"
        assert data["status"] == "todo"  # default status
        assert data["id"] is not None

    def test_defaults_to_medium_priority_when_not_specified(self, authenticated_client):
        response = authenticated_client.post("/tasks", json={"title": "Quick task"})

        assert response.status_code == 201
        assert response.json()["priority"] == "medium"

    def test_returns_422_when_title_missing(self, authenticated_client):
        response = authenticated_client.post("/tasks", json={"description": "No title"})
        assert response.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# GET /tasks — list tasks for current user
# ═════════════════════════════════════════════════════════════════════════════


class TestListTasks:
    def test_returns_401_when_not_authenticated(self, client):
        response = client.get("/tasks")
        assert response.status_code == 401

    def test_returns_empty_list_when_user_has_no_tasks(self, authenticated_client):
        response = authenticated_client.get("/tasks")

        assert response.status_code == 200
        assert response.json() == []

    def test_returns_only_current_users_tasks(
        self, authenticated_client, user_factory, task_factory
    ):
        """Users should only see their own tasks — not other users' tasks."""
        from src.auth import get_current_user
        from src.main import app

        # Create current user first — they claim id=1 (first insert)
        current_user = user_factory()
        app.dependency_overrides[get_current_user] = lambda: {"user_id": current_user.id}

        # Create a different user and give them tasks — they get id=2
        other_user = user_factory()
        task_factory(user_id=other_user.id, title="Other user's task")

        response = authenticated_client.get("/tasks")

        # current_user has no tasks — should get empty list
        assert response.status_code == 200
        assert response.json() == []


# ═════════════════════════════════════════════════════════════════════════════
# PATCH /tasks/{task_id}/status — update task status
# ═════════════════════════════════════════════════════════════════════════════


class TestUpdateTaskStatus:
    def test_returns_200_for_valid_status_transition(
        self, authenticated_client, task_factory
    ):
        """todo → in_progress is a valid transition."""
        task = task_factory(user_id=1, status="todo")

        response = authenticated_client.patch(
            f"/tasks/{task.id}/status",
            json={"status": "in_progress"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "in_progress"

    def test_returns_422_for_invalid_status_transition(
        self, authenticated_client, task_factory
    ):
        """todo → done is not allowed (must go through in_progress)."""
        task = task_factory(user_id=1, status="todo")

        response = authenticated_client.patch(
            f"/tasks/{task.id}/status",
            json={"status": "done"},
        )

        assert response.status_code == 422
        assert "Cannot transition" in response.json()["detail"]

    def test_returns_422_when_task_not_found(self, authenticated_client):
        response = authenticated_client.patch(
            "/tasks/99999/status",
            json={"status": "in_progress"},
        )
        assert response.status_code == 422
