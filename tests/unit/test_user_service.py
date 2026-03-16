"""
Unit tests for user_service.py

WHAT WE TEST HERE:
    - Pure business logic functions (no DB, no HTTP)
    - calculate_discount: discounts per tier
    - validate_task_status_transition: allowed/disallowed transitions

WHY UNIT TESTS:
    - Millisecond execution — run constantly during development
    - Isolate logic bugs from infrastructure bugs
    - Easiest to write and maintain

PATTERNS DEMONSTRATED:
    - AAA (Arrange-Act-Assert)
    - @pytest.mark.parametrize for multiple input scenarios
    - pytest.raises for error path testing
    - make_user() factory for object creation without DB
"""

import pytest

from src.models import TierEnum
from src.services.user_service import (
    calculate_discount,
    validate_task_status_transition,
)

# Import the factory function directly (not a fixture — it doesn't need the DB)
from tests.conftest import make_user

# ═════════════════════════════════════════════════════════════════════════════
# calculate_discount
# ═════════════════════════════════════════════════════════════════════════════


class TestCalculateDiscount:
    """Tests for the calculate_discount() function."""

    # ── Happy paths ──────────────────────────────────────────────────────────

    def test_returns_full_price_for_free_tier(self):
        # Arrange
        price = 100.0
        tier = TierEnum.FREE

        # Act
        result = calculate_discount(price, tier)

        # Assert
        assert result == 100.0

    def test_applies_10_percent_discount_for_pro_tier(self):
        result = calculate_discount(100.0, TierEnum.PRO)
        assert result == 90.0

    def test_applies_25_percent_discount_for_enterprise_tier(self):
        result = calculate_discount(100.0, TierEnum.ENTERPRISE)
        assert result == 75.0

    def test_rounds_result_to_two_decimal_places(self):
        # 33.33 * 0.9 = 29.997 → should round to 30.0
        result = calculate_discount(33.33, TierEnum.PRO)
        assert result == 29.99

    # ── Parametrize — same logic, multiple inputs ─────────────────────────────
    # Use parametrize when testing the same behaviour with different values.
    # Each tuple is: (price, tier, expected_result)

    @pytest.mark.parametrize(
        "price,tier,expected",
        [
            (200.0, TierEnum.FREE, 200.0),
            (200.0, TierEnum.PRO, 180.0),
            (200.0, TierEnum.ENTERPRISE, 150.0),
            (0.0, TierEnum.PRO, 0.0),  # zero price edge case
            (0.01, TierEnum.PRO, 0.01),  # small value rounds correctly
        ],
    )
    def test_discount_amounts_for_all_tiers(self, price, tier, expected):
        assert calculate_discount(price, tier) == expected

    # ── Error paths ───────────────────────────────────────────────────────────

    def test_raises_value_error_for_unknown_tier(self):
        """match= verifies the error message contains the right info."""
        with pytest.raises(ValueError, match="Unknown tier: vip"):
            calculate_discount(100.0, "vip")

    def test_raises_value_error_for_empty_tier(self):
        with pytest.raises(ValueError, match="Unknown tier"):
            calculate_discount(100.0, "")

    # ── Edge cases ────────────────────────────────────────────────────────────

    def test_handles_negative_price(self):
        """Not a realistic scenario but verifies no crash."""
        result = calculate_discount(-100.0, TierEnum.PRO)
        assert result == -90.0


# ═════════════════════════════════════════════════════════════════════════════
# validate_task_status_transition
# ═════════════════════════════════════════════════════════════════════════════


class TestValidateTaskStatusTransition:
    """Tests for task status transition validation."""

    # ── Valid transitions ─────────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "current,new",
        [
            ("todo", "in_progress"),
            ("in_progress", "done"),
            ("in_progress", "todo"),  # undo
            ("done", "in_progress"),  # reopen
        ],
    )
    def test_returns_true_for_valid_transitions(self, current, new):
        result = validate_task_status_transition(current, new)
        assert result is True

    # ── Invalid transitions ───────────────────────────────────────────────────

    @pytest.mark.parametrize(
        "current,new",
        [
            ("todo", "done"),  # cannot skip in_progress
            ("done", "todo"),  # cannot go directly back to todo
            ("todo", "todo"),  # no-op transitions
        ],
    )
    def test_raises_for_invalid_transitions(self, current, new):
        with pytest.raises(ValueError, match="Cannot transition"):
            validate_task_status_transition(current, new)


# ═════════════════════════════════════════════════════════════════════════════
# make_user factory — testing the factory itself
# ═════════════════════════════════════════════════════════════════════════════


class TestMakeUserFactory:
    """
    Tests for the make_user() helper.

    TEMPLATE NOTE: Delete this class in your own project — it's here to
    demonstrate testing factory helpers. Your factories are test utilities,
    not production code, so testing them is optional.
    """

    def test_creates_user_with_default_free_tier(self):
        user = make_user()
        assert user.tier == "free"

    def test_creates_user_with_overridden_tier(self):
        user = make_user(tier="pro")
        assert user.tier == "pro"

    def test_creates_unique_emails_by_default(self):
        user1 = make_user()
        user2 = make_user()
        assert user1.email != user2.email

    def test_overridden_email_is_used(self):
        user = make_user(email="specific@example.com")
        assert user.email == "specific@example.com"
