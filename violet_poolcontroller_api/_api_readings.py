"""Internal reading and monitoring operations."""

from __future__ import annotations

from typing import Any

from ._api_mixin import APIClientMixin
from ._api_model import VioletPoolAPIError
from .const_api import (
    API_GET_HISTORY,
    API_GET_OUTPUT_RUNTIMES,
    API_GET_OUTPUT_STATES,
    API_GET_OVERALL_DOSING,
    API_GET_WEATHER_DATA,
    API_READINGS,
)
from .readings import VioletReadings


class ReadingsMixin(APIClientMixin):
    """Reading and monitoring operations."""

    def _flatten_getreadings_response(
        self,
        response: dict[str, Any],
    ) -> dict[str, Any]:
        """Flatten the getReadings list response for standalone firmware.

        Args:
            response: The raw response dictionary from the controller.

        Returns:
            The flattened key-value dictionary,
            or the original response if not applicable.

        """
        readings = response.get("getReadings")
        if readings is None:
            return response

        if isinstance(readings, dict):
            self._dosing_standalone = False
            return self._filter_orphan_extension_keys(readings)

        if isinstance(readings, list):
            self._dosing_standalone = True
            flat_dict: dict[str, Any] = {}
            for item in readings:
                if isinstance(item, dict) and item.get("VALUE NAME"):
                    key = str(item["VALUE NAME"]).strip().strip('"')
                    val = item.get("VALUE", item.get("VALUE ", item.get("value")))  # "VALUE " fallback for firmware <1.0.9 trailing-space bug
                    flat_dict[key] = val
            return flat_dict

        return response

    @staticmethod
    def _filter_orphan_extension_keys(readings: dict[str, Any]) -> dict[str, Any]:
        """Remove EXT*_ keys when the corresponding module is not connected.

        The controller always returns EXT*_ keys even when no hardware module
        is physically present.  We only keep them when the matching
        ``SYSTEM_ext*module_alive_count`` key exists in the payload.
        """
        ext1_alive = "SYSTEM_ext1module_alive_count" in readings
        ext2_alive = "SYSTEM_ext2module_alive_count" in readings

        if not ext1_alive:
            readings = {k: v for k, v in readings.items() if not k.startswith("EXT1")}
        if not ext2_alive:
            readings = {k: v for k, v in readings.items() if not k.startswith("EXT2")}
        return readings

    async def get_readings(self) -> VioletReadings:
        """Return the complete dataset from the controller as a typed snapshot.

        The returned :class:`~violet_poolcontroller_api.readings.VioletReadings`
        object implements :class:`~collections.abc.Mapping`, so all existing
        code that accesses ``data.get("KEY")`` or ``"KEY" in data`` continues
        to work unchanged.  Typed properties (``readings.pump``,
        ``readings.ph``, etc.) are available as an additive convenience.

        Returns:
            A :class:`VioletReadings` instance wrapping all readings.

        Raises:
            VioletPoolAPIError: If the payload is unexpected.

        """
        response = await self._request_json_dict(
            API_READINGS,
            query="ALL",
            payload_name="getReadings",
        )
        flat = self._flatten_getreadings_response(response)
        return VioletReadings(flat)

    async def get_hardware_profile(self) -> dict[str, bool]:
        """Detect connected hardware modules from the controller readings.

        Uses ``SYSTEM_*_alive_count`` keys to determine which modules are
        physically present.  For standalone dosing setups (list-format
        payloads) the base module is always reported as absent.

        Returns:
            A dictionary with keys ``base_module``, ``dosing_module``,
            ``extension_module_1``, and ``extension_module_2``.
        """
        response = await self._request_json_dict(
            API_READINGS,
            query="ALL",
            payload_name="getReadings",
        )
        # Use flat dict directly (VioletReadings wrapping not needed here)
        flat = self._flatten_getreadings_response(response)

        has_base = not self._dosing_standalone and bool(flat)
        return {
            "base_module": has_base,
            "dosing_module": self._dosing_standalone or "SYSTEM_dosagemodule_alive_count" in flat,
            "extension_module_1": "SYSTEM_ext1module_alive_count" in flat,
            "extension_module_2": "SYSTEM_ext2module_alive_count" in flat,
        }

    async def get_specific_readings(
        self,
        categories: list[str] | tuple[str, ...],
    ) -> VioletReadings:
        """Return a reduced typed snapshot for the provided categories.

        Categories are joined with ``,`` and sent as the query string of
        ``/getReadings?<categories>``.  See
        :data:`~violet_poolcontroller_api.const_api.SPECIFIC_READING_GROUPS`
        for the special tokens (``DOSAGE``, ``RUNTIMES``, ``PUMPPRIOSTATE``,
        ``BACKWASH``, ``SYSTEM``) that act as feature flags rather than
        regex matchers – without them the corresponding computed fields are
        NOT included in the response, even when ``ALL`` is present.

        Args:
            categories: A list or tuple of category strings to fetch.  To
                receive computed dosing stats, runtimes, or priority states,
                include ``ALL`` plus the respective token
                (e.g. ``["ALL", "DOSAGE"]``).

        Returns:
            A :class:`VioletReadings` instance for the requested categories.

        Raises:
            VioletPoolAPIError: If no categories are provided
                or the payload is unexpected.

        """
        if not categories:
            msg = "At least one category must be provided"
            raise VioletPoolAPIError(msg)

        query = self._csv_query_from_values(categories, field_name="categories")
        response = await self._request_json_dict(
            API_READINGS,
            query=query,
            payload_name="getReadings",
        )
        return VioletReadings(self._flatten_getreadings_response(response))

    async def get_history(
        self,
        *,
        hours: int = 24,
        sensor: str = "ALL",
    ) -> dict[str, Any]:
        """Fetch historical readings from the controller.

        Args:
            hours: The number of hours of history to fetch.
            sensor: The specific sensor to fetch history for, or "ALL".

        Returns:
            A dictionary containing the history data.

        Raises:
            VioletPoolAPIError: If the payload is unexpected.

        """
        safe_hours = max(1, int(hours))
        params = {"hours": safe_hours, "sensor": sensor or "ALL"}
        return await self._request_json_dict(
            API_GET_HISTORY,
            params=params,
            payload_name="getHistory",
        )

    async def get_weather_data(self) -> dict[str, Any]:
        """Return the current weather information used by the controller.

        Returns:
            A dictionary containing weather data.

        Raises:
            VioletPoolAPIError: If the payload is unexpected.

        """
        return await self._request_json_dict(
            API_GET_WEATHER_DATA,
            payload_name="getWeatherdata",
        )

    async def get_overall_dosing(self) -> dict[str, Any]:
        """Return aggregated dosing statistics.

        Returns:
            A dictionary containing overall dosing statistics.

        Raises:
            VioletPoolAPIError: If the payload is unexpected.

        """
        return await self._request_json_dict(
            API_GET_OVERALL_DOSING,
            payload_name="getOverallDosing",
        )

    async def get_output_states(self) -> dict[str, Any]:
        """Return detailed information about output states.

        Returns:
            A dictionary containing output states.

        Raises:
            VioletPoolAPIError: If the payload is unexpected.

        """
        return await self._request_json_dict(
            API_GET_OUTPUT_STATES,
            payload_name="getOutputstates",
        )

    async def get_output_runtimes(self) -> dict[str, Any]:
        """Fetch output runtime statistics from the controller.

        Returns a flat dict with runtime (HH:MM:SS format) and last-on/off
        (ISO datetime strings) for all outputs: PUMP, SOLAR, HEATER, BACKWASH,
        REFILL, LIGHT, ECO, all dosing outputs, OMNIDC channels, and extension
        relay channels.  Also includes CPU_UPTIME, LOAD_AVG, and version fields.

        Returns:
            Dict with runtime/timestamp strings for all outputs.

        Raises:
            VioletPoolAPIError: If the API call fails or the response is not a
                JSON object.

        """
        return await self._request_json_dict(
            API_GET_OUTPUT_RUNTIMES,
            payload_name="getOutputruntimes",
        )
