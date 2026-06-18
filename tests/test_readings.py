"""Tests for violet_poolcontroller_api.readings module."""

from collections.abc import Mapping
from datetime import timedelta

import pytest

from violet_poolcontroller_api.const_devices import (
    CoverState,
    OnewireState,
    OutputState,
    PvSurplusState,
)
from violet_poolcontroller_api.readings import VioletReadings


class TestVioletReadingsMappingProtocol:
    """VioletReadings implements the Mapping protocol (drop-in for dict)."""

    @pytest.fixture
    def sample_data(self):
        return {
            "POOL_TEMP": 24.5,
            "SOLAR_TEMP": 32.1,
            "AMBIENT_TEMP": 18.3,
            "pH": 7.2,
            "ORP": 650,
            "PUMP_STATE": "1",
            "HEATER_STATE": "0",
        }

    def test_is_a_mapping_not_a_dict(self, sample_data):
        readings = VioletReadings(sample_data)
        assert isinstance(readings, Mapping)
        assert not isinstance(readings, dict)

    def test_length(self, sample_data):
        assert len(VioletReadings(sample_data)) == 7

    def test_value_access_via_get(self, sample_data):
        readings = VioletReadings(sample_data)
        assert readings.get("POOL_TEMP") == 24.5
        assert readings.get("pH") == 7.2

    def test_missing_key_returns_none(self, sample_data):
        readings = VioletReadings(sample_data)
        assert readings.get("NONEXISTENT") is None
        assert readings.get("NONEXISTENT", "default") == "default"

    def test_contains(self, sample_data):
        readings = VioletReadings(sample_data)
        assert "POOL_TEMP" in readings
        assert "NONEXISTENT" not in readings

    def test_getitem(self, sample_data):
        assert VioletReadings(sample_data)["ORP"] == 650

    def test_getitem_raises_keyerror_for_missing(self, sample_data):
        with pytest.raises(KeyError):
            VioletReadings(sample_data)["NONEXISTENT"]

    def test_keys_iteration(self, sample_data):
        readings = VioletReadings(sample_data)
        keys = list(readings.keys())
        assert "POOL_TEMP" in keys
        assert len(keys) == 7


class TestVioletReadingsDefensiveCopy:
    """The wrapped dict is copied so external mutation does not leak in."""

    def test_external_mutation_does_not_affect_readings(self):
        data = {"TEMP": 25.0}
        readings = VioletReadings(data)
        data["TEMP"] = 999.0
        assert readings.get("TEMP") == 25.0

    def test_raw_is_read_only_proxy(self):
        readings = VioletReadings({"A": 1})
        raw = readings.raw
        assert raw["A"] == 1
        with pytest.raises(TypeError):
            raw["A"] = 2


