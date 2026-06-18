"""Tests for violet_poolcontroller_api.parsers module."""

from datetime import UTC, datetime, timedelta

import pytest

from violet_poolcontroller_api.parsers import (
    parse_epoch_milliseconds,
    parse_epoch_seconds,
    parse_hms_string,
    parse_optional_seconds,
    parse_runtime_string,
    parse_uptime_string,
)


class TestParseRuntimeString:
    """parse_runtime_string converts labelled runtime strings to timedelta."""

    def test_hours_minutes_seconds(self):
        assert parse_runtime_string("04h 33m 12s") == timedelta(
            hours=4, minutes=33, seconds=12
        )

    def test_with_days(self):
        assert parse_runtime_string("1d 04h 33m 12s") == timedelta(
            days=1, hours=4, minutes=33, seconds=12
        )

    def test_partial_components(self):
        assert parse_runtime_string("2h") == timedelta(hours=2)
        assert parse_runtime_string("45m 30s") == timedelta(minutes=45, seconds=30)

    def test_empty_returns_zero(self):
        assert parse_runtime_string("") == timedelta(0)

    def test_non_matching_returns_zero(self):
        # The labelled regex does not match "HH:MM:SS"; that format is handled
        # by parse_hms_string. An all-optional match yields timedelta(0).
        assert parse_runtime_string("invalid") == timedelta(0)


class TestParseHmsString:
    """parse_hms_string converts "HH:MM:SS" strings to timedelta."""

    def test_valid_hms(self):
        assert parse_hms_string("01:30:45") == timedelta(hours=1, minutes=30, seconds=45)
        assert parse_hms_string("00:00:01") == timedelta(seconds=1)
        assert parse_hms_string("23:59:59") == timedelta(
            hours=23, minutes=59, seconds=59
        )

    def test_all_zeros(self):
        assert parse_hms_string("00:00:00") == timedelta(0)

    def test_invalid_returns_zero(self):
        assert parse_hms_string("invalid") == timedelta(0)
        assert parse_hms_string("1:2") == timedelta(0)

    def test_strips_whitespace(self):
        assert parse_hms_string("  01:30:45  ") == timedelta(
            hours=1, minutes=30, seconds=45
        )


class TestParseUptimeString:
    """parse_uptime_string converts CPU uptime strings to timedelta."""

    def test_days_hours_minutes(self):
        assert parse_uptime_string("250d 11h 48m") == timedelta(
            days=250, hours=11, minutes=48
        )

    def test_hours_minutes_only(self):
        assert parse_uptime_string("11h 48m") == timedelta(hours=11, minutes=48)

    def test_empty_returns_zero(self):
        assert parse_uptime_string("") == timedelta(0)

    def test_non_matching_returns_zero(self):
        assert parse_uptime_string("invalid") == timedelta(0)


class TestParseOptionalSeconds:
    """parse_optional_seconds converts float seconds (with NONE sentinel)."""

    def test_numeric_string(self):
        assert parse_optional_seconds("120") == timedelta(seconds=120)
        assert parse_optional_seconds("0") == timedelta(0)
        assert parse_optional_seconds("3600") == timedelta(hours=1)

    def test_float_string(self):
        assert parse_optional_seconds("1.5") == timedelta(seconds=1.5)

    def test_none_sentinel(self):
        assert parse_optional_seconds("NONE") is None
        assert parse_optional_seconds("none") is None
        assert parse_optional_seconds("None") is None

    def test_invalid_returns_none(self):
        assert parse_optional_seconds("invalid") is None


class TestParseEpochSeconds:
    """parse_epoch_seconds converts Unix seconds to a UTC datetime."""

    def test_known_timestamp(self):
        result = parse_epoch_seconds("1609459200")
        assert result == datetime(2021, 1, 1, tzinfo=UTC)

    def test_returns_datetime(self):
        result = parse_epoch_seconds("1700000000")
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_zero_is_sentinel(self):
        # The controller uses 0 to mean "no timestamp available".
        assert parse_epoch_seconds("0") is None

    def test_invalid_returns_none(self):
        assert parse_epoch_seconds("invalid") is None


class TestParseEpochMilliseconds:
    """parse_epoch_milliseconds converts Unix milliseconds to a UTC datetime."""

    def test_known_timestamp(self):
        result = parse_epoch_milliseconds("1609459200000")
        assert result == datetime(2021, 1, 1, tzinfo=UTC)

    def test_returns_datetime(self):
        result = parse_epoch_milliseconds("1700000000000")
        assert isinstance(result, datetime)
        assert result.tzinfo is not None

    def test_zero_is_sentinel(self):
        assert parse_epoch_milliseconds("0") is None

    def test_invalid_returns_none(self):
        assert parse_epoch_milliseconds("invalid") is None


class TestParserEmptyStringHandling:
    """Empty strings are handled per each parser's documented contract."""

    @pytest.mark.parametrize(
        ("parser", "expected"),
        [
            (parse_runtime_string, timedelta(0)),
            (parse_hms_string, timedelta(0)),
            (parse_uptime_string, timedelta(0)),
            (parse_optional_seconds, None),
            (parse_epoch_seconds, None),
            (parse_epoch_milliseconds, None),
        ],
    )
    def test_empty_string(self, parser, expected):
        assert parser("") == expected
