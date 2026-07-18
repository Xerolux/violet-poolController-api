"""Internal chemical dosing and setpoint operations."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from ._api_mixin import APIClientMixin
from ._api_model import (
    VioletPayloadError,
    VioletPoolAPIError,
    validate_duration,
    validate_setpoint,
)
from .const_api import (
    ACTION_OFF,
    ACTION_ON,
    API_GET_CONFIG,
    API_PRIORITY_CRITICAL,
    API_SET_CAN_AMOUNT,
    API_TRIGGER_MANUAL_DOSING,
    DOSING_CANISTER_ID,
    DOSING_CONFIG_PREFIX,
    DOSING_FUNCTIONS,
    DOSING_OUTPUT_INDEX,
    TARGET_MIN_CHLORINE,
    TARGET_ORP,
    TARGET_PH,
)


class DosingMixin(APIClientMixin):
    """Chemical dosing and setpoint operations."""

    async def _trigger_dosing(
        self,
        key: str,
        action: str,
        *,
        duration: int | None = None,
    ) -> dict[str, Any]:
        """Trigger or stop a manual dosing run via /triggerManualDosing.

        setFunctionManually does not work for dosing outputs (confirmed by
        PoolDigital in the support forum): neither ON nor AUTO has any
        effect there. Starting AND stopping a manual dosing run must both
        go through /triggerManualDosing.

        Args:
            key: The dosing pump key (e.g. DOS_6_FLOC).
            action: ON/START → DOSSTART; OFF/STOP/AUTO → DOSSTOP
                (stopping a run returns the channel to automatic mode).
            duration: Duration in seconds (whole number).

        Returns:
            A dictionary with the command result.

        Raises:
            VioletPoolAPIError: If the dosing key or action is unknown.

        """
        output_index = DOSING_OUTPUT_INDEX.get(key)
        if output_index is None:
            msg = f"Unknown dosing output key: {key}"
            raise VioletPoolAPIError(msg)

        action_upper = action.strip().upper()
        if action_upper in ("OFF", "STOP", "AUTO", "DOSSTOP"):
            dos_action = "DOSSTOP"
        elif action_upper in ("ON", "START", "DOSSTART"):
            dos_action = "DOSSTART"
        else:
            # Never default to DOSSTART: an unexpected action must not
            # start a chemical dosing run.
            msg = f"Unsupported dosing action for {key}: {action}"
            raise VioletPoolAPIError(msg)

        if dos_action == "DOSSTART":
            if duration is None:
                msg = f"A positive duration is required to start dosing output {key}"
                raise VioletPoolAPIError(msg)
            dos_duration = validate_duration(duration, minimum=1)
        else:
            dos_duration = 0

        form_data = {
            "action": dos_action,
            "output": str(output_index),
            "runtime": str(dos_duration),
            "from": "1",
            "runtime_formatted": f"{dos_duration // 60:02d}:{dos_duration % 60:02d}",
        }
        body = await self._request(
            API_TRIGGER_MANUAL_DOSING,
            method="POST",
            data=form_data,
            priority=API_PRIORITY_CRITICAL,
        )
        return self._command_result(body)

    async def manual_dosing(self, dosing_type: str, duration: int) -> dict[str, Any]:
        """Trigger a dosing run using the manual function endpoint.

        Args:
            dosing_type: The type of dosing (e.g., "Chlor").
            duration: The duration in seconds.

        Returns:
            A dictionary with the command result.

        Raises:
            VioletPoolAPIError: If the dosing type is unknown.

        """
        device_key = DOSING_FUNCTIONS.get(dosing_type)
        if not device_key:
            msg = f"Unknown dosing type: {dosing_type}"
            raise VioletPoolAPIError(msg)

        # /triggerManualDosing requires an explicit runtime; duration <= 0
        # stops a running manual dosing instead (documented behavior).
        if duration <= 0:
            return await self.set_switch_state(device_key, ACTION_OFF)

        return await self.set_switch_state(
            device_key,
            ACTION_ON,
            duration=duration,
        )

    async def set_ph_target(self, value: float) -> dict[str, Any]:
        """Update the pH setpoint.

        Args:
            value: The new pH target value (valid range: 6.0–8.0).

        Returns:
            A dictionary with the command result.

        Raises:
            VioletSetpointError: If ``value`` is outside the valid range or
                is not a finite number.

        """
        validate_setpoint(TARGET_PH, float(value))
        return await self.set_target_value(TARGET_PH, float(value))

    async def set_orp_target(self, value: int) -> dict[str, Any]:
        """Update the ORP setpoint.

        Args:
            value: The new ORP target value in mV (valid range: 500–900).

        Returns:
            A dictionary with the command result.

        Raises:
            VioletSetpointError: If ``value`` is outside the valid range or
                is not a finite number.

        """
        validate_setpoint(TARGET_ORP, float(value))
        return await self.set_target_value(TARGET_ORP, int(value))

    async def set_min_chlorine_level(self, value: float) -> dict[str, Any]:
        """Update the minimum chlorine level.

        Args:
            value: The new minimum chlorine level in mg/L (valid range: 0.0–5.0).

        Returns:
            A dictionary with the command result.

        Raises:
            VioletSetpointError: If ``value`` is outside the valid range or
                is not a finite number.

        """
        validate_setpoint(TARGET_MIN_CHLORINE, float(value))
        return await self.set_target_value(TARGET_MIN_CHLORINE, float(value))

    async def set_target_value(self, key: str, value: float) -> dict[str, Any]:
        """Send a generic target value update to the controller.

        For known setpoint keys (see ``SETPOINT_RANGES``), validation is
        performed automatically.  Call ``validate_setpoint()`` directly for
        keys not covered by the convenience methods.

        Args:
            key: The target key.
            value: The new value.

        Returns:
            A dictionary with the command result.

        Raises:
            VioletSetpointError: If ``value`` is non-finite or outside a
                known valid range for ``key``.

        """
        validate_setpoint(key, float(value))
        return await self.set_config({key: value})

    async def set_dosing_parameters(
        self,
        parameters: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Update dosing parameters via /setConfig.

        The /setDosingParameters endpoint does not exist on the controller
        (firmware 1.1.9). All dosing parameters are written through
        POST /setConfig, just like other configuration values.

        Args:
            parameters: A mapping of dosing parameters.

        Returns:
            A dictionary with the command result.

        """
        return await self.set_config(dict(parameters))

    async def set_dosage_enabled(
        self,
        dosing_type: str,
        enabled: bool,
    ) -> dict[str, Any]:
        """Enable or disable a dosing function.

        Args:
            dosing_type: One of ``"pH-"``, ``"pH+"``, ``"Chlor"``,
                ``"Elektrolyse"``, ``"Flockmittel"``, ``"H2O2"``.
            enabled: True to enable, False to disable.

        Returns:
            A dictionary with the command result.

        Raises:
            VioletPoolAPIError: If the dosing type is unknown.

        """
        prefix = DOSING_CONFIG_PREFIX.get(dosing_type)
        if prefix is None:
            msg = f"Unknown dosing type '{dosing_type}'. Valid: {list(DOSING_CONFIG_PREFIX)}"
            raise VioletPoolAPIError(msg)

        return await self.set_config({f"{prefix}_use": 1 if enabled else 0})

    async def is_dosage_enabled(self, dosing_type: str) -> bool:
        """Check whether a dosing function is enabled.

        Args:
            dosing_type: One of ``"pH-"``, ``"pH+"``, ``"Chlor"``,
                ``"Elektrolyse"``, ``"Flockmittel"``, ``"H2O2"``.

        Returns:
            True if the dosing function is enabled.

        Raises:
            VioletPoolAPIError: If the dosing type is unknown.

        """
        prefix = DOSING_CONFIG_PREFIX.get(dosing_type)
        if prefix is None:
            msg = f"Unknown dosing type '{dosing_type}'. Valid: {list(DOSING_CONFIG_PREFIX)}"
            raise VioletPoolAPIError(msg)

        result = await self._request_json_dict(
            API_GET_CONFIG,
            query=f"{prefix}_use",
            payload_name="getConfig",
        )
        raw_value = result.get(f"{prefix}_use", 0)
        try:
            return bool(int(float(raw_value)))
        except (TypeError, ValueError, OverflowError) as err:
            msg = f"Invalid dosage enabled state for {dosing_type}: {raw_value!r}"
            raise VioletPayloadError(msg) from err

    async def set_can_amount(
        self,
        dosing_key: str,
        amount_ml: int,
        *,
        reset: bool = False,
    ) -> dict[str, Any]:
        """Set or reset the canister fill level for a dosing channel.

        Used after refilling or replacing a chemical canister so the
        controller's remaining-range calculation is accurate.

        Args:
            dosing_key: One of ``DOS_1_CL``, ``DOS_2_ELO``, ``DOS_4_PHM``,
                ``DOS_5_PHP``, ``DOS_6_FLOC``.  H2O2 shares ``DOS_1_CL``
                with Chlorine and is not a separate key here.
            amount_ml: New fill level in millilitres (must be > 0).
            reset: When True, also resets the daily-dosing counter and the
                "last can reset" timestamp (firmware action ``RESET``).
                When False (default), only adjusts the fill level
                (firmware action ``ADJUST``) and leaves the daily counter
                untouched.

        Returns:
            A dict with the command result.

        Raises:
            VioletPoolAPIError: If ``dosing_key`` is unknown or the API
                request fails.
            ValueError: If ``amount_ml`` is not positive.

        """
        cid = DOSING_CANISTER_ID.get(dosing_key)
        if cid is None:
            msg = (
                f"Unknown dosing key for set_can_amount: {dosing_key!r}. "
                f"Expected one of: {sorted(DOSING_CANISTER_ID)}"
            )
            raise VioletPoolAPIError(msg)
        if amount_ml <= 0:
            raise ValueError(f"amount_ml must be > 0, got {amount_ml}")

        action = "RESET" if reset else "ADJUST"
        form_data = {
            "action": action,
            "which": dosing_key,
            "amount": str(int(amount_ml)),
            "cid": str(cid),
        }
        body = await self._request(
            API_SET_CAN_AMOUNT,
            method="POST",
            data=form_data,
            priority=API_PRIORITY_CRITICAL,
        )
        return self._command_result(body)
