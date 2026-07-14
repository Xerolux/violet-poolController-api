"""Internal pump, relay, lighting, cover, valve, and rs485 operations."""

from __future__ import annotations

import logging
import math
from typing import Any
from urllib.parse import quote

from ._api_mixin import APIClientMixin
from ._api_model import VioletPoolAPIError, VioletUnsafeOperationError, validate_duration
from .const_api import (
    ACTION_ALLAUTO,
    ACTION_ALLOFF,
    ACTION_ALLON,
    ACTION_AUTO,
    ACTION_COLOR,
    ACTION_LOCK,
    ACTION_OFF,
    ACTION_ON,
    ACTION_PUSH,
    ACTION_UNLOCK,
    API_GET_RS485_PUMP_DATA,
    API_PRIORITY_CRITICAL,
    API_PRIORITY_NORMAL,
    API_SET_FUNCTION_MANUALLY,
    API_SET_OUTPUT_TESTMODE,
    API_SET_RS485_LIVE,
    OMNI_POSITIONS,
    RS485_PUMP_MODES,
    RS485_PUMP_NAMES,
)
from .const_devices import COVER_FUNCTIONS

_LOGGER = logging.getLogger(__name__)

class OutputsMixin(APIClientMixin):
    """Pump, relay, lighting, cover, valve, and RS485 operations."""

    async def set_output_test_mode(
        self,
        *,
        output: str,
        mode: str = "SWITCH",
        duration: int = 120,
    ) -> dict[str, Any]:
        """Activate the controller's output test mode.

        Args:
            output: The identifier of the output.
            mode: The test mode (default is "SWITCH").
            duration: The duration in seconds (default is 120).

        Returns:
            A dictionary with the command result.

        Raises:
            VioletPoolAPIError: If the output is missing.

        """
        if not output:
            msg = "Output identifier is required"
            raise VioletPoolAPIError(msg)

        duration_ms = validate_duration(duration) * 1000
        payload = f"{output},{mode},{duration_ms}"
        body = await self._request(
            API_SET_OUTPUT_TESTMODE,
            query=payload,
        )
        return self._command_result(body)

    async def set_switch_state(
        self,
        key: str,
        action: str,
        *,
        duration: float | None = None,
        last_value: float | None = None,
    ) -> dict[str, Any]:
        """Control a function output.

        Uses /triggerManualDosing for dosing pumps (DOS_*) and
        /setFunctionManually for all other functions.

        Args:
            key: The device key.
            action: The action to perform (e.g., ON, OFF, AUTO).
            duration: An optional duration for the action.
            last_value: An optional last value (e.g., speed).

        Returns:
            A dictionary with the command result.

        """
        if duration is not None:
            duration = validate_duration(duration)

        if self._dosing_standalone and self._is_base_module_function(key):
            msg = (
                f"Function '{key}' requires the Violet base module and is not "
                "available in dosing-standalone mode"
            )
            raise VioletPoolAPIError(
                msg,
            )

        if key.startswith("DOS_"):
            return await self._trigger_dosing(key, action, duration=duration)

        if key == "PVSURPLUS":
            action = self._normalize_pv_surplus_action(action)

        payload = self._build_manual_command(
            key,
            action,
            duration=duration,
            last_value=last_value,
        )
        query = quote(payload, safe=",")
        body = await self._request(API_SET_FUNCTION_MANUALLY, query=query)
        return self._command_result(body)

    @staticmethod
    def _normalize_pv_surplus_action(action: str) -> str:
        """Normalize an action for the PVSURPLUS function.

        Manual section 26.3 only documents ON and OFF for PVSURPLUS; there is
        no AUTO mode (the getReadings PVSURPLUS state is 0/1/2 - off,
        triggered by digital input, or triggered by HTTP).  Sending AUTO is
        therefore mapped to OFF, which releases the HTTP trigger and returns
        control to the configured digital input / controller logic.

        Args:
            action: The requested action.

        Returns:
            The spec-conform action (ON or OFF).

        Raises:
            VioletPoolAPIError: If the action cannot be mapped to ON or OFF.

        """
        normalized = (action or "").strip().upper()
        if normalized == ACTION_AUTO:
            _LOGGER.warning(
                "PVSURPLUS does not support AUTO (manual section 26.3); "
                "sending OFF to release the HTTP trigger instead",
            )
            return ACTION_OFF
        if normalized not in (ACTION_ON, ACTION_OFF):
            msg = (
                f"Unsupported PVSURPLUS action '{action}': "
                "manual section 26.3 only documents ON and OFF"
            )
            raise VioletPoolAPIError(msg)
        return normalized

    async def set_pv_surplus(
        self,
        *,
        active: bool,
        pump_speed: int | None = None,
    ) -> dict[str, Any]:
        """Enable or disable PV surplus mode.

        Per manual section 26.3 the command format is
        ``PVSURPLUS,{ON|OFF},{speed},0`` where the speed (1-3) is only
        evaluated for variable-speed pumps.  If no speed is provided the
        controller falls back to the speed configured in its GUI.

        Args:
            active: Whether to activate PV surplus mode.
            pump_speed: An optional pump speed (1-3).

        Returns:
            A dictionary with the command result.

        """
        speed: int | None = None
        if pump_speed is not None:
            speed = max(1, min(3, int(pump_speed)))
        return await self.set_switch_state(
            "PVSURPLUS",
            ACTION_ON if active else ACTION_OFF,
            last_value=speed,
        )

    async def set_all_dmx_scenes(self, action: str) -> dict[str, Any]:
        """Send a global DMX command that affects all scenes and the LIGHT output.

        The controller treats ALLON/ALLOFF/ALLAUTO as global actions: a single
        request to any DMX_SCENE key switches all 12 scenes and LIGHT at once.

        Args:
            action: The action to perform (ALLON, ALLOFF, ALLAUTO).

        Returns:
            A dictionary with the command result.

        Raises:
            VioletPoolAPIError: If the action is unsupported.

        """
        if action not in {ACTION_ALLON, ACTION_ALLOFF, ACTION_ALLAUTO}:
            msg = f"Unsupported DMX action: {action}"
            raise VioletPoolAPIError(msg)

        return await self.set_switch_state("DMX_SCENE1", action)

    async def set_cover_command(
        self,
        action: str,
        *,
        acknowledge_unsafe: bool = False,
    ) -> dict[str, Any]:
        """Send an open, close, or stop command to the pool cover.

        Cover movement is a potentially hazardous operation (motorised cover,
        risk of entrapment).  Callers must explicitly pass
        ``acknowledge_unsafe=True`` to confirm they are aware of the risk and
        have taken appropriate safety precautions.

        Args:
            action: ``"OPEN"``, ``"CLOSE"``, or ``"STOP"`` (case-insensitive).
            acknowledge_unsafe: Must be ``True`` to allow the command.

        Returns:
            A dictionary with the command result.

        Raises:
            VioletUnsafeOperationError: If ``acknowledge_unsafe`` is ``False``.
            VioletPoolAPIError: If ``action`` is not a known cover action.

        """
        if not acknowledge_unsafe:
            msg = (
                "Cover movement is a potentially unsafe operation. "
                "Pass acknowledge_unsafe=True to confirm you are aware of the risk."
            )
            raise VioletUnsafeOperationError(msg)

        cover_key = COVER_FUNCTIONS.get(action.strip().upper())
        if not cover_key:
            msg = f"Unknown cover action '{action}'. Valid: {list(COVER_FUNCTIONS)}"
            raise VioletPoolAPIError(msg)

        return await self.set_switch_state(cover_key, ACTION_PUSH)

    async def set_light_color_pulse(self) -> dict[str, Any]:
        """Trigger the color pulse animation for the pool light.

        Returns:
            A dictionary with the command result.

        """
        return await self.set_switch_state("LIGHT", ACTION_COLOR)

    async def trigger_digital_input_rule(self, rule_key: str) -> dict[str, Any]:
        """Trigger a digital input rule via a PUSH action.

        Args:
            rule_key: The rule key (e.g., DIRULE_1).

        Returns:
            A dictionary with the command result.

        """
        return await self.set_switch_state(rule_key, ACTION_PUSH)

    async def set_digital_input_rule_lock(
        self,
        rule_key: str,
        *,
        locked: bool,
    ) -> dict[str, Any]:
        """Lock or unlock a digital input rule.

        Args:
            rule_key: The rule key.
            locked: True to lock, False to unlock.

        Returns:
            A dictionary with the command result.

        """
        return await self.set_switch_state(
            rule_key,
            ACTION_LOCK if locked else ACTION_UNLOCK,
        )

    async def set_device_temperature(
        self,
        climate_key: str,
        temperature: float,
    ) -> dict[str, Any]:
        """Set the target temperature for heater or solar circuits.

        Args:
            climate_key: The climate key (HEATER or SOLAR).
            temperature: The target temperature in °C.

        Returns:
            A dictionary with the command result.

        Raises:
            VioletSetpointError: If ``temperature`` is outside the valid range
                (5–45 °C for heater, 5–55 °C for solar).

        """
        normalized_key = climate_key.strip().upper()
        config_keys = {"HEATER": "HEATER_set_temp", "SOLAR": "SOLAR_maxtemp"}
        config_key = config_keys.get(normalized_key)
        if config_key is None:
            msg = f"Unknown climate key {climate_key!r}. Expected HEATER or SOLAR"
            raise VioletPoolAPIError(msg)
        return await self.set_target_value(config_key, float(temperature))

    async def set_pump_speed(
        self,
        speed: int,
        duration: int = 0,
    ) -> dict[str, Any]:
        """Set the pump speed.

        Args:
            speed: The pump speed (1-3, where 1=ECO, 2=Normal, 3=Boost).
            duration: Optional duration in seconds (0 = permanent).

        Returns:
            A dictionary with the command result.

        """
        safe_speed = max(1, min(3, int(speed)))
        safe_duration = validate_duration(duration)

        return await self.set_switch_state(
            key="PUMP",
            action=ACTION_ON,
            duration=safe_duration,
            last_value=safe_speed,
        )

    async def control_pump(
        self,
        action: str,
        speed: int | None = None,
        duration: int = 0,
    ) -> dict[str, Any]:
        """Control the pump with optional speed and duration.

        Args:
            action: The action to perform (ON, OFF, AUTO).
            speed: Optional pump speed (1-3).
            duration: Optional duration in seconds.

        Returns:
            A dictionary with the command result.

        """
        return await self.set_switch_state(
            key="PUMP",
            action=action,
            duration=duration,
            last_value=speed,
        )

    async def set_omni_position(self, position: int) -> dict[str, Any]:
        """Drive the OmniTronic multi-port valve to a fixed position.

        Sends ``setFunctionManually?OMNI,OMNI_DC<N>``.  The controller
        physically rotates the valve; the pump and dependent outputs
        (heater/solar/dosing) are blocked with priority 5 while the valve
        is moving.  Typical change-over is ~3 s per step.

        Position 0 ("Filtration") has a special meaning: it also clears the
        BACKWASH_RULE and releases any manual override, returning the
        controller to automatic mode.  Use it after a manual backwash or
        after positioning the valve at any other port.

        Args:
            position: Valve position (0-5).  0=Filtration/AUTO,
                1-5=other physical ports (backwash, rinse, waste, ... –
                exact meaning depends on the valve's plumbing).

        Returns:
            A dict with the command result.

        Raises:
            VioletPoolAPIError: If ``position`` is out of range or the
                request fails.

        """
        if position not in OMNI_POSITIONS:
            msg = (
                f"Invalid OmniTronic position: {position!r}. "
                f"Must be one of {sorted(OMNI_POSITIONS)}"
            )
            raise VioletPoolAPIError(msg)
        state_token = OMNI_POSITIONS[position]
        url = f"{API_SET_FUNCTION_MANUALLY}?OMNI,{state_token},0,0"
        body = await self._request(
            url,
            method="GET",
            priority=API_PRIORITY_CRITICAL,
        )
        return self._command_result(body)

    async def get_rs485_pump_data(
        self,
        pump_name: str,
    ) -> dict[str, Any]:
        """Return live data and register config for an RS485 pump.

        Wraps ``GET /getRS485PumpData?<pumpName>``.  The response combines
        the static register map from ``config/RS485_PUMP/<NAME>.json`` with
        live values: pump power consumption (Watts), flow rate (depending on
        the configured flow monitor), pump-blocked flag, BACKWASH_STEP and
        a SLAVE_PRESENT flag.

        Args:
            pump_name: Pump model identifier (e.g. ``"BADU_ECO_DRIVE_II"``).
                See :data:`~violet_poolcontroller_api.const_api.RS485_PUMP_NAMES`
                for the known names.

        Returns:
            The full JSON dict returned by the controller.

        Raises:
            VioletPoolAPIError: If ``pump_name`` is unknown or the request
                fails.

        """
        if pump_name not in RS485_PUMP_NAMES:
            msg = (
                f"Unknown RS485 pump name: {pump_name!r}. "
                f"Expected one of {RS485_PUMP_NAMES}"
            )
            raise VioletPoolAPIError(msg)
        url = f"{API_GET_RS485_PUMP_DATA}?{pump_name}"
        body = await self._request(
            url,
            method="GET",
            priority=API_PRIORITY_NORMAL,
            expect_json=True,
        )
        if isinstance(body, dict):
            return body
        return {"raw": body}

    async def set_rs485_live(
        self,
        pump_name: str,
        slave_id: int,
        mode: str,
        level: float,
    ) -> str:
        """Send live control data to an RS485 variable-speed pump.

        Wraps ``GET /setRS485Live?<pumpName>,<slaveID>,<mode>,<level>``.
        While live mode is active the controller blocks its normal RS485
        polling for ~3 s after each call – call :meth:`end_rs485_live`
        when you're done to release the bus.

        Args:
            pump_name: Pump model identifier (see
                :data:`~violet_poolcontroller_api.const_api.RS485_PUMP_NAMES`).
            slave_id: Modbus slave ID of the pump (usually 1).
            mode: Control mode – one of ``"rpm"``, ``"pwr"`` or ``"hz"``.
                Which modes are valid depends on the pump model (most BADU
                pumps expose only ``"hz"`` – check
                ``MOTIONCONTROLMODE_VALIDMODES`` in the pump config).
            level: Target value (RPM, kW, or Hz).  Clamped to the pump's
                ``SETTARGET_*_VALIDMIN`` / ``VALIDMAX`` on the controller.

        Returns:
            The register/value string the controller forwards to the pump's
            modbus interface (e.g. ``"1|0,0|2,4500"``).

        Raises:
            VioletPoolAPIError: If arguments are invalid or the request fails.

        """
        if pump_name not in RS485_PUMP_NAMES:
            msg = (
                f"Unknown RS485 pump name: {pump_name!r}. "
                f"Expected one of {RS485_PUMP_NAMES}"
            )
            raise VioletPoolAPIError(msg)
        if mode.lower() not in RS485_PUMP_MODES:
            msg = (
                f"Invalid RS485 mode: {mode!r}. "
                f"Expected one of {RS485_PUMP_MODES}"
            )
            raise VioletPoolAPIError(msg)
        if slave_id < 1 or slave_id > 247:
            raise ValueError(f"slave_id must be 1-247, got {slave_id}")
        if not math.isfinite(float(level)):
            raise ValueError(f"level must be finite, got {level}")

        url = (
            f"{API_SET_RS485_LIVE}?{pump_name},{int(slave_id)},"
            f"{mode.lower()},{level}"
        )
        body = await self._request(
            url,
            method="GET",
            priority=API_PRIORITY_CRITICAL,
        )
        text = str(body) if body is not None else ""
        # Firmware JSON-encodes the response (res.write(JSON.stringify(...))),
        # so strip surrounding quotes for the common single-string case.
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        return text

    async def end_rs485_live(self) -> str:
        """End an RS485 live-control session and release the bus.

        Sends ``GET /setRS485Live?DONE``.  Always call this when finished
        with :meth:`set_rs485_live`, otherwise the controller keeps the
        normal RS485 polling paused for ~3 s after each call.

        Returns:
            The response string from the controller (usually ``"DONE"``).

        """
        body = await self._request(
            f"{API_SET_RS485_LIVE}?DONE",
            method="GET",
            priority=API_PRIORITY_CRITICAL,
        )
        text = str(body) if body is not None else ""
        if text.startswith('"') and text.endswith('"'):
            return text[1:-1]
        return text
