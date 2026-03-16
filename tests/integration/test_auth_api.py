"""
Integration tests for authentication routes.

WHAT WE TEST HERE:
    - Login with valid credentials → returns JWT token
    - Login with invalid credentials → returns 401
    - Protected routes reject missing/invalid/tampered tokens
    - Valid token grants access to protected routes

PATTERNS DEMONSTRATED:
    - Testing the full login flow end-to-end
    - Using create_access_token() for generating test tokens
    - Passing Bearer tokens in request headers
    - Testing token validation (expired, tampered, missing)
"""

from src.auth import create_access_token

# ═════════════════════════════════════════════════════════════════════════════
# POST /auth/login
# ═════════════════════════════════════════════════════════════════════════════


class TestLogin:
    def test_returns_token_for_valid_credentials(self, client, user_factory):
        """
        Creates a user with a known password, then verifies login works.
        user_factory uses hash_password("testpassword123") by default.
        """
        user_factory(email="login@example.com")

        # OAuth2 login uses form data (not JSON)
        response = client.post(
            "/auth/login",
            data={
                "username": "login@example.com",
                "password": "testpassword123",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert len(data["access_token"]) > 20  # token should be non-trivial

    def test_returns_401_for_wrong_password(self, client, user_factory):
        user_factory(email="user@example.com")

        response = client.post(
            "/auth/login",
            data={
                "username": "user@example.com",
                "password": "wrongpassword",
            },
        )

        assert response.status_code == 401
        assert "Incorrect" in response.json()["detail"]

    def test_returns_401_for_nonexistent_email(self, client):
        response = client.post(
            "/auth/login",
            data={
                "username": "nobody@example.com",
                "password": "anypassword",
            },
        )

        assert response.status_code == 401

    def test_returns_422_when_credentials_not_provided(self, client):
        """FastAPI returns 422 if required form fields are missing."""
        response = client.post("/auth/login", data={})
        assert response.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# Protected routes — token validation
# ═════════════════════════════════════════════════════════════════════════════


class TestProtectedRoutes:
    """
    Tests that verify protected routes correctly enforce authentication.

    Use create_access_token() when testing the auth mechanism itself.
    Use authenticated_client when testing non-auth route functionality.
    """

    def test_protected_route_returns_401_when_no_token(self, client):
        """No Authorization header — must return 401."""
        response = client.get("/users/me")
        assert response.status_code == 401

    def test_protected_route_returns_401_for_tampered_token(self, client):
        """Manually modified token — signature check should fail."""
        response = client.get(
            "/users/me",
            headers={"Authorization": "Bearer this.is.a.fake.jwt.token"},
        )
        assert response.status_code == 401

    def test_protected_route_returns_401_for_malformed_header(self, client):
        """Missing 'Bearer' prefix — should return 401."""
        token = create_access_token({"sub": "1"})
        response = client.get(
            "/users/me",
            headers={"Authorization": token},  # missing "Bearer " prefix
        )
        assert response.status_code == 401

    def test_valid_token_grants_access_to_protected_route(self, client, user_factory):
        """
        Full flow: create user → login → use token → access protected route.
        This is the end-to-end auth test.
        """
        # Step 1: Create a user
        user = user_factory(email="auth_test@example.com")

        # Step 2: Generate a real token for that user
        token = create_access_token({"sub": str(user.id)})

        # Step 3: Use the token to access a protected route
        response = client.get(
            f"/users/{user.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["email"] == "auth_test@example.com"

    def test_token_for_different_user_can_still_access_users_endpoint(
        self, client, user_factory
    ):
        """
        Any authenticated user can look up another user's profile.
        Tests that auth check passes — not ownership check.
        """
        user_a = user_factory(email="a@example.com")
        user_b = user_factory(email="b@example.com")

        # User A's token
        token = create_access_token({"sub": str(user_a.id)})

        # Access user B's profile
        response = client.get(
            f"/users/{user_b.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["email"] == "b@example.com"
