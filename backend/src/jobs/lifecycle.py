"""
Job lifecycle state machine.

Defines valid state transitions to enforce the job lifecycle:
    queued → claimed → running → completed
                              → failed → (retry) → queued
                                       → (max retries) → dead

This prevents invalid transitions at the application level,
ensuring data integrity regardless of concurrent access patterns.
"""

from typing import Optional

from src.core.exceptions import InvalidStateTransitionError

# ─── Valid State Transitions ─────────────────────────────────
# Maps current_state → set of valid next_states
VALID_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"claimed", "cancelled", "scheduled"},
    "scheduled": {"queued", "cancelled"},
    "claimed": {"running", "queued"},  # queued = release back (worker crash recovery)
    "running": {"completed", "failed"},
    "failed": {"queued", "dead"},  # queued = retry, dead = DLQ
    "completed": set(),  # Terminal state
    "dead": {"queued"},  # Manual retry from DLQ
    "cancelled": set(),  # Terminal state
}

# Terminal states (no further transitions allowed except manual DLQ retry)
TERMINAL_STATES = {"completed", "cancelled"}

# Active states (job is being processed)
ACTIVE_STATES = {"claimed", "running"}

# Retriable states
RETRIABLE_STATES = {"failed", "dead"}


def validate_transition(current_status: str, new_status: str) -> None:
    """
    Validate that a job state transition is allowed.

    Args:
        current_status: The current job status.
        new_status: The desired new status.

    Raises:
        InvalidStateTransitionError: If the transition is not allowed.
    """
    valid_next = VALID_TRANSITIONS.get(current_status, set())
    if new_status not in valid_next:
        raise InvalidStateTransitionError(
            current_state=current_status,
            target_state=new_status,
            resource="Job",
        )


def can_transition(current_status: str, new_status: str) -> bool:
    """Check if a transition is valid without raising an exception."""
    valid_next = VALID_TRANSITIONS.get(current_status, set())
    return new_status in valid_next


def is_terminal(status: str) -> bool:
    """Check if a status is a terminal (final) state."""
    return status in TERMINAL_STATES


def is_active(status: str) -> bool:
    """Check if a job is currently being processed."""
    return status in ACTIVE_STATES


def is_retriable(status: str) -> bool:
    """Check if a job can be retried."""
    return status in RETRIABLE_STATES
