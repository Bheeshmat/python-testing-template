"""
Unit tests for ai_service.py

WHAT WE TEST HERE:
    - LLM call functions (summarise_task, analyse_task) with MOCKED API calls
    - Agent tool execution (execute_agent_tool) — no LLM needed
    - Agent run loop (run_task_agent) with mocked LLM responses
    - Output validation (Pydantic parsing, invalid structure handling)

KEY PRINCIPLE:
    We NEVER call the real Anthropic API in these tests.
    We test OUR code's behaviour around the LLM, not the LLM itself.

PATTERNS DEMONSTRATED:
    - @patch decorator for mocking the Anthropic client
    - mock_llm_response / mock_tool_use_response fixtures from conftest.py
    - assert_called_once / assert_not_called for verifying LLM was called correctly
    - side_effect list for multi-call agent flows
    - Testing Pydantic output validation
    - @pytest.mark.evaluation for real API tests (run separately)
"""

import json
from unittest.mock import patch

import pytest

from src.services.ai_service import (
    analyse_task,
    execute_agent_tool,
    run_task_agent,
    summarise_task,
)

# ═════════════════════════════════════════════════════════════════════════════
# summarise_task — basic LLM call
# ═════════════════════════════════════════════════════════════════════════════


class TestSummariseTask:
    """Tests for summarise_task() — a simple LLM text generation call."""

    # IMPORTANT: patch path must be where the client is USED, not where it's imported
    # Pattern: "src.services.ai_service.client.messages.create"

    @patch("src.services.ai_service.client.messages.create")
    def test_returns_summary_and_metadata(self, mock_create, mock_llm_response):
        # Arrange — configure what the mock returns
        mock_create.return_value = mock_llm_response(
            "Fix the authentication bug in the login flow.",
            input_tokens=150,
            output_tokens=10,
        )

        # Act
        result = summarise_task(
            "Fix login bug", "Users can't log in on mobile devices."
        )

        # Assert — response parsing is correct
        assert result["summary"] == "Fix the authentication bug in the login flow."
        assert result["word_count"] == 8
        assert result["input_tokens"] == 150
        assert result["output_tokens"] == 10

    @patch("src.services.ai_service.client.messages.create")
    def test_prompt_contains_title_and_description(
        self, mock_create, mock_llm_response
    ):
        """Verifies we're sending the right data to the LLM."""
        mock_create.return_value = mock_llm_response("A summary.")

        summarise_task("My Task Title", "My task description here.")

        # Inspect what was actually sent to the API
        call_args = mock_create.call_args
        prompt_content = call_args.kwargs["messages"][0]["content"]

        assert "My Task Title" in prompt_content
        assert "My task description here." in prompt_content

    @patch("src.services.ai_service.client.messages.create")
    def test_raises_value_error_for_empty_title(self, mock_create):
        """Validates that input is checked BEFORE calling the LLM."""
        with pytest.raises(ValueError, match="required"):
            summarise_task("", "Some description.")

        # The LLM should never be called for invalid input
        mock_create.assert_not_called()

    @patch("src.services.ai_service.client.messages.create")
    def test_raises_value_error_for_empty_description(self, mock_create):
        with pytest.raises(ValueError, match="required"):
            summarise_task("Some title", "")

        mock_create.assert_not_called()

    @patch("src.services.ai_service.client.messages.create")
    def test_raises_value_error_for_whitespace_only_inputs(self, mock_create):
        with pytest.raises(ValueError, match="required"):
            summarise_task("   ", "   ")

        mock_create.assert_not_called()


# ═════════════════════════════════════════════════════════════════════════════
# analyse_task — structured output with tool_choice
# ═════════════════════════════════════════════════════════════════════════════


