# Python Testing Template

A drop-in testing template for Python/FastAPI/GenAI projects.
Covers: Unit tests · Integration tests · AI/LLM mocking · JWT auth testing · DB isolation

---

## What's Included

```
python-testing-template/
├── src/                            ← Reference app (use or discard)
│   ├── main.py                     ← FastAPI routes
│   ├── database.py                 ← SQLAlchemy + get_db dependency
│   ├── models.py                   ← User + Task SQLAlchemy models
│   ├── auth.py                     ← JWT auth utilities
│   └── services/
│       ├── user_service.py         ← CRUD business logic
│       └── ai_service.py          ← Anthropic SDK + agent
│
├── tests/                          ← THE TEMPLATE (drop this into any project)
│   ├── conftest.py                 ← All shared fixtures
│   ├── unit/
│   │   ├── test_user_service.py    ← Unit tests (no DB, no LLM)
│   │   └── test_ai_service.py      ← LLM mocking + agent testing
│   └── integration/
│       ├── test_user_api.py        ← CRUD API tests
│       ├── test_auth_api.py        ← JWT auth tests
│       └── test_ai_api.py          ← AI endpoint tests
│
├── pytest.ini                      ← pytest config + markers
├── pyproject.toml                  ← Ruff linter config
├── requirements.txt                ← All dependencies
├── .env.example                    ← Environment variable template
└── .gitignore
```

---

## Quick Start

```bash
# 1. Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set up environment variables
cp .env.example .env
# Edit .env — add your ANTHROPIC_API_KEY and SECRET_KEY

# 4. Run all tests
pytest

# 5. Run with verbose output
pytest -v

# 6. Run only unit tests (fast, no DB)
pytest -m unit

# 7. Run only integration tests
pytest -m integration

# 8. Run evaluation tests (calls real LLM — costs money)
pytest -m evaluation
```

---

## Dropping the `tests/` Folder Into Your Project

### Step 1 — Copy the folder
```bash
cp -r python-testing-template/tests/ your-project/tests/
cp python-testing-template/pytest.ini your-project/pytest.ini
```

### Step 2 — Update imports in `conftest.py`
```python
# Replace these imports with your own app's structure
from src.auth import get_current_user    # → your auth module
from src.database import Base, get_db   # → your database module
from src.main import app                 # → your FastAPI app
from src import models                   # → your models package
from src.models import User, Task        # → your model classes
```

### Step 3 — Update factories
Replace `make_user()` and `make_task()` with factories for your own models:
```python
def make_[your_model](**overrides) -> YourModel:
    defaults = {
        "field1": "default_value",
        "unique_field": f"{uuid.uuid4().hex[:8]}",  # unique to avoid collisions
    }
    return YourModel(**{**defaults, **overrides})
```

### Step 4 — Update the auth override in `authenticated_client`
```python
def override_get_current_user():
    # Return whatever shape YOUR routes expect from current_user
    return {"user_id": 1, "tier": "pro"}  # add fields your routes use
```

### Step 5 — Update the LLM mock patch path
```python
# Replace with your project's module path to the Anthropic client
@patch("your_app.services.ai_service.client.messages.create")
```

---

## Key Concepts

### Fixtures (conftest.py)

| Fixture | What it provides | When to use |
|---|---|---|
| `db_session` | Clean DB session, rolls back after each test | When you need direct DB access |
| `client` | TestClient + test DB injected | Unauthenticated route tests |
| `authenticated_client` | TestClient + fake logged-in user | Protected route tests |
| `user_factory` | Creates + persists users to test DB | When routes need real DB records |
| `task_factory` | Creates + persists tasks to test DB | When routes need task records |
| `mock_llm_response` | Factory for mock Anthropic text responses | Testing LLM service functions |
| `mock_tool_use_response` | Factory for mock tool_use responses | Testing agent tool selection |
| `mock_structured_response` | Factory for mock tool_choice responses | Testing structured output parsing |

### Test Markers

| Marker | Command | When to run |
|---|---|---|
| `unit` | `pytest -m unit` | Constantly during development |
| `integration` | `pytest -m integration` | Before committing |
| `evaluation` | `pytest -m evaluation` | Before releases (costs money) |

### Mocking LLM Calls

Always mock — never call the real API in unit/integration tests:

```python
@patch("src.services.ai_service.client.messages.create")
def test_something(mock_create, mock_llm_response):
    mock_create.return_value = mock_llm_response("The response text.")

    result = your_function()

    mock_create.assert_called_once()  # verify LLM was called
```

### DB Isolation

Every test gets a clean database via transaction rollback:
```
Test starts  → empty DB
Test runs    → adds data
Test ends    → rollback → empty DB again
Next test    → starts fresh
```

---

## Running the Reference App

```bash
uvicorn src.main:app --reload
# API docs: http://localhost:8000/docs
```

---

## What to Delete When Adapting

- `src/` — replace with your own application code
- `tests/unit/test_user_service.py` — replace with tests for your services
- `tests/integration/test_user_api.py` — replace with tests for your routes
- Keep: `tests/conftest.py` (update imports), `pytest.ini`, `pyproject.toml`
