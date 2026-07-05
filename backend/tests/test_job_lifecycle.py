"""
Tests for job lifecycle state machine.

Covers: valid transitions, invalid transitions, terminal states, retriability.
"""

import pytest

from src.core.exceptions import InvalidStateTransitionError
from src.jobs.lifecycle import (
    can_transition,
    is_active,
    is_retriable,
    is_terminal,
    validate_transition,
)


class TestJobLifecycle:
    """Test the job state machine transitions."""

    def test_valid_transitions(self):
        """All valid transitions should not raise."""
        valid_cases = [
            ("queued", "claimed"),
            ("queued", "cancelled"),
            ("queued", "scheduled"),
            ("scheduled", "queued"),
            ("scheduled", "cancelled"),
            ("claimed", "running"),
            ("claimed", "queued"),  # Worker crash recovery
            ("running", "completed"),
            ("running", "failed"),
            ("failed", "queued"),  # Retry
            ("failed", "dead"),   # Max retries → DLQ
            ("dead", "queued"),   # Manual DLQ retry
        ]
        for current, target in valid_cases:
            validate_transition(current, target)  # Should not raise

    def test_invalid_transitions(self):
        """Invalid transitions should raise InvalidStateTransitionError."""
        invalid_cases = [
            ("completed", "running"),  # Can't restart completed
            ("completed", "queued"),   # Can't re-queue completed
            ("cancelled", "queued"),   # Can't re-queue cancelled
            ("queued", "completed"),   # Can't skip to completed
            ("queued", "running"),     # Must go through claimed
            ("running", "queued"),     # Can't go back to queued from running
            ("failed", "running"),     # Must go through queued first
        ]
        for current, target in invalid_cases:
            with pytest.raises(InvalidStateTransitionError):
                validate_transition(current, target)

    def test_can_transition(self):
        """can_transition should return bool without raising."""
        assert can_transition("queued", "claimed") is True
        assert can_transition("completed", "running") is False
        assert can_transition("running", "completed") is True
        assert can_transition("dead", "queued") is True

    def test_terminal_states(self):
        """Terminal states should be identified correctly."""
        assert is_terminal("completed") is True
        assert is_terminal("cancelled") is True
        assert is_terminal("queued") is False
        assert is_terminal("running") is False
        assert is_terminal("dead") is False  # Dead can be retried

    def test_active_states(self):
        """Active states should be identified correctly."""
        assert is_active("claimed") is True
        assert is_active("running") is True
        assert is_active("queued") is False
        assert is_active("completed") is False

    def test_retriable_states(self):
        """Retriable states should be identified correctly."""
        assert is_retriable("failed") is True
        assert is_retriable("dead") is True
        assert is_retriable("queued") is False
        assert is_retriable("completed") is False
        assert is_retriable("running") is False
