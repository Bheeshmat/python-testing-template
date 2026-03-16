"""
AI service — LLM calls and agent logic using the Anthropic SDK.

TEMPLATE NOTE:
- Never call the real API in unit or integration tests — always mock.
- Use @patch("src.services.ai_service.client.messages.create") to mock calls.
- Use the mock_llm_response fixture from conftest.py for realistic mocks.
- The TOOLS list defines what the agent can do — expand for your project.
- evaluation tests (pytest -m evaluation) are the only tests that call the real API.
"""

import json

import anthropic
from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

load_dotenv()

# ── Client ────────────────────────────────────────────────────────────────────
# Reads ANTHROPIC_API_KEY from environment automatically
# TESTING NOTE: patch "src.services.ai_service.client.messages.create"
client = anthropic.Anthropic()

MODEL = "claude-sonnet-4-6"  # update to latest model as needed


# ── Pydantic Schemas for Structured Output ────────────────────────────────────
class TaskAnalysis(BaseModel):
    """Schema for the structured output from analyse_task()."""

    summary: str
    suggested_priority: str  # low | medium | high
    estimated_hours: float
    key_actions: list[str]


# ── Simple LLM Calls ─────────────────────────────────────────────────────────


def summarise_task(title: str, description: str) -> dict:
    """
    Generates a concise summary of a task using Claude.

    Args:
        title:       The task title.
        description: The task description.

    Returns:
        dict with keys: summary (str), word_count (int),
        input_tokens (int), output_tokens (int)

    Raises:
        ValueError: If title or description is empty.

    TESTING NOTE:
        Mock client.messages.create and verify:
        1. The right prompt was sent (check call_args)
        2. The response is parsed correctly
        3. Empty input raises before calling the API (assert_not_called)
    """
    if not title.strip() or not description.strip():
        raise ValueError("Task title and description are required for summarisation.")

    response = client.messages.create(
        model=MODEL,
        max_tokens=200,
        messages=[
            {
                "role": "user",
                "content": (
                    f"Summarise this task in 1-2 sentences:\n\n"
                    f"Title: {title}\n"
                    f"Description: {description}"
                ),
            }
        ],
    )

    summary = response.content[0].text.strip()
    return {
        "summary": summary,
        "word_count": len(summary.split()),
        "input_tokens": response.usage.input_tokens,
        "output_tokens": response.usage.output_tokens,
    }


def analyse_task(title: str, description: str) -> TaskAnalysis:
    """
    Returns a structured analysis of a task using Pydantic validation.

    Uses tool_choice to force Claude to return structured data — the most
    reliable approach for structured output (no JSON parsing needed).

    Args:
        title:       The task title.
        description: The task description.

    Returns:
        TaskAnalysis Pydantic model with summary, priority, hours, actions.

    Raises:
        ValueError: If the LLM returns an invalid structure (Pydantic validation).

    TESTING NOTE:
        Mock the response's content[0].input dict to match TaskAnalysis fields.
        Test that ValidationError is raised for malformed responses.
    """
    if not title.strip():
        raise ValueError("Task title is required.")

    response = client.messages.create(
        model=MODEL,
        max_tokens=500,
        tools=[
            {
                "name": "submit_task_analysis",
                "description": "Submit the structured analysis of a task.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "summary": {
                            "type": "string",
                            "description": "1-2 sentence summary of the task.",
                        },
                        "suggested_priority": {
                            "type": "string",
                            "enum": ["low", "medium", "high"],
                            "description": "Suggested priority level.",
                        },
                        "estimated_hours": {
                            "type": "number",
                            "description": "Estimated hours to complete.",
                        },
                        "key_actions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of 2-4 concrete next actions.",
                        },
                    },
                    "required": [
                        "summary",
                        "suggested_priority",
                        "estimated_hours",
                        "key_actions",
                    ],
                },
            }
        ],
        tool_choice={"type": "tool", "name": "submit_task_analysis"},
        messages=[
            {
                "role": "user",
                "content": (
                    f"Analyse this task:\n\n"
                    f"Title: {title}\n"
                    f"Description: {description or 'No description provided.'}"
                ),
            }
        ],
    )

    try:
        tool_input = response.content[0].input
        return TaskAnalysis(**tool_input)
    except (ValidationError, AttributeError) as e:
        raise ValueError(f"LLM returned invalid structure: {e}")