class TestAnalyseTask:
    """Tests for analyse_task() — structured output via tool_choice."""

    @patch("src.services.ai_service.client.messages.create")
    def test_returns_task_analysis_for_valid_response(
        self, mock_create, mock_structured_response
    ):
        # Arrange — mock a valid structured response from the LLM
        mock_create.return_value = mock_structured_response(
            {
                "summary": "Fix the login authentication issue.",
                "suggested_priority": "high",
                "estimated_hours": 3.0,
                "key_actions": [
                    "Reproduce the bug",
                    "Write a failing test",
                    "Implement fix",
                ],
            }
        )

        # Act
        result = analyse_task("Fix login bug", "Mobile login fails for all users.")

        # Assert — Pydantic model is populated correctly
        assert result.summary == "Fix the login authentication issue."
        assert result.suggested_priority == "high"
        assert result.estimated_hours == 3.0
        assert len(result.key_actions) == 3

    @patch("src.services.ai_service.client.messages.create")
    def test_raises_value_error_when_required_field_missing(
        self, mock_create, mock_structured_response
    ):
        """Pydantic validation catches incomplete LLM responses."""
        # Missing estimated_hours — Pydantic should reject this
        mock_create.return_value = mock_structured_response(
            {
                "summary": "A summary.",
                "suggested_priority": "medium",
                # estimated_hours missing
                "key_actions": ["Action 1"],
            }
        )

        with pytest.raises(ValueError, match="invalid structure"):
            analyse_task("Some task", "Some description.")

    @patch("src.services.ai_service.client.messages.create")
    def test_raises_value_error_for_empty_title(self, mock_create):
        with pytest.raises(ValueError, match="required"):
            analyse_task("", "Some description.")
        mock_create.assert_not_called()

    @patch("src.services.ai_service.client.messages.create")
    def test_uses_tool_choice_to_force_structured_output(
        self, mock_create, mock_structured_response
    ):
        """Verifies the API call includes tool_choice to force structured output."""
        mock_create.return_value = mock_structured_response(
            {
                "summary": "Summary.",
                "suggested_priority": "low",
                "estimated_hours": 1.0,
                "key_actions": ["Do thing"],
            }
        )

        analyse_task("Task", "Description.")

        call_kwargs = mock_create.call_args.kwargs
        assert "tool_choice" in call_kwargs
        assert call_kwargs["tool_choice"]["name"] == "submit_task_analysis"


# ═════════════════════════════════════════════════════════════════════════════
# execute_agent_tool — tool execution (no LLM needed)
# ═════════════════════════════════════════════════════════════════════════════


class TestExecuteAgentTool:
    """
    Tests for execute_agent_tool() — the function that runs the tools
    Claude selects. No LLM mocking needed here — this is pure logic.
    """

    def test_get_task_details_returns_json_with_task_id(self):
        result_str = execute_agent_tool("get_task_details", {"task_id": 42})
        result = json.loads(result_str)

        assert result["id"] == 42
        assert "title" in result
        assert "status" in result

    def test_get_user_tasks_returns_json_with_user_id_and_tasks(self):
        result_str = execute_agent_tool("get_user_tasks", {"user_id": 5})
        result = json.loads(result_str)

        assert result["user_id"] == 5
        assert isinstance(result["tasks"], list)

    def test_calculate_task_discount_applies_pro_discount(self):
        result_str = execute_agent_tool(
            "calculate_task_discount", {"price": 100.0, "tier": "pro"}
        )
        result = json.loads(result_str)

        assert result["discounted_price"] == 90.0

    def test_raises_value_error_for_unknown_tool(self):
        with pytest.raises(ValueError, match="Unknown tool"):
            execute_agent_tool("nonexistent_tool", {})


# ═════════════════════════════════════════════════════════════════════════════
# run_task_agent — the full agent loop
# ═════════════════════════════════════════════════════════════════════════════


