"""State mapping layer for Peak Monitor integration.

This module provides clean separation between:
- Internal state values (ACTIVE_STATE_*)
- User-facing state keys (STATE_*)
- Reason codes (REASON_*)

Following Silver-tier architectural pattern of separating:
1. Calculation layer (coordinator logic in __init__.py)
2. Mapping layer (this module)
3. Presentation layer (sensor.py with translations)
"""
from __future__ import annotations

from .const import (
    ACTIVE_STATE_OFF,
    ACTIVE_STATE_ON,
    ACTIVE_STATE_REDUCED,
    STATE_ACTIVE,
    STATE_INACTIVE,
    STATE_REDUCED,
    REASON_EXTERNAL_MUTE,
    REASON_EXCLUDED_MONTH,
    REASON_HOLIDAY,
    REASON_WEEKEND,
    REASON_TIME_OF_DAY,
    REASON_EXTERNAL_CONTROL,
)


class StateMapper:
    """Maps internal states to user-facing presentation states."""
    
    # Internal to user-facing state mapping
    _STATE_MAP = {
        ACTIVE_STATE_OFF: STATE_INACTIVE,
        ACTIVE_STATE_ON: STATE_ACTIVE,
        ACTIVE_STATE_REDUCED: STATE_REDUCED,
    }
    
    # Valid reason codes for inactive state
    _VALID_INACTIVE_REASONS = {
        REASON_EXTERNAL_MUTE,
        REASON_EXCLUDED_MONTH,
        REASON_HOLIDAY,
        REASON_WEEKEND,
        REASON_TIME_OF_DAY,
    }
    
    # Valid reason codes for reduced state
    _VALID_REDUCED_REASONS = {
        REASON_TIME_OF_DAY,
        REASON_EXTERNAL_CONTROL,
    }
    
    @classmethod
    def map_state(cls, internal_state: str) -> str:
        """Map internal state to user-facing state.
        
        Args:
            internal_state: One of ACTIVE_STATE_OFF, ACTIVE_STATE_ON, ACTIVE_STATE_REDUCED
            
        Returns:
            User-facing state: STATE_INACTIVE, STATE_ACTIVE, or STATE_REDUCED
        """
        return cls._STATE_MAP.get(internal_state, STATE_INACTIVE)
    
    @classmethod
    def validate_reason(cls, state: str, reason: str) -> bool:
        """Validate that a reason code is appropriate for the given state.
        
        Args:
            state: The current state (STATE_INACTIVE, STATE_ACTIVE, STATE_REDUCED)
            reason: The reason code to validate
            
        Returns:
            True if the reason is valid for this state, False otherwise
        """
        if state == STATE_INACTIVE:
            return reason in cls._VALID_INACTIVE_REASONS
        elif state == STATE_REDUCED:
            return reason in cls._VALID_REDUCED_REASONS
        else:  # STATE_ACTIVE
            return False  # Active state should not have reasons
    
    @classmethod
    def get_valid_reasons(cls, state: str) -> set[str]:
        """Get all valid reason codes for a given state.
        
        Args:
            state: The current state
            
        Returns:
            Set of valid reason codes for this state
        """
        if state == STATE_INACTIVE:
            return cls._VALID_INACTIVE_REASONS.copy()
        elif state == STATE_REDUCED:
            return cls._VALID_REDUCED_REASONS.copy()
        else:
            return set()
    
    @classmethod
    def get_state_options(cls) -> list[str]:
        """Get list of all possible user-facing states.
        
        Returns:
            List of state strings in the order they should appear
        """
        return [STATE_INACTIVE, STATE_REDUCED, STATE_ACTIVE]
