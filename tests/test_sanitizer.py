"""Tests for public input-sanitizing helpers."""

import math

import pytest

from violet_poolcontroller_api.utils_sanitizer import InputSanitizer


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), "nan", "inf"])
def test_sanitize_float_replaces_non_finite_values(value: object) -> None:
    result = InputSanitizer.sanitize_float(value, default=1.5)

    assert result == 1.5
    assert math.isfinite(result)


@pytest.mark.parametrize("value", [float("inf"), float("-inf"), "inf", "-inf"])
def test_sanitize_integer_replaces_infinite_values(value: object) -> None:
    assert InputSanitizer.sanitize_integer(value, default=7) == 7


def test_numeric_sanitizer_rejects_non_finite_values() -> None:
    assert InputSanitizer.sanitize_numeric(float("nan")) == 0.0
    assert InputSanitizer.sanitize_numeric(float("inf")) == 0.0


def test_numeric_sanitizer_parses_scientific_notation() -> None:
    """'1e10' must parse as 1e10, not as digit-stripped '110'."""
    assert InputSanitizer.sanitize_numeric("1e10") == 1e10
    assert InputSanitizer.sanitize_numeric("-2.5e-3") == -2.5e-3


def test_numeric_sanitizer_still_extracts_digits_from_messy_strings() -> None:
    """Non-numeric strings still fall back to best-effort digit extraction."""
    assert InputSanitizer.sanitize_numeric("12.5 mL") == 12.5


def test_validate_ph_value_matches_controller_setpoint_range() -> None:
    """The sanitizer's pH bounds must agree with SETPOINT_RANGES (6.0-8.0)."""
    assert InputSanitizer.validate_ph_value(8.5) == 8.0
    assert InputSanitizer.validate_ph_value(5.0) == 6.0
    assert InputSanitizer.validate_ph_value(7.2) == 7.2
