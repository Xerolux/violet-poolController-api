"""Internal notifications, logs, services, diagnostics, and updates."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from ._api_mixin import APIClientMixin
from ._api_model import VioletPoolAPIError
from .const_api import (
    API_GET_LIVE_TRACE,
    API_GET_LOG,
    API_GET_NOTIFICATIONS,
    API_GET_SERVICE_STATES,
    API_GET_UPDATE_HISTORY,
    API_GET_UPDATE_STATE,
    API_INIT_UPDATE,
    API_PRIORITY_CRITICAL,
    API_PRIORITY_NORMAL,
    API_RESET_BLOCKING,
    ERROR_CODES,
    ERROR_SEVERITY_ALARM,
    ERROR_SEVERITY_INFO,
    ERROR_SEVERITY_REMINDER,
    ERROR_SEVERITY_WARNING,
    LOG_TYPE_ACTIONS,
    LOG_TYPES,
    SYSTEM_SERVICES,
)

_LOGGER = logging.getLogger(__name__)

class SystemMixin(APIClientMixin):
    """Notifications, logs, services, diagnostics, and updates."""

    @staticmethod
    def parse_error_notification(
        error_code: str,
        subject: str | None = None,
    ) -> dict[str, Any]:
        """Parse an error notification received from the controller.

        The controller sends outbound HTTP requests with ERRORCODE and SUBJECT
        fields when warnings/alarms occur.  This method decodes them into a
        structured dict suitable for display as a sensor entity.

        Args:
            error_code: The 4-digit error code string (e.g. "0020").
            subject: The SUBJECT field from the controller (optional fallback).

        Returns:
            A dict with keys: code, severity, message, is_alarm, is_warning,
            is_info, is_reminder.

        """
        code = str(error_code).strip()
        if not code:
            return {"code": "0000", "severity": "UNKNOWN", "message": "Invalid empty error code"}
        code = code.zfill(4)
        info = ERROR_CODES.get(code)

        if info:
            severity = info["severity"]
            message = info["message"]
        else:
            severity = ERROR_SEVERITY_WARNING
            message = subject or f"Unbekannter Fehlercode {code}"

        return {
            "code": code,
            "severity": severity,
            "message": message,
            "is_alarm": severity == ERROR_SEVERITY_ALARM,
            "is_warning": severity == ERROR_SEVERITY_WARNING,
            "is_info": severity == ERROR_SEVERITY_INFO,
            "is_reminder": severity == ERROR_SEVERITY_REMINDER,
        }

    @staticmethod
    def parse_multiple_errors(
        error_data: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Parse multiple error codes from a notification payload.

        Handles payloads where ERRORCODE may contain multiple comma-separated
        codes or where multiple error fields are present.

        Args:
            error_data: The full notification payload dict.

        Returns:
            A list of parsed error dicts.

        """
        results: list[dict[str, Any]] = []
        raw_code = str(error_data.get("ERRORCODE", ""))
        subject = str(error_data.get("SUBJECT", ""))

        if not raw_code or raw_code == "0":
            return results

        for code in raw_code.split(","):
            code = code.strip()
            if code and code != "0":
                results.append(
                    SystemMixin.parse_error_notification(code, subject),
                )

        return results

    async def get_log(
        self,
        log_type: str,
        page: int = 0,
    ) -> dict[str, Any]:
        """Fetch log entries from the controller.

        Args:
            log_type: One of ``LOG_TYPE_ACTIONS``, ``LOG_TYPE_SWITCHING``,
                ``LOG_TYPE_ONEWIRE`` (``"actions"``, ``"switching"``,
                ``"onewire"``).
            page: Page number (0-based). Use -1 to download the full
                actions log instead of paginated text.

        Returns:
            A dict with keys:
            - ``lines``: list of pipe-delimited log line strings
            - ``has_more``: True when ``LOAD_MORE`` sentinel was present
            - ``raw``: the raw text response

        Raises:
            VioletPoolAPIError: If ``log_type`` is not one of the supported
                values or the request fails.

        """
        normalized = (log_type or "").strip()
        if normalized not in LOG_TYPES:
            msg = (
                f"Unsupported log_type {log_type!r}. "
                f"Expected one of: {sorted(LOG_TYPES)}"
            )
            raise VioletPoolAPIError(msg)

        if page < 0 and normalized == LOG_TYPE_ACTIONS:
            query = "downloadActionsLog"
        else:
            query = f"{normalized}&{int(page)}"

        resp = await self._request(
            API_GET_LOG,
            query=query,
            priority=API_PRIORITY_NORMAL,
        )
        text = resp.strip() if resp else ""
        lines = text.split("\n") if text else []
        has_more = lines and lines[-1].strip() == "LOAD_MORE"
        if has_more:
            lines = lines[:-1]
        lines = [ln for ln in lines if ln.strip()]
        return {"lines": lines, "has_more": has_more, "raw": text}

    async def get_notifications(self) -> dict[str, Any]:
        """Fetch all notification history from the controller.

        Returns:
            The JSON response dict where each key is a numeric ID and each
            value is a notification record with fields like DATE, TIME,
            SENSOR_ID, TYPE, TEXT, MAIL_STATE, etc.

        """
        return await self._request_json_dict(
            API_GET_NOTIFICATIONS,
            query="ALL",
            payload_name="getNotifications",
        )

    async def reset_blocking(self) -> dict[str, Any]:
        """Clear fault-induced blockings on the controller.

        Clears the ``BLOCKED_BY_ESC`` flag raised by empty-canister alarms
        and similar fault states so that dosing/control resumes after the
        underlying issue has been fixed (e.g. after refilling a canister).
        Equivalent to clicking "Reset" on the controller's web UI error page.

        Returns:
            A dict with the command result (``success`` flag and ``response``
            text from the controller).

        Raises:
            VioletPoolAPIError: If the API request fails.

        """
        body = await self._request(
            API_RESET_BLOCKING,
            method="GET",
            priority=API_PRIORITY_CRITICAL,
        )
        return self._command_result(body)

    async def set_system_service(
        self,
        service: str,
        enabled: bool,
    ) -> dict[str, Any]:
        """Enable or disable a controller-side system service.

        The controller exposes per-service ``/enable*`` and ``/disable*``
        endpoints (FTP, Samba, SSH, Shairport/AirPlay, Homebridge/HomeKit,
        Alexa, cloud tunnel, support tunnel).  State can be queried via
        :meth:`get_system_services`.

        Args:
            service: One of the keys in
                :data:`~violet_poolcontroller_api.const_api.SYSTEM_SERVICES`
                (``"ftp"``, ``"samba"``, ``"ssh"``, ``"shairport"``,
                ``"homebridge"``, ``"alexa"``, ``"tunnel"``,
                ``"support_tunnel"``).
            enabled: True to enable, False to disable.

        Returns:
            A dict with the command result.

        Raises:
            VioletPoolAPIError: If ``service`` is unknown or the request fails.

        """
        info = SYSTEM_SERVICES.get(service)
        if info is None:
            msg = (
                f"Unknown system service: {service!r}. "
                f"Expected one of: {sorted(SYSTEM_SERVICES)}"
            )
            raise VioletPoolAPIError(msg)

        endpoint = info["enable_endpoint"] if enabled else info["disable_endpoint"]
        body = await self._request(
            endpoint,
            method="GET",
            priority=API_PRIORITY_CRITICAL,
        )
        return self._command_result(body)

    async def get_system_services(self) -> dict[str, bool]:
        """Return the live state of all controller-side system services.

        Wraps ``GET /getServiceStates`` and normalises each value to a
        boolean.  Services whose state is not reported by the controller
        (currently only Alexa) are absent from the returned dict.

        Returns:
            A dict mapping service key (``"ftp"``, ``"samba"``, ...) to a
            boolean enabled state.

        Raises:
            VioletPoolAPIError: If the request fails or the payload is
                missing the expected keys.

        """
        raw = await self._request_json_dict(
            API_GET_SERVICE_STATES,
            payload_name="getServiceStates",
        )

        result: dict[str, bool] = {}
        for service, info in SYSTEM_SERVICES.items():
            state_key = info.get("state_key", "")
            if not state_key:
                continue
            if state_key in raw:
                result[service] = bool(int(raw[state_key]))
        return result

    async def get_live_trace(self) -> dict[str, str]:
        """Return a single-row snapshot of every controller reading.

        Wraps ``GET /getLiveTrace``.  The controller returns a 3-line
        text/plain body (header row, units row, values row) with
        semicolon-separated fields and German decimal commas.  This method
        splits the rows and zips header→value into a dict (parsing values
        as ``float`` when possible, falling back to the raw string).

        Useful for ad-hoc troubleshooting dashboards – the controller does
        not document this endpoint as stable, so prefer the typed
        :meth:`get_readings` for production use.

        Returns:
            A dict mapping the header field names to their current values.

        Raises:
            VioletPoolAPIError: If the request fails or the payload is
                malformed.

        """
        body = await self._request(
            API_GET_LIVE_TRACE,
            method="GET",
            priority=API_PRIORITY_NORMAL,
        )
        text = str(body) if body is not None else ""
        lines = text.splitlines()
        if len(lines) < 3:
            msg = f"Malformed getLiveTrace payload: expected 3 lines, got {len(lines)}"
            raise VioletPoolAPIError(msg)
        header = lines[0].split(";")
        values = lines[2].split(";")
        result: dict[str, str] = {}
        if len(header) != len(values):
            _LOGGER.warning("Live trace header/value length mismatch: %d vs %d", len(header), len(values))
        for key, raw_value in zip(header, values):
            key = key.strip()
            if not key:
                continue
            result[key] = raw_value.replace(",", ".").strip()
        return result

    async def init_update(self) -> str:
        """Trigger firmware update installation on the controller.

        The controller downloads and installs the update, then restarts
        (takes ~30 seconds). Returns "STARTING" on success.

        Returns:
            Response string from the controller (e.g. "STARTING").

        Raises:
            VioletPoolAPIError: If the API call fails or auth is rejected.

        """
        resp = await self._request(
            API_INIT_UPDATE,
            method="GET",
            priority=API_PRIORITY_CRITICAL,
        )
        return str(resp).strip() if resp else ""

    async def get_update_state(self) -> str:
        """Fetch the current firmware update progress log.

        The controller writes progress to /home/violet/log/update.log
        during an active update. Returns "STANDBY" when no update is running.

        Returns:
            Raw update log string or "STANDBY".

        Raises:
            VioletPoolAPIError: If the API call fails.

        """
        resp = await self._request(
            API_GET_UPDATE_STATE,
            method="GET",
            priority=API_PRIORITY_NORMAL,
        )
        return str(resp).strip() if resp else "STANDBY"

    async def get_update_history(self) -> str:
        """Fetch formatted release notes for recent firmware versions.

        The controller fetches notes from the PoolDigital update server and
        returns them pre-formatted with HTML bullet points.

        Returns:
            HTML-formatted release notes string, or empty string on error.

        Raises:
            VioletPoolAPIError: If the API call fails.

        """
        resp = await self._request(
            API_GET_UPDATE_HISTORY,
            method="GET",
            priority=API_PRIORITY_NORMAL,
        )
        return str(resp).strip() if resp else ""