class TestVioletReadingsTypedAccessors:
    """Typed cached_property accessors cast raw strings to proper types."""

    @pytest.fixture
    def readings(self):
        return VioletReadings(
            {
                "SW_VERSION": "1.1.9",
                "CPU_TEMP": "52.3",
                "CPU_UPTIME": "12d 4h 30m",
                "SYSTEM_MEMORY": "256.5",
                "pH_value": "7.20",
                "pH_value_min": "7.0",
                "pH_value_max": "7.4",
                "orp_value": "650",
                "pot_value": "1.5",
                "PUMP": "4",
                "PUMP_RUNTIME": "04h 33m 12s",
                "SOLAR": "3|PUMP_ANTI_FREEZE",
                "HEATER": "0",
                "PVSURPLUS": "1",
                "COVER_STATE": "open",
                "onewire1_value": "24.1",
                "onewire1_state": "OK",
                "onewire2_state": "CRC_FAULT",
                "ADC1_value": "3.3",
                "INPUT1": "1",
                "INPUT2": "0",
                "DOS_1_CL": "1",
                "DMX_SCENE1": "4",
                "EXT1_1": "0",
            }
        )

    def test_sw_version(self, readings):
        assert readings.sw_version == "1.1.9"

    def test_cpu_temp(self, readings):
        assert readings.cpu_temp == pytest.approx(52.3)

    def test_cpu_uptime_is_timedelta(self, readings):
        assert readings.cpu_uptime == timedelta(days=12, hours=4, minutes=30)

    def test_memory_usage(self, readings):
        assert readings.memory_usage_mb == pytest.approx(256.5)

    def test_ph(self, readings):
        assert readings.ph == pytest.approx(7.20)
        assert readings.ph_min == pytest.approx(7.0)
        assert readings.ph_max == pytest.approx(7.4)

    def test_orp(self, readings):
        assert readings.orp == pytest.approx(650.0)

    def test_chlorine(self, readings):
        assert readings.chlorine == pytest.approx(1.5)

    def test_pump_state_enum(self, readings):
        assert readings.pump is OutputState.MANUAL_ON
        assert readings.pump.is_on
        assert readings.pump.is_manual

    def test_pump_runtime(self, readings):
        assert readings.pump_runtime == timedelta(hours=4, minutes=33, seconds=12)

    def test_solar_composite_state_uses_numeric_prefix(self, readings):
        assert readings.solar is OutputState.AUTO_PRIO_ON

    def test_heater_state(self, readings):
        assert readings.heater is OutputState.AUTO_OFF

    def test_pv_surplus(self, readings):
        assert readings.pv_surplus is PvSurplusState.ON_BY_INPUT
        assert readings.pv_surplus.is_on

    def test_cover_state_case_insensitive(self, readings):
        assert readings.cover is CoverState.OPEN

    def test_onewire_temperatures(self, readings):
        assert readings.onewire_temperatures[1] == pytest.approx(24.1)
        assert readings.onewire_temperatures[2] is None  # not provided

    def test_onewire_states(self, readings):
        assert readings.onewire_states[1] is OnewireState.OK
        assert readings.onewire_states[2] is OnewireState.CRC_FAULT

    def test_analog_inputs(self, readings):
        assert readings.analog_inputs[1] == pytest.approx(3.3)

    def test_digital_inputs(self, readings):
        assert readings.digital_inputs[1] is True
        assert readings.digital_inputs[2] is False

    def test_dosing_states(self, readings):
        assert readings.dosing_states["DOS_1_CL"] is OutputState.AUTO_ON

    def test_dmx_scenes(self, readings):
        assert readings.dmx_scenes[1] is not None

    def test_extension_relays(self, readings):
        assert readings.extension_relays["EXT1_1"] is OutputState.AUTO_OFF

    def test_repr(self, readings):
        text = repr(readings)
        assert "VioletReadings" in text
        assert "pH=" in text


class TestVioletReadingsEdgeCases:
    def test_empty_readings(self):
        readings = VioletReadings({})
        assert len(readings) == 0
        assert readings.ph is None
        assert readings.pump is None

    def test_large_dataset(self):
        large_data = {f"KEY_{i}": f"value_{i}" for i in range(1000)}
        readings = VioletReadings(large_data)
        assert len(readings) == 1000
        assert readings.get("KEY_0") == "value_0"
        assert readings.get("KEY_999") == "value_999"

    def test_special_characters_in_values(self):
        data = {
            "UNICODE": "测试",
            "SPECIAL": "!@#$%^&*()",
            "QUOTES": 'value with "quotes"',
        }
        readings = VioletReadings(data)
        assert readings.get("UNICODE") == "测试"
        assert readings.get("SPECIAL") == "!@#$%^&*()"

    def test_numeric_edge_cases(self):
        data = {
            "ZERO": 0,
            "NEGATIVE": -100,
            "FLOAT": 3.14159,
            "LARGE": 999999999,
        }
        readings = VioletReadings(data)
        assert readings.get("ZERO") == 0
        assert readings.get("NEGATIVE") == -100
        assert readings.get("FLOAT") == 3.14159


class TestVioletReadingsRealisticSnapshot:
    def test_realistic_pool_data(self):
        realistic_data = {
            "POOL_TEMP": 24.5,
            "SOLAR_TEMP": 35.2,
            "AMBIENT_TEMP": 22.0,
            "pH": 7.3,
            "ORP": 680,
            "CONDUCTIVITY": 1200,
            "PUMP_STATE": "1",
            "HEATER_STATE": "0",
            "SOLAR_STATE": "1",
            "DOSING_PH_MINUS": "0",
            "DOSING_PH_PLUS": "0",
            "DOSING_CL": "1",
            "PUMP_RUNTIME": 3600,
            "FILTER_RUNTIME": 3600,
            "ERROR_CODE": "0",
            "DI1": "0",
            "DI2": "1",
            "DO1": "0",
            "DO2": "1",
        }
        readings = VioletReadings(realistic_data)
        assert len(readings) == 19
        assert readings.get("POOL_TEMP") == 24.5
        assert readings.get("DI1") == "0"
