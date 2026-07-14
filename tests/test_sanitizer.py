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
