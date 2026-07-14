# violet-poolController-api - API für Violet Pool Controller
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

"""HTTP client utilities for the Violet Pool Controller."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import json
import logging
import math
import random
import re
import ssl
from typing import TYPE_CHECKING, Any, cast
from urllib.parse import urlparse, urlunparse

import aiohttp

from ._api_dosing import DosingMixin
from ._api_model import (  # noqa: F401
    SETPOINT_RANGES,
    DeterministicClientError,
    VioletAuthError,
    VioletPayloadError,
    VioletPoolAPIError,
    VioletSetpointError,
    VioletTimeoutError,
    VioletUnsafeOperationError,
    validate_duration,
    validate_setpoint,
)
from ._api_outputs import OutputsMixin
from ._api_readings import ReadingsMixin
from ._api_system import SystemMixin
from .circuit_breaker import CircuitBreaker, CircuitBreakerOpenError
from .const_api import (
    API_GET_CALIB_HISTORY,
    API_GET_CALIB_RAW_VALUES,
    API_GET_CONFIG,
    API_PRIORITY_NORMAL,
    API_RATE_LIMIT_BURST,
    API_RATE_LIMIT_REQUESTS,
    API_RATE_LIMIT_RETRY_AFTER,
    API_RATE_LIMIT_WINDOW,
    API_RESTORE_CALIBRATION,
    API_SET_CONFIG,
)
from .const_devices import DEVICE_PARAMETERS
from .utils_rate_limiter import RateLimiter
from .utils_sanitizer import InputSanitizer

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

_LOGGER = logging.getLogger(__name__)

_MAX_HOSTNAME_LENGTH = 253
_HTTP_SERVER_ERROR = 500
_HTTP_CLIENT_ERROR = 400
_HTTP_TOO_MANY_REQUESTS = 429
_HTTP_UNAUTHORIZED = 401
_HTTP_FORBIDDEN = 403
_MIN_CALIB_HISTORY_PARTS = 3

class VioletPoolAPI(ReadingsMixin, DosingMixin, OutputsMixin, SystemMixin):
    """A small HTTP client for interacting with the Violet Pool Controller.

    This class handles API requests, including authentication, rate limiting,
    and error handling. It provides methods for accessing various controller
    endpoints.
    """

    def __init__(  # noqa: PLR0913
        self,
        *,
        host: str,
        session: aiohttp.ClientSession,
        username: str | None = None,
        password: str | None = None,
        use_ssl: bool = False,
        verify_ssl: bool = True,
        timeout: int = 10,
        max_retries: int = 3,
        dosing_standalone: bool = False,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize the API helper.

        Args:
            host: The hostname or IP address of the controller.
            session: The aiohttp client session.
            username: The username for authentication.
            password: The password for authentication.
            use_ssl: Whether to use SSL for the connection.
            verify_ssl: Whether to verify SSL certificates (security feature).
            timeout: The request timeout in seconds.
            max_retries: The maximum number of retries for failed requests.
            dosing_standalone: Whether the controller runs in dosing-standalone
                mode without a connected base module.
            rate_limiter: Optional limiter to share explicitly between clients.

        """
        if session is None:
            msg = "A valid aiohttp session must be provided"
            raise ValueError(msg)

        self._base_url = self._build_secure_base_url(host, use_ssl=use_ssl).rstrip("/")

        self._session = session
        total_timeout = max(float(timeout), 1.0)
        self._timeout = aiohttp.ClientTimeout(total=total_timeout)
        self._max_retries = max(1, int(max_retries))
        self._dosing_standalone = bool(dosing_standalone)
        self._headers: dict[str, str] = {}
        if username:
            if ":" in username:
                msg = "Basic authentication username must not contain ':'"
                raise ValueError(msg)
            credentials = f"{username}:{password or ''}".encode()
            token = base64.b64encode(credentials).decode("ascii")
            self._headers["Authorization"] = f"Basic {token}"

        # SSL/TLS security configuration
        self._verify_ssl = verify_ssl
        self._use_ssl = use_ssl
        self._ssl_context: ssl.SSLContext | None = None
        if use_ssl and not verify_ssl:
            _LOGGER.warning(
                "SSL certificate verification is DISABLED. "
                "This is a security risk and should only be used for testing "
                "or with self-signed certificates in trusted networks.",
            )
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE

        # Rate limiting to protect the controller from being overloaded
        self._rate_limiter = rate_limiter or RateLimiter(
            max_requests=API_RATE_LIMIT_REQUESTS,
            time_window=API_RATE_LIMIT_WINDOW,
            burst_size=API_RATE_LIMIT_BURST,
            retry_after=API_RATE_LIMIT_RETRY_AFTER,
        )
        self._circuit_breaker = CircuitBreaker(
            expected_exception=VioletPoolAPIError,
            ignored_exceptions=(DeterministicClientError,),
        )
        _LOGGER.debug(
            "API initialized with rate limiting enabled, SSL=%s, verify_ssl=%s",
            use_ssl,
            verify_ssl,
        )

    # ---------------------------------------------------------------------
    # Public Properties
    # ---------------------------------------------------------------------

    @property
    def timeout(self) -> float:
        """Get current timeout in seconds.

        Returns:
            The timeout value in seconds.

        """
        return self._timeout.total or 0.0

    @property
    def max_retries(self) -> int:
        """Get maximum retry attempts.

        Returns:
            The maximum number of retry attempts.

        """
        return self._max_retries

    @property
    def dosing_standalone(self) -> bool:
        """Return whether dosing-standalone mode is enabled."""
        return self._dosing_standalone

    @property
    def _ssl_param(self) -> ssl.SSLContext | bool:
        """Return the SSL parameter for aiohttp requests.

        For plain-HTTP connections the value is ignored by aiohttp, so the
        library default (True) is returned.
        """
        if not self._use_ssl:
            return True
        if self._ssl_context is not None:
            return self._ssl_context
        return True

    # ---------------------------------------------------------------------
    # Generic helpers
    # ---------------------------------------------------------------------

    def _build_secure_base_url(self, host: str, *, use_ssl: bool) -> str:
        """Securely construct base URL with comprehensive validation."""
        # Strip existing protocols to prevent override
        host = host.strip()
        if host.startswith(("http://", "https://")):
            parsed = urlparse(host)
            host = parsed.netloc

        try:
            literal_ip = ipaddress.ip_address(host)
        except ValueError:
            literal_ip = None
        if literal_ip is not None and literal_ip.version == 6:
            protocol = "https" if use_ssl else "http"
            return urlunparse((protocol, f"[{host}]", "", "", "", ""))

        try:
            parsed_host = urlparse(f"//{host}")
        except ValueError as err:
            msg = f"Invalid hostname format: {host}"
            raise ValueError(msg) from err

        if parsed_host.username or parsed_host.password:
            msg = f"Invalid hostname format: {host}"
            raise ValueError(msg)
        if parsed_host.path or parsed_host.query or parsed_host.fragment:
            msg = f"Invalid hostname format: {host}"
            raise ValueError(msg)

        hostname = parsed_host.hostname
        if not hostname:
            msg = f"Invalid hostname format: {host}"
            raise ValueError(msg)

        try:
            port = parsed_host.port
        except ValueError as err:
            msg = f"Invalid port in hostname: {host}"
            raise ValueError(msg) from err

        if port is not None and not 1 <= port <= 65535:
            msg = f"Invalid port in hostname: {host}"
            raise ValueError(msg)

        try:
            ipaddress.ip_address(hostname)
            is_ip_literal = True
        except ValueError:
            is_ip_literal = False

        if not is_ip_literal and not re.match(r"^[a-zA-Z0-9.-]+$", hostname):
            msg = f"Invalid hostname format: {host}"
            raise ValueError(msg)

        # Additional validation
        if len(hostname) > _MAX_HOSTNAME_LENGTH or ".." in hostname or "//" in host:
            msg = f"Invalid hostname: {host}"
            raise ValueError(msg)

        netloc = f"[{hostname}]" if ":" in hostname else hostname
        if port is not None:
            netloc = f"{netloc}:{port}"

        protocol = "https" if use_ssl else "http"
        return urlunparse((protocol, netloc, "", "", "", ""))

    def _build_url(self, endpoint: str) -> str:
        """Construct the full URL for a given endpoint.

        Args:
            endpoint: The API endpoint.

        Returns:
            The full URL.

        """
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        return f"{self._base_url}{endpoint}"

    async def _request(  # noqa: C901, PLR0913
        self,
        endpoint: str,
        *,
        method: str = "GET",
        params: Mapping[str, Any] | None = None,
        query: str | None = None,
        json_payload: Any | None = None,  # noqa: ANN401
        data: Any | None = None,  # noqa: ANN401
        expect_json: bool = False,
        priority: int = API_PRIORITY_NORMAL,
        retryable: bool | None = None,
    ) -> Any:  # noqa: ANN401
        """Perform a request with rate limiting, retries, and error handling.

        This method automatically waits if the request limit is reached.

        Args:
            endpoint: The API endpoint to request.
            method: The HTTP method to use.
            params: A mapping of URL parameters.
            query: A raw query string.
            json_payload: The JSON payload for POST requests.
            expect_json: Whether to expect a JSON response.
            priority: The request priority for rate limiting.
            retryable: Override whether transient failures may be retried.

        Returns:
            The API response, either as JSON or text.

        Raises:
            VioletPoolAPIError: If the API returns an error or the request fails.

        """
        if params and query:
            msg = "'params' and 'query' are mutually exclusive"
            raise ValueError(msg)

        async def _execute_request() -> Any:  # noqa: ANN401
            # Wait if the rate limit is reached
            try:
                await self._rate_limiter.wait_if_needed(priority=priority, timeout=10.0)
            except TimeoutError:
                _LOGGER.warning(
                    "Rate limiter timeout for %s (priority: %d) - applying fallback delay",
                    endpoint,
                    priority,
                )
                await asyncio.sleep(1.0)

            url = self._build_url(endpoint)
            if query:
                url = f"{url}?{query}"

            method_upper = method.upper()
            should_retry = retryable if retryable is not None else method_upper in {"GET", "HEAD"}
            attempt_limit = self._max_retries if should_retry else 1

            for attempt in range(1, attempt_limit + 1):
                try:
                    async with self._session.request(
                        method,
                        url,
                        params=params,
                        json=json_payload,
                        data=data,
                        headers=self._headers or None,
                        timeout=self._timeout,
                        ssl=self._ssl_param,
                    ) as response:
                        if (
                            response.status >= _HTTP_SERVER_ERROR
                            or response.status == _HTTP_TOO_MANY_REQUESTS
                        ):
                            # Server error or rate limit
                            # -> trigger retry via ClientError
                            response.raise_for_status()

                        if (
                            response.status >= _HTTP_CLIENT_ERROR
                            and response.status < _HTTP_SERVER_ERROR
                        ):
                            body = await response.text()
                            msg = f"HTTP {response.status} for {endpoint}: {body.strip()}"
                            is_auth = response.status in (
                                _HTTP_UNAUTHORIZED,
                                _HTTP_FORBIDDEN,
                            )
                            raise DeterministicClientError(msg, is_auth=is_auth)

                        if expect_json:
                            body_text = await response.text()
                            try:
                                return json.loads(body_text)
                            except (
                                json.JSONDecodeError,
                            ) as err:
                                msg = f"Invalid JSON payload for {endpoint}: {body_text.strip()}"
                                raise VioletPayloadError(msg) from err

                        return await response.text()

                except (TimeoutError,) as err:
                    timeout_error = VioletTimeoutError(
                        f"Request to {endpoint} timed out: {err}",
                    )
                    _LOGGER.debug(
                        "Attempt %d for %s timed out: %s",
                        attempt,
                        endpoint,
                        err,
                    )
                    if attempt == attempt_limit:
                        raise timeout_error from None
                    delay = min(30.0, 1.0 * (2 ** (attempt - 1)))
                    jitter = random.uniform(0, delay * 0.1)  # nosec B311
                    await asyncio.sleep(delay + jitter)
                except aiohttp.ClientError as err:
                    client_error = VioletPoolAPIError(
                        f"Error communicating with Violet controller: {err}",
                    )
                    _LOGGER.debug(
                        "Attempt %d for %s failed: %s",
                        attempt,
                        endpoint,
                        err,
                    )
                    if attempt == attempt_limit:
                        raise client_error from None
                    headers = err.headers if isinstance(err, aiohttp.ClientResponseError) else None
                    retry_after = headers.get("Retry-After") if headers else None
                    try:
                        parsed_retry_after = (
                            float(retry_after) if retry_after is not None else 0.0
                        )
                    except ValueError:
                        parsed_retry_after = 0.0
                    if math.isfinite(parsed_retry_after) and parsed_retry_after > 0:
                        delay = min(30.0, parsed_retry_after)
                    else:
                        delay = 0.0
                    if delay <= 0:
                        delay = min(30.0, 1.0 * (2 ** (attempt - 1)))
                    jitter = random.uniform(0, delay * 0.1)  # nosec B311
                    await asyncio.sleep(delay + jitter)

            msg = "All retry attempts exhausted"
            raise VioletPoolAPIError(msg)

        try:
            return await self._circuit_breaker.call(_execute_request)
        except DeterministicClientError as err:
            if err.is_auth:
                raise VioletAuthError(str(err)) from err
            raise VioletPoolAPIError(str(err)) from err
        except CircuitBreakerOpenError as err:
            msg = "Circuit breaker is open due to repeated communication failures"
            raise VioletPoolAPIError(
                msg,
            ) from err

    @staticmethod
    def _command_result(body: str | dict[str, Any]) -> dict[str, Any]:
        """Normalize the controller's response for command-style requests.

        The controller responds with up to 4 lines of text/plain:
          Line 1: OK or ERROR
          Line 2: Output name (e.g. PUMP, DOS_1_CL)
          Line 3+: Status message

        For dosing: MANDOS_STARTED\\nOK or MANDOS_STOPPED\\nOK

        Args:
            body: The raw response body or dict.

        Returns:
            A dictionary with success status, response text, and optional
            parsed output/message fields.

        """
        if isinstance(body, dict):
            return body

        text = (body or "").strip()
        lines = text.splitlines() if text else []
        first_line = lines[0].strip().upper() if lines else ""

        # Manual section 26.2: line 1 of the response is "OK" or "ERROR".
        # Dosing responses use "MANDOS_STARTED\nOK" instead, so fall back to
        # a substring check when the first line is neither marker.
        if first_line.startswith("ERROR"):
            success = False
        elif first_line == "OK" or first_line.startswith("MANDOS_"):
            success = True
        else:
            success = False

        result: dict[str, Any] = {"success": success, "response": text}
        if len(lines) >= 2:
            result["output"] = lines[1].strip()
        if len(lines) >= 3:
            result["message"] = "\n".join(line.strip() for line in lines[2:])

        return result

    def _build_manual_command(
        self,
        key: str,
        action: str,
        *,
        duration: float | None = None,
        last_value: float | None = None,
    ) -> str:
        """Render the command payload based on the device parameter template.

        Args:
            key: The device key.
            action: The action to perform (e.g., ON, OFF).
            duration: The duration for the action.
            last_value: The last value (e.g., speed).

        Returns:
            The formatted command payload.

        Raises:
            VioletPoolAPIError: If the template is misconfigured.

        """
        template = cast(
            "str",
            DEVICE_PARAMETERS.get(key, {}).get(
                "api_template",
                f"{key},{{action}},{{duration}},{{value}}",
            ),
        )
        payload_data = {
            "action": action,
            "duration": int(duration or 0),
            "speed": int(last_value or 0),
            "value": int(last_value or 0),
        }
        try:
            return template.format_map(payload_data)
        except KeyError as err:
            msg = f"Template for {key} requires missing field: {err.args[0]}"
            raise VioletPoolAPIError(
                msg,
            ) from err

    @staticmethod
    def _csv_query_from_values(values: Iterable[str], *, field_name: str) -> str:
        """Build a comma-separated query string from a collection of values."""
        query = ",".join([v for value in values if (v := value.strip())])
        if not query:
            msg = f"No valid {field_name} provided"
            raise VioletPoolAPIError(msg)
        return query

    async def _request_json_dict(
        self,
        endpoint: str,
        *,
        params: Mapping[str, Any] | None = None,
        query: str | None = None,
        payload_name: str,
    ) -> dict[str, Any]:
        """Request JSON content and enforce a dictionary response shape."""
        response = await self._request(
            endpoint,
            params=params,
            query=query,
            expect_json=True,
        )
        if not isinstance(response, dict):
            msg = f"Unexpected payload returned from {payload_name}"
            raise VioletPoolAPIError(
                msg,
            )
        return response

    def _sanitize_config_payload(self, config: Mapping[str, Any]) -> dict[str, Any]:
        """Sanitize and validate configuration payload before POSTing it."""
        sanitized_config: dict[str, str | int | float] = {}

        for key, value in config.items():
            try:
                sanitized_key = InputSanitizer.validate_api_parameter(str(key))
                sanitized_value: str | int | float

                if isinstance(value, str):
                    sanitized_value = InputSanitizer.sanitize_string(
                        value,
                        max_length=1000,
                        allow_special_chars=True,
                        escape_html=False,
                    )
                elif isinstance(value, (int, float)):
                    sanitized_value = InputSanitizer.sanitize_numeric(value)
                else:
                    sanitized_value = InputSanitizer.sanitize_string(str(value))

                sanitized_config[sanitized_key] = sanitized_value
            except ValueError as err:
                _LOGGER.warning("Invalid config parameter %s", key)
                msg = f"Invalid configuration parameter: {key}"
                raise VioletPoolAPIError(
                    msg,
                ) from err

        return sanitized_config

    def _is_base_module_function(self, key: str) -> bool:
        """Return True if the function depends on the base module."""
        normalized = (key or "").strip().upper()
        if not normalized:
            return False

        if normalized.startswith("DOS_"):
            return False

        if normalized.startswith(("EXT", "DMX_SCENE", "DIRULE_", "OMNI_DC")):
            return True

        return normalized in {
            "PUMP",
            "SOLAR",
            "HEATER",
            "LIGHT",
            "ECO",
            "BACKWASH",
            "BACKWASHRINSE",
            "REFILL",
            "PVSURPLUS",
        }

    # ---------------------------------------------------------------------
    # Public API surface
    # ---------------------------------------------------------------------


    async def get_config(
        self,
        parameters: list[str] | tuple[str, ...],
    ) -> dict[str, Any]:
        """Fetch controller configuration values for the provided keys.

        Args:
            parameters: A list or tuple of configuration keys to fetch.

        Returns:
            A dictionary containing the configuration values.

        Raises:
            VioletPoolAPIError: If no keys are provided or the payload is unexpected.

        """
        if not parameters:
            msg = "At least one configuration key is required"
            raise VioletPoolAPIError(msg)

        query = self._csv_query_from_values(
            parameters,
            field_name="configuration keys",
        )
        return await self._request_json_dict(
            API_GET_CONFIG,
            query=query,
            payload_name="getConfig",
        )

    async def set_config(self, config: Mapping[str, Any]) -> dict[str, Any]:
        """Update controller configuration values.

        Args:
            config: A mapping of configuration keys and values to update.

        Returns:
            A dictionary with command result.

        Raises:
            VioletPoolAPIError: If configuration payload is empty.

        """
        if not config:
            msg = "Configuration payload must not be empty"
            raise VioletPoolAPIError(msg)

        sanitized_config = self._sanitize_config_payload(config)

        body = await self._request(
            API_SET_CONFIG,
            method="POST",
            data=sanitized_config,
            retryable=True,
        )
        return self._command_result(body)

    async def get_calibration_raw_values(self) -> dict[str, Any]:
        """Return the current raw values for all calibration sensors.

        Returns:
            A dictionary containing raw calibration values.

        Raises:
            VioletPoolAPIError: If the payload is unexpected.

        """
        return await self._request_json_dict(
            API_GET_CALIB_RAW_VALUES,
            payload_name="getCalibRawValues",
        )

    async def get_calibration_history(self, sensor: str) -> list[dict[str, str]]:
        """Return the calibration history for the provided sensor.

        Args:
            sensor: The name of the sensor.

        Returns:
            A list of dictionaries representing the history entries.

        Raises:
            VioletPoolAPIError: If the sensor name is missing.

        """
        if not sensor:
            msg = "Sensor name required for calibration history"
            raise VioletPoolAPIError(msg)

        response = await self._request(
            API_GET_CALIB_HISTORY,
            query=sensor,
            expect_json=False,
        )

        entries: list[dict[str, str]] = []
        for line in (response or "").strip().splitlines():
            try:
                parts = [part.strip() for part in line.split("|")]
                if len(parts) >= _MIN_CALIB_HISTORY_PARTS:
                    entries.append(
                        {
                            "timestamp": parts[0],
                            "value": parts[1],
                            "type": parts[2],
                        },
                    )
                else:
                    _LOGGER.warning(
                        "Skipping malformed calibration history line: %s",
                        line,
                    )
            except (IndexError, AttributeError) as err:
                err_msg = str(err) or type(err).__name__
                _LOGGER.warning(
                    "Error parsing calibration history line '%s': %s",
                    line,
                    err_msg,
                )
        return entries

    async def restore_calibration(self, sensor: str, timestamp: str) -> dict[str, Any]:
        """Restore a previous calibration entry for the given sensor.

        Args:
            sensor: The name of the sensor.
            timestamp: The timestamp of the calibration to restore.

        Returns:
            A dictionary with the command result.

        Raises:
            VioletPoolAPIError: If the sensor or timestamp is missing.

        """
        if not sensor or not timestamp:
            msg = "Sensor and timestamp are required for calibration restore"
            raise VioletPoolAPIError(
                msg,
            )

        body = await self._request(
            API_RESTORE_CALIBRATION,
            method="POST",
            data={"sensor": sensor, "timestamp": timestamp},
        )
        return self._command_result(body)