# ── Agent with Tool Use ───────────────────────────────────────────────────────

# Tool definitions — what the agent can do
# TEMPLATE NOTE: Add your own tools here. Each tool needs:
#   - name: snake_case identifier
#   - description: clear description of what it does and when to use it
#   - input_schema: JSON Schema for the tool's parameters
AGENT_TOOLS = [
    {
        "name": "get_task_details",
        "description": "Retrieves the full details of a task by its ID.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "The ID of the task to retrieve.",
                },
            },
            "required": ["task_id"],
        },
    },
    {
        "name": "get_user_tasks",
        "description": "Retrieves all tasks belonging to a specific user.",
        "input_schema": {
            "type": "object",
            "properties": {
                "user_id": {
                    "type": "integer",
                    "description": "The ID of the user whose tasks to retrieve.",
                },
            },
            "required": ["user_id"],
        },
    },
    {
        "name": "calculate_task_discount",
        "description": "Calculates the discounted price for a task-related service based on user tier.",
        "input_schema": {
            "type": "object",
            "properties": {
                "price": {"type": "number"},
                "tier": {
                    "type": "string",
                    "enum": ["free", "pro", "enterprise"],
                },
            },
            "required": ["price", "tier"],
        },
    },
]


def execute_agent_tool(tool_name: str, tool_input: dict) -> str:
    """
    Executes the tool selected by the agent and returns the result as a JSON string.

    TEMPLATE NOTE:
        Add cases for each tool in AGENT_TOOLS. Each case should call
        your service/DB functions and return a JSON-serialisable string.

    TESTING NOTE:
        Test this function independently (no LLM needed) — it's pure logic.
        Verify correct output for each tool and ValueError for unknown tools.
    """
    if tool_name == "get_task_details":
        # In production: query the DB. Here we return mock data for illustration.
        return json.dumps(
            {
                "id": tool_input["task_id"],
                "title": "Sample Task",
                "status": "todo",
                "priority": "medium",
            }
        )

    if tool_name == "get_user_tasks":
        return json.dumps(
            {
                "user_id": tool_input["user_id"],
                "tasks": [
                    {"id": 1, "title": "Task 1", "status": "todo"},
                    {"id": 2, "title": "Task 2", "status": "in_progress"},
                ],
            }
        )

    if tool_name == "calculate_task_discount":
        from src.services.user_service import calculate_discount

        price = calculate_discount(tool_input["price"], tool_input["tier"])
        return json.dumps({"discounted_price": price})

    raise ValueError(
        f"Unknown tool: {tool_name}. Available: {[t['name'] for t in AGENT_TOOLS]}"
    )


def run_task_agent(user_message: str) -> str:
    """
    Runs one agent turn — handles tool use if Claude requests it.

    Flow:
        1. Send user message to Claude with available tools
        2. If Claude returns stop_reason="tool_use", execute the requested tool
        3. Send the tool result back to Claude for a final natural language answer
        4. If Claude returns stop_reason="end_turn", return the answer directly

    Args:
        user_message: The user's question or instruction.

    Returns:
        Claude's final natural language response.

    TESTING NOTE:
        Use mock_create.side_effect = [tool_use_response, text_response]
        to simulate the two-call flow. See tests/unit/test_ai_service.py.
    """
    response = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        tools=AGENT_TOOLS,
        messages=[{"role": "user", "content": user_message}],
    )

    # Claude wants to use a tool
    if response.stop_reason == "tool_use":
        tool_block = response.content[0]
        tool_result = execute_agent_tool(tool_block.name, tool_block.input)

        # Send the tool result back to Claude for a final answer
        final_response = client.messages.create(
            model=MODEL,
            max_tokens=1000,
            tools=AGENT_TOOLS,
            messages=[
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response.content},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_block.id,
                            "content": tool_result,
                        }
                    ],
                },
            ],
        )
        return final_response.content[0].text

    # Claude answered directly without needing a tool
    return response.content[0].text
