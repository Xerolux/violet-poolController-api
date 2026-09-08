# violet-poolController-api - API for Violet Pool Controller
# Copyright (C) 2024-2026  Xerolux
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.


"""Input sanitization utilities for user inputs and API parameters."""

from __future__ import annotations

import logging
import math
import re
import unicodedata
from html import escape
from typing import Any

_LOGGER = logging.getLogger(__name__)

_MAX_DEVICE_KEY_LENGTH = 50
_MAX_API_PARAM_LENGTH = 100


class InputSanitizer:
    """Input sanitization for security and data integrity.

    Protects against:
    - XSS (Cross-Site Scripting)
    - SQL injection (not relevant for an HTTP API, but defended against)
    - Command Injection
    - Path Traversal
    - Unerwarteten Zeichen
    """

    # Erlaubte Zeichen-Patterns
    ALPHANUMERIC = re.compile(r"^[a-zA-Z0-9]+$")
    ALPHANUMERIC_UNDERSCORE = re.compile(r"^[a-zA-Z0-9_]+$")
    ALPHANUMERIC_DASH_UNDERSCORE = re.compile(r"^[a-zA-Z0-9_-]+$")
    NUMERIC = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
    INTEGER = re.compile(r"^-?[0-9]+$")
    FLOAT = re.compile(r"^-?[0-9]+\.[0-9]+$")

    # Dangerous patterns
    DANGEROUS_CHARS = re.compile(r'[<>&"\';\\]')
    PATH_TRAVERSAL = re.compile(r"\.\.|/|\\")
    COMMAND_INJECTION = re.compile(r"[;&|`$(){}[\]]")

    @staticmethod
    def sanitize_string(
        value: Any,  # noqa: ANN401
        max_length: int = 255,
        *,
        allow_special_chars: bool = False,
        escape_html: bool = True,
    ) -> str:
        """Sanitize a string value.

        Args:
            value: The value to convert.
            max_length: Maximum length.
            allow_special_chars: Erlaube Sonderzeichen (sonst nur alphanumerisch)
            escape_html: Whether to HTML-escape the result.

        Returns:
            Sanitisierter String

        Raises:
            ValueError: If the input is invalid.

        """
        if value is None:
            return ""

        # Konvertiere zu String
        str_value = str(value).strip()

        # Unicode normalisation (NFKD, defence in depth)
        # Normalized Form Compatibility Decomposition
        str_value = unicodedata.normalize("NFKD", str_value)

        # Length validation
        if len(str_value) > max_length:
            _LOGGER.warning(
                "String too long (%d > %d), truncating: %s...",
                len(str_value),
                max_length,
                str_value[:50],
            )
            str_value = str_value[:max_length]

        if not allow_special_chars:
            original = str_value
            str_value = re.sub(r"[^a-zA-Z0-9 _-]", "", str_value)
            if str_value != original:
                _LOGGER.warning(
                    "Removed dangerous characters: '%s' -> '%s'",
                    original,
                    str_value,
                )
        if escape_html:
            str_value = escape(str_value)

        return str_value

    @staticmethod
    def sanitize_numeric(value: Any) -> float:  # noqa: ANN401
        """Return *value* as a finite float, or 0.0 if it is not a number.

        A single comma is read as a decimal separator before anything else,
        because the controller emits German-formatted numbers in places
        (``getLiveTrace``).  Without that step the digit-extraction fallback
        below turned ``"1,5"`` into ``15.0`` - a different number, silently.

        A value carrying a unit (``"12.5 mL"``) still yields its number; a
        string whose digits do not form a valid float (``"1.2.3"``) yields the
        0.0 default.

        Args:
            value: The value to convert.

        Returns:
            The value as a finite float, or 0.0.

        """
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if not math.isfinite(float(value)):
                _LOGGER.warning("Non-finite numeric value: %s", value)
                return 0.0
            return float(value)

        str_value = str(value).strip()
        # Decimal comma first, so the fallback never concatenates the parts.
        if str_value.count(",") == 1 and "." not in str_value:
            str_value = str_value.replace(",", ".")

        try:
            parsed = float(str_value)
        except (ValueError, TypeError, OverflowError):
            parsed = None

        if parsed is None:
            has_minus = str_value.startswith("-")
            cleaned = re.sub(r"[^0-9.]", "", str_value)
            if has_minus and cleaned:
                cleaned = f"-{cleaned}"
            try:
                parsed = float(cleaned)
            except (ValueError, TypeError, OverflowError):
                _LOGGER.warning("Invalid numeric value: %s", value)
                return 0.0

        if not math.isfinite(parsed):
            _LOGGER.warning("Non-finite numeric value: %s", value)
            return 0.0
        return parsed

    @staticmethod
    def sanitize_integer(
        value: Any,  # noqa: ANN401
        min_value: int | None = None,
        max_value: int | None = None,
        default: int = 0,
    ) -> int:
        """Sanitize an integer value.

        Args:
            value: The value to convert.
            min_value: Lowest allowed value.
            max_value: Highest allowed value.
            default: Value returned when conversion fails.

        Returns:
            The sanitized integer.

        """
        try:
            try:
                int_value = int(value)
            except (ValueError, TypeError, OverflowError):
                int_value = int(float(value))

            # Range-Validierung
            if min_value is not None and int_value < min_value:
                _LOGGER.warning(
                    "Integer value %d below min %d, clamping",
                    int_value,
                    min_value,
                )
                return min_value

            if max_value is not None and int_value > max_value:
                _LOGGER.warning(
                    "Integer value %d above max %d, clamping",
                    int_value,
                    max_value,
                )
                return max_value

        except (ValueError, TypeError, OverflowError) as err:
            _LOGGER.warning(
                "Invalid integer value '%s', using default %d: %s",
                value,
                default,
                err,
            )
            return default
        else:
            return int_value

    @staticmethod
    def sanitize_float(
        value: Any,  # noqa: ANN401
        min_value: float | None = None,
        max_value: float | None = None,
        precision: int = 2,
        default: float = 0.0,
    ) -> float:
        """Sanitize a float value.

        Args:
            value: The value to convert.
            min_value: Lowest allowed value.
            max_value: Highest allowed value.
            precision: Number of decimal places.
            default: Value returned when conversion fails.

        Returns:
            Sanitisierter Float

        """
        try:
            float_value = float(value)
            if not math.isfinite(float_value):
                _LOGGER.warning(
                    "Non-finite float value '%s', using default %.2f",
                    value,
                    default,
                )
                return default

            # Range-Validierung
            if min_value is not None and float_value < min_value:
                _LOGGER.warning(
                    "Float value %.2f below min %.2f, clamping",
                    float_value,
                    min_value,
                )
                return min_value

            if max_value is not None and float_value > max_value:
                _LOGGER.warning(
                    "Float value %.2f above max %.2f, clamping",
                    float_value,
                    max_value,
                )
                return max_value

            # Precision
            return round(float_value, precision)

        except (ValueError, TypeError) as err:
            _LOGGER.warning(
                "Invalid float value '%s', using default %.2f: %s",
                value,
                default,
                err,
            )
            return default

    @staticmethod
    def sanitize_boolean(value: Any, *, default: bool = False) -> bool:  # noqa: ANN401
        """Sanitize a boolean value.

        Args:
            value: The value to convert.
            default: Value returned when conversion fails.

        Returns:
            Sanitisierter Boolean

        """
        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            lower_value = value.lower().strip()
            if lower_value in {"true", "1", "yes", "on", "enabled"}:
                return True
            if lower_value in {"false", "0", "no", "off", "disabled"}:
                return False

        if isinstance(value, (int, float)):
            return bool(value)

        _LOGGER.warning(
            "Invalid boolean value '%s', using default %s",
            value,
            default,
        )
        return default

    @staticmethod
    def validate_device_key(key: str) -> str:
        """Validate a device key (PUMP, HEATER, pH_value, ...).

        The key is returned unchanged.  Controller keys are case-sensitive -
        ``pH_value`` and ``onewire1_value`` are real keys - so an invalid key
        is rejected rather than rewritten into a different, valid-looking one.

        Args:
            key: The device key to validate.

        Returns:
            The key, unchanged.

        Raises:
            ValueError: If the key is empty, too long, or contains characters
                outside ``[A-Za-z0-9_]``.

        """
        if not key:
            msg = "Device key must not be empty"
            raise ValueError(msg)

        if len(key) > _MAX_DEVICE_KEY_LENGTH:
            msg = f"Device key too long: {len(key)} > {_MAX_DEVICE_KEY_LENGTH}"
            raise ValueError(msg)

        if not re.fullmatch(r"[A-Za-z0-9_]+", key):
            msg = f"Device key contains invalid characters: {key!r}"
            raise ValueError(msg)

        return key

    @staticmethod
    def validate_api_parameter(param: str) -> str:
        """Validate an API parameter name.

        The parameter is returned unchanged.  Stripping "dangerous" characters
        used to turn ``DOSAGE_ph.minus`` into ``DOSAGE_phminus``, which is a
        real, different controller setting - a typo would silently write to
        the wrong key.  An invalid name is now an error.

        Args:
            param: The parameter name to validate.

        Returns:
            The parameter name, unchanged.

        Raises:
            ValueError: If the parameter is empty, too long, contains a path
                traversal sequence, or characters outside ``[A-Za-z0-9_-]``.

        """
        if not param:
            msg = "API parameter must not be empty"
            raise ValueError(msg)

        # Check for path traversal before anything else.
        if InputSanitizer.PATH_TRAVERSAL.search(param):
            msg = f"Path traversal detected in parameter: {param}"
            raise ValueError(msg)

        if len(param) > _MAX_API_PARAM_LENGTH:
            msg = f"API parameter too long: {len(param)} > {_MAX_API_PARAM_LENGTH}"
            raise ValueError(msg)

        if not re.fullmatch(r"[A-Za-z0-9_-]+", param):
            msg = f"API parameter contains invalid characters: {param!r}"
            raise ValueError(msg)

        return param

    @staticmethod
    def validate_temperature(
        temp: Any,  # noqa: ANN401
        min_temp: float = -50.0,
        max_temp: float = 100.0,
    ) -> float:
        """Validate a temperature value.

        Args:
            temp: The temperature value.
            min_temp: Minimale Temperatur
            max_temp: Maximale Temperatur

        Returns:
            Validierte Temperatur

        """
        return InputSanitizer.sanitize_float(
            temp,
            min_value=min_temp,
            max_value=max_temp,
            precision=1,
            default=20.0,
        )

    @staticmethod
    def validate_ph_value(ph: Any) -> float:  # noqa: ANN401
        """Validate a pH value.

        Args:
            ph: The pH value.

        Returns:
            The validated pH value (6.0-8.0), matching the range the
            controller accepts as a setpoint (see ``SETPOINT_RANGES``).

        """
        return InputSanitizer.sanitize_float(
            ph,
            min_value=6.0,
            max_value=8.0,
            precision=1,
            default=7.2,
        )

    @staticmethod
    def validate_orp_value(orp: Any) -> int:  # noqa: ANN401
        """Validate an ORP (redox potential) value.

        Args:
            orp: The ORP value in mV.

        Returns:
            The validated ORP value (500-900 mV).

        """
        return InputSanitizer.sanitize_integer(
            orp,
            min_value=500,
            max_value=900,
            default=700,
        )

    @staticmethod
    def validate_chlorine_level(chlorine: Any) -> float:  # noqa: ANN401
        """Validate a chlorine value.

        Args:
            chlorine: The chlorine value in mg/l.

        Returns:
            The validated chlorine value (0.0-5.0 mg/l).

        """
        return InputSanitizer.sanitize_float(
            chlorine,
            min_value=0.0,
            max_value=5.0,
            precision=1,
            default=0.6,
        )


# Singleton instance for convenient access
_sanitizer = InputSanitizer()


def sanitize_string(*args: Any, **kwargs: Any) -> str:  # noqa: ANN401
    """Shortcut for InputSanitizer.sanitize_string()."""
    return _sanitizer.sanitize_string(*args, **kwargs)


def sanitize_integer(*args: Any, **kwargs: Any) -> int:  # noqa: ANN401
    """Shortcut for InputSanitizer.sanitize_integer()."""
    return _sanitizer.sanitize_integer(*args, **kwargs)


def sanitize_float(*args: Any, **kwargs: Any) -> float:  # noqa: ANN401
    """Shortcut for InputSanitizer.sanitize_float()."""
    return _sanitizer.sanitize_float(*args, **kwargs)


def sanitize_boolean(*args: Any, **kwargs: Any) -> bool:  # noqa: ANN401
    """Shortcut for InputSanitizer.sanitize_boolean()."""
    return _sanitizer.sanitize_boolean(*args, **kwargs)


__all__ = [
    "InputSanitizer",
    "sanitize_boolean",
    "sanitize_float",
    "sanitize_integer",
    "sanitize_string",
]
