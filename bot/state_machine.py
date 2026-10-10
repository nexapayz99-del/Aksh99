import logging
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger("StateMachine")

class AuthState(Enum):
    IDLE = "idle"
    WAITING_PHONE = "waiting_phone"
    WAITING_CODE = "waiting_code"
    WAITING_PASSWORD = "waiting_password"
    IMPORTING_SESSION = "importing_session"

class StateMachine:
    """
    In-memory state machine for handling multi-step UI flows (e.g., login).
    Tracks user interaction states and temporary data.
    """
    def __init__(self):
        # Format: {user_id: {"state": AuthState, "data": {...}}}
        self._states: Dict[int, Dict[str, Any]] = {}

    def get_state(self, user_id: int) -> AuthState:
        """Retrieves the current state of a user."""
        return self._states.get(user_id, {}).get("state", AuthState.IDLE)

    def set_state(self, user_id: int, state: AuthState, data: Optional[Dict[str, Any]] = None):
        """Sets the state and optional contextual data for a user."""
        if user_id not in self._states:
            self._states[user_id] = {}
        
        self._states[user_id]["state"] = state
        if data is not None:
            # Merge or overwrite data
            current_data = self._states[user_id].get("data", {})
            current_data.update(data)
            self._states[user_id]["data"] = current_data
            
        logger.debug(f"User {user_id} state transitioned to {state.name}")

    def get_data(self, user_id: int, key: str) -> Any:
        """Retrieves specific contextual data for a user."""
        return self._states.get(user_id, {}).get("data", {}).get(key)

    def clear_state(self, user_id: int):
        """Resets a user's state to IDLE and clears their data."""
        if user_id in self._states:
            del self._states[user_id]
        logger.debug(f"User {user_id} state cleared.")

state_manager = StateMachine()
