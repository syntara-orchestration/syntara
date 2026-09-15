"""Unit tests for form prompt status transitions.

Tests the can_transition function and terminal status constants.
"""

from syntara.forms.models import TERMINAL_PROMPT_STATUSES, FormPromptStatus, can_transition


class TestStatusTransitions:
    """Test form prompt status transition logic."""

    def test_pending_to_submitted(self) -> None:
        """Test that PENDING can transition to SUBMITTED."""
        assert can_transition(FormPromptStatus.PENDING, FormPromptStatus.SUBMITTED)

    def test_pending_to_expired(self) -> None:
        """Test that PENDING can transition to EXPIRED."""
        assert can_transition(FormPromptStatus.PENDING, FormPromptStatus.EXPIRED)

    def test_pending_to_cancelled(self) -> None:
        """Test that PENDING can transition to CANCELLED."""
        assert can_transition(FormPromptStatus.PENDING, FormPromptStatus.CANCELLED)

    def test_pending_to_pending_rejected(self) -> None:
        """Test that PENDING cannot transition to itself."""
        assert not can_transition(FormPromptStatus.PENDING, FormPromptStatus.PENDING)

    def test_submitted_is_terminal(self) -> None:
        """Test that SUBMITTED cannot transition to any state."""
        assert not can_transition(FormPromptStatus.SUBMITTED, FormPromptStatus.PENDING)
        assert not can_transition(FormPromptStatus.SUBMITTED, FormPromptStatus.SUBMITTED)
        assert not can_transition(FormPromptStatus.SUBMITTED, FormPromptStatus.EXPIRED)
        assert not can_transition(FormPromptStatus.SUBMITTED, FormPromptStatus.CANCELLED)

    def test_expired_is_terminal(self) -> None:
        """Test that EXPIRED cannot transition to any state."""
        assert not can_transition(FormPromptStatus.EXPIRED, FormPromptStatus.PENDING)
        assert not can_transition(FormPromptStatus.EXPIRED, FormPromptStatus.SUBMITTED)
        assert not can_transition(FormPromptStatus.EXPIRED, FormPromptStatus.EXPIRED)
        assert not can_transition(FormPromptStatus.EXPIRED, FormPromptStatus.CANCELLED)

    def test_cancelled_is_terminal(self) -> None:
        """Test that CANCELLED cannot transition to any state."""
        assert not can_transition(FormPromptStatus.CANCELLED, FormPromptStatus.PENDING)
        assert not can_transition(FormPromptStatus.CANCELLED, FormPromptStatus.SUBMITTED)
        assert not can_transition(FormPromptStatus.CANCELLED, FormPromptStatus.EXPIRED)
        assert not can_transition(FormPromptStatus.CANCELLED, FormPromptStatus.CANCELLED)

    def test_terminal_statuses_constant(self) -> None:
        """Test that TERMINAL_PROMPT_STATUSES contains all terminal statuses."""
        assert FormPromptStatus.SUBMITTED in TERMINAL_PROMPT_STATUSES
        assert FormPromptStatus.EXPIRED in TERMINAL_PROMPT_STATUSES
        assert FormPromptStatus.CANCELLED in TERMINAL_PROMPT_STATUSES
        assert FormPromptStatus.PENDING not in TERMINAL_PROMPT_STATUSES

    def test_enum_string_values(self) -> None:
        """Test that enum string values are stable and lowercase."""
        assert FormPromptStatus.PENDING.value == "pending"
        assert FormPromptStatus.SUBMITTED.value == "submitted"
        assert FormPromptStatus.EXPIRED.value == "expired"
        assert FormPromptStatus.CANCELLED.value == "cancelled"
