"""
Integration tests for AI API routes.

WHAT WE TEST HERE:
    - /ai/summarise endpoint: request validation, LLM call, response shape
    - /ai/agent endpoint: message routing, response shape
    - Auth protection on all AI routes
    - Error handling when LLM returns bad data

KEY PRINCIPLE:
    Even in integration tests, we MOCK the LLM calls.
    We're testing the HTTP layer + our code's logic — not the LLM.

PATTERNS DEMONSTRATED:
    - @patch at the integration test level (route → service → LLM)
    - Combining authenticated_client with mocked LLM calls
    - Testing that routes return the right HTTP status for LLM errors
"""

from unittest.mock import patch

# ═════════════════════════════════════════════════════════════════════════════
# POST /ai/summarise
# ═════════════════════════════════════════════════════════════════════════════


class TestSummariseEndpoint:
    def test_returns_401_when_not_authenticated(self, client):
        response = client.post(
            "/ai/summarise",
            json={
                "title": "Task title",
                "description": "Task description",
            },
        )
        assert response.status_code == 401

    @patch("src.services.ai_service.client.messages.create")
    def test_returns_summary_for_valid_request(
        self, mock_create, authenticated_client, mock_llm_response
    ):
        mock_create.return_value = mock_llm_response("A concise task summary.")

        response = authenticated_client.post(
            "/ai/summarise",
            json={
                "title": "Fix login bug",
                "description": "Users cannot log in on mobile devices.",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["summary"] == "A concise task summary."
        assert data["word_count"] == 4
        assert "input_tokens" in data
        assert "output_tokens" in data

    @patch("src.services.ai_service.client.messages.create")
    def test_returns_422_for_empty_title(self, mock_create, authenticated_client):
        """Empty title is caught by the service layer before calling the LLM."""
        response = authenticated_client.post(
            "/ai/summarise",
            json={
                "title": "",
                "description": "Some description.",
            },
        )

        assert response.status_code == 422
        assert "required" in response.json()["detail"].lower()
        mock_create.assert_not_called()

    def test_returns_422_when_required_fields_missing(self, authenticated_client):
        """FastAPI Pydantic validation catches missing fields."""
        response = authenticated_client.post(
            "/ai/summarise",
            json={
                "title": "Only title, no description",
                # description missing
            },
        )
        # Pydantic will return 422 for missing required field
        assert response.status_code == 422


# ═════════════════════════════════════════════════════════════════════════════
# POST /ai/agent
# ═════════════════════════════════════════════════════════════════════════════


class TestAgentEndpoint:
    def test_returns_401_when_not_authenticated(self, client):
        response = client.post("/ai/agent", json={"message": "Hello"})
        assert response.status_code == 401

    @patch("src.services.ai_service.client.messages.create")
    def test_returns_agent_response_for_valid_message(
        self, mock_create, authenticated_client, mock_llm_response
    ):
        mock_create.return_value = mock_llm_response(
            "I can help you manage your tasks!"
        )

        response = authenticated_client.post(
            "/ai/agent", json={"message": "What can you help me with?"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["response"] == "I can help you manage your tasks!"
        assert "user_id" in data

    @patch("src.services.ai_service.client.messages.create")
    def test_agent_handles_tool_use_flow(
        self,
        mock_create,
        authenticated_client,
        mock_tool_use_response,
        mock_llm_response,
    ):
        """
        Verifies the full tool use flow works end-to-end:
        1. Route receives message
        2. Agent calls LLM (returns tool_use)
        3. Agent executes tool
        4. Agent sends result back to LLM
        5. LLM returns final answer
        6. Route returns final answer to client
        """
        mock_create.side_effect = [
            mock_tool_use_response("get_task_details", {"task_id": 1}),
            mock_llm_response("Task 1 has medium priority."),
        ]

        response = authenticated_client.post(
            "/ai/agent", json={"message": "What are the details of task 1?"}
        )

        assert response.status_code == 200
        assert response.json()["response"] == "Task 1 has medium priority."
        assert mock_create.call_count == 2

    def test_returns_422_when_message_field_missing(self, authenticated_client):
        response = authenticated_client.post("/ai/agent", json={})
        assert response.status_code == 422
