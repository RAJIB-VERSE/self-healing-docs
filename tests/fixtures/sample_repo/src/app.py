"""Sample application code for dochealer tests."""
from __future__ import annotations

DEFAULT_TIMEOUT = 30


def get_user(user_id: int, include_inactive: bool = False) -> dict:
    """Fetch a user by ID.

    Set include_inactive to also return deactivated accounts.
    """
    return {"id": user_id, "active": not include_inactive}


def delete_user(user_id: int) -> bool:
    """Permanently delete a user."""
    return True


class Settings:
    """Application settings loaded from the environment."""

    retry_delay: int = 5
    max_retries: int = 3

    def reload(self) -> None:
        """Re-read settings from the environment."""


def _internal_helper(x: int) -> int:
    # private; docs never mention this
    return x * 2