class TestRunTaskAgent:
    """
    Tests for run_task_agent() — the full agent loop with tool use.

    The agent calls the LLM twice when a tool is needed:
        Call 1: User message → LLM returns tool_use
        Call 2: Tool result → LLM returns final answer

    Use mock_create.side_effect = [response1, response2] for multi-call flows.
    """

    @patch("src.services.ai_service.client.messages.create")
    def test_returns_direct_answer_when_no_tool_needed(
        self, mock_create, mock_llm_response
    ):
        """When Claude can answer without tools, only one LLM call is made."""
        mock_create.return_value = mock_llm_response("I can help you with tasks!")

        result = run_task_agent("What can you help me with?")

        assert result == "I can help you with tasks!"
        assert mock_create.call_count == 1

    @patch("src.services.ai_service.client.messages.create")
    def test_calls_tool_and_returns_final_answer(
        self, mock_create, mock_tool_use_response, mock_llm_response
    ):
        """
        When Claude requests a tool, the agent should:
        1. Execute the tool
        2. Send the result back to Claude
        3. Return Claude's final answer
        """
        # side_effect: first call returns tool_use, second returns final answer
        mock_create.side_effect = [
            mock_tool_use_response("get_task_details", {"task_id": 1}),
            mock_llm_response("Task 1 is titled 'Sample Task' with medium priority."),
        ]

        result = run_task_agent("What are the details of task 1?")

        assert result == "Task 1 is titled 'Sample Task' with medium priority."
        # LLM must be called exactly twice — once for tool selection, once for final answer
        assert mock_create.call_count == 2

    @patch("src.services.ai_service.client.messages.create")
    def test_tool_result_is_included_in_second_llm_call(
        self, mock_create, mock_tool_use_response, mock_llm_response
    ):
        """Verifies the tool result is sent back to the LLM correctly."""
        mock_create.side_effect = [
            mock_tool_use_response("get_task_details", {"task_id": 5}),
            mock_llm_response("Here are the task details."),
        ]

        run_task_agent("Tell me about task 5.")

        # Inspect the second LLM call — it should include tool_result
        second_call_messages = mock_create.call_args_list[1].kwargs["messages"]
        # Messages: [user_msg, assistant_tool_use, tool_result]
        tool_result_message = second_call_messages[2]
        assert tool_result_message["role"] == "user"
        assert tool_result_message["content"][0]["type"] == "tool_result"

    @patch("src.services.ai_service.client.messages.create")
    def test_passes_user_message_in_first_call(self, mock_create, mock_llm_response):
        """Verifies the user's message is included in the first LLM call."""
        mock_create.return_value = mock_llm_response("Sure, I can help.")

        run_task_agent("Show me all my tasks please.")

        first_call_messages = mock_create.call_args_list[0].kwargs["messages"]
        assert first_call_messages[0]["content"] == "Show me all my tasks please."


# ═════════════════════════════════════════════════════════════════════════════
# Evaluation tests — call the REAL API (run separately with: pytest -m evaluation)
# ═════════════════════════════════════════════════════════════════════════════


@pytest.mark.evaluation
class TestSummariseTaskEvaluation:
    """
    EVALUATION TESTS — These call the real Anthropic API.

    Run separately:  pytest -m evaluation
    Do NOT run in CI or on every commit (slow + costs money).

    These tests verify output quality, not just structure.
    NEVER assert exact text — LLM output varies. Assert properties instead.
    """

    def test_summary_is_non_empty_and_concise(self):
        result = summarise_task(
            "Fix mobile login bug",
            "Users on iOS devices cannot log in. The login button becomes unresponsive after entering credentials.",
        )
        assert len(result["summary"]) > 20
        assert result["word_count"] < 50  # should be concise
        assert result["word_count"] > 3  # should be meaningful

    def test_analyse_task_returns_valid_structure(self):
        result = analyse_task(
            "Implement user authentication",
            "Add JWT-based login and registration with email/password.",
        )
        assert result.suggested_priority in ["low", "medium", "high"]
        assert result.estimated_hours > 0
        assert len(result.key_actions) >= 2
        assert len(result.summary) > 10
