"""Shared exceptions and validation helpers for the API client."""

from __future__ import annotations

import math

from .const_api import TARGET_MIN_CHLORINE, TARGET_ORP, TARGET_PH

SETPOINT_RANGES: dict[str, tuple[float, float]] = {
    TARGET_PH: (6.0, 8.0),
    TARGET_ORP: (500.0, 900.0),
    TARGET_MIN_CHLORINE: (0.0, 5.0),
    "HEATER_set_temp": (5.0, 45.0),
    "SOLAR_maxtemp": (5.0, 55.0),
}


class VioletPoolAPIError(Exception):
    """Base exception for all Violet Pool Controller API errors."""


class VioletAuthError(VioletPoolAPIError):
    """Raised when the controller rejects credentials (HTTP 401 or 403)."""


class VioletTimeoutError(VioletPoolAPIError):
    """Raised when an HTTP request to the controller exceeds the timeout."""


class VioletPayloadError(VioletPoolAPIError):
    """Raised when the controller returns a malformed or unparseable response."""


class VioletSetpointError(VioletPoolAPIError, ValueError):
    """Raised when a setpoint value is outside its documented valid range."""


class VioletUnsafeOperationError(VioletPoolAPIError):
    """Raised for potentially dangerous operations without acknowledgment."""


class DeterministicClientError(Exception):
    """Internal marker for deterministic HTTP client errors."""

    def __init__(self, msg: str, *, is_auth: bool = False) -> None:
        super().__init__(msg)
        self.is_auth = is_auth


def validate_setpoint(field: str, value: float) -> None:
    """Validate a setpoint value against documented controller ranges."""
    if not math.isfinite(value):
        msg = f"Invalid setpoint for '{field}': {value!r} is not a finite number"
        raise VioletSetpointError(msg)

    bounds = SETPOINT_RANGES.get(field)
    if bounds is None:
        return

    lo, hi = bounds
    if not lo <= value <= hi:
        msg = f"Setpoint '{field}' value {value} is outside the valid range [{lo}, {hi}]"
        raise VioletSetpointError(msg)


def validate_duration(
    value: int | float,
    *,
    minimum: int = 0,
    maximum: int = 86400,
) -> int:
    """Validate an actuator duration without silently coercing invalid values."""
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as err:
        msg = f"Duration must be a whole number between {minimum} and {maximum} seconds"
        raise VioletPoolAPIError(msg) from err
    if not math.isfinite(numeric) or not numeric.is_integer() or not minimum <= numeric <= maximum:
        msg = f"Duration must be a whole number between {minimum} and {maximum} seconds"
        raise VioletPoolAPIError(msg)
    return int(numeric)
