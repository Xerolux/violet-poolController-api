# Violet Pool Controller API - Wiki

Welcome to the official documentation for the **Violet Pool Controller API** Python library. This library is designed to facilitate asynchronous interaction with your Violet Pool Controller.

## Table of Contents
1. [Introduction](#introduction)
2. [Installation](#installation)
3. [Initialization & Authentication](#initialization--authentication)
4. [Fetching Data](#fetching-data)
   - [All Readings](#all-readings)
   - [Specific Readings](#specific-readings)
   - [History & Statistics](#history--statistics)
   - [Weather Data](#weather-data)
5. [Controlling Devices](#controlling-devices)
   - [Pump Control](#pump-control)
   - [Climate / Heating Control](#climate--heating-control)
   - [Light Control](#light-control)
   - [Relays & Switches](#relays--switches)
   - [DMX Scenes](#dmx-scenes)
   - [Digital Input Rules](#digital-input-rules)
6. [Dosing & Targets](#dosing--targets)
   - [Target Values (pH, ORP, Chlorine)](#target-values)
   - [Manual Dosing](#manual-dosing)
   - [Dosing Parameters](#dosing-parameters)
7. [Configuration & Calibration](#configuration--calibration)
   - [Reading Configuration](#reading-configuration)
   - [Setting Configuration](#setting-configuration)
   - [Calibration Data](#calibration-data)
8. [Advanced Topics](#advanced-topics)
   - [PV Surplus Mode](#pv-surplus-mode)
   - [Test Mode](#test-mode)
   - [Error Handling](#error-handling)
   - [Rate Limiting & Circuit Breaker](#rate-limiting--circuit-breaker)

---

## Introduction
The `violet_poolcontroller_api` provides an asynchronous `VioletPoolAPI` class to communicate with the Violet Pool Controller. It uses `aiohttp` for robust and non-blocking HTTP requests.

## Installation
```bash
pip install violet-poolController-api
```

## Initialization & Authentication
To start, you need an `aiohttp.ClientSession` and your controller's credentials.

```python
import asyncio
import aiohttp
from violet_poolcontroller_api.api import VioletPoolAPI, VioletPoolAPIError

async def main():
    async with aiohttp.ClientSession() as session:
        api = VioletPoolAPI(
            host="192.168.1.100",
            username="admin",        # Optional, depending on controller settings
            password="your_password",# Optional
            session=session,
            use_ssl=False,           # Set to True if you use HTTPS
            verify_ssl=True,
            timeout=10,              # Request timeout in seconds
            max_retries=3
        )

        # Now you can call api methods...
```

## Fetching Data

### All Readings
To retrieve all current sensor and device states:
```python
readings = await api.get_readings()
print(readings)
```

### Specific Readings
To optimize data transfer, you can fetch only specific categories (e.g., `ADC`, `DOSAGE`, `SYSTEM`):
```python
readings = await api.get_specific_readings(["ADC", "SYSTEM"])
```

### History & Statistics
```python
# Fetch history for the last 24 hours
history = await api.get_history(hours=24, sensor="ALL")

# Fetch overall dosing statistics
dosing_stats = await api.get_overall_dosing()

# Fetch output states
output_states = await api.get_output_states()
```

### Weather Data
If configured on the controller, fetch current weather data:
```python
weather = await api.get_weather_data()
```

## Controlling Devices

Many devices can be turned `ON`, `OFF`, or set to `AUTO`. Some devices support durations (`duration` in seconds, `0` means permanently) or speeds/values.

### Pump Control
```python
# Set filter pump to normal speed (2) permanently (0)
await api.set_pump_speed(speed=2, duration=0)

# Alternative general control: Turn pump OFF for 1 hour (3600 seconds)
await api.control_pump(action="OFF", duration=3600)
```
*Speeds:* `1` = ECO, `2` = Normal, `3` = Boost.

### Climate / Heating Control
```python
# Set Target Temperature for HEATER
await api.set_device_temperature("HEATER", 28.5)

# Set Target Temperature for SOLAR
await api.set_device_temperature("SOLAR", 30.0)

# Turn HEATER ON
await api.set_switch_state("HEATER", "ON")
```

### Light Control
```python
# Turn LIGHT ON
await api.set_switch_state("LIGHT", "ON")

# Trigger the Light Color Pulse
await api.set_light_color_pulse()
```

### Relays & Switches
You can control various relays like `BACKWASH`, `REFILL`, `ECO`, extension relays (`EXT1_1` to `EXT2_8`), and Omni DC outputs (`OMNI_DC0` to `OMNI_DC5`) using `set_switch_state`.
```python
# Turn on Extension Relay 1.1 for 5 minutes
await api.set_switch_state("EXT1_1", "ON", duration=300)
```

### DMX Scenes
The controller supports 12 DMX scenes (`DMX_SCENE1` to `DMX_SCENE12`).
```python
# Trigger DMX Scene 1
await api.set_switch_state("DMX_SCENE1", "ON")

# Turn ALL DMX Scenes OFF
await api.set_all_dmx_scenes("ALLOFF") # options: ALLON, ALLOFF, ALLAUTO
```

### Digital Input Rules
Digital input rules (`DIRULE_1` to `DIRULE_7`) can be triggered or locked.
```python
# Trigger Rule 1
await api.trigger_digital_input_rule("DIRULE_1")

# Lock Rule 1
await api.set_digital_input_rule_lock("DIRULE_1", locked=True)
```

## Dosing & Targets

### Target Values
Update your pool's chemistry targets:
```python
# Set pH target to 7.2
await api.set_ph_target(7.2)

# Set ORP (Redox) target to 750 mV
await api.set_orp_target(750)

# Set Minimum Chlorine target to 1.5 mg/l
await api.set_min_chlorine_level(1.5)
```

### Manual Dosing
Trigger manual dosing for a specific duration (in seconds).
Supported types: `"Chlor"`, `"pH-"`, `"pH+"`, `"Elektrolyse"`, `"Flockmittel"`.
```python
# Manually dose Chlorine for 60 seconds
await api.manual_dosing(dosing_type="Chlor", duration=60)
```

### Dosing Parameters
Update specific dosing settings via a mapping:
```python
parameters = {
    "DOS_1_CL_PER_H": 500,
    "DOS_4_PHM_PER_H": 250
}
await api.set_dosing_parameters(parameters)
```

## Configuration & Calibration

### Reading Configuration
Fetch specific system configuration keys.
```python
config_values = await api.get_config(["PUMP_SPEED_1", "PUMP_SPEED_2"])
print(config_values)
```

### Setting Configuration
Safely update system settings (input is sanitized automatically).
```python
await api.set_config({"PUMP_SPEED_1": 1500})
```

### Calibration Data
```python
# Get raw calibration values for all sensors
raw_calib = await api.get_calibration_raw_values()

# Get calibration history for a specific sensor (e.g., "pH")
ph_history = await api.get_calibration_history("pH")
print(ph_history)

# Restore a previous calibration (requires timestamp from history)
await api.restore_calibration("pH", "2023-10-01T12:00:00")
```

## Advanced Topics

### PV Surplus Mode
If you have a PV system integrated, you can enable the PV surplus mode to utilize excess solar energy.
```python
# Enable PV Surplus mode and force pump speed to 3
await api.set_pv_surplus(active=True, pump_speed=3)
```

### Test Mode
Activate the controller's hardware test mode for a specific output.
```python
await api.set_output_test_mode(output="RELAY_1", mode="SWITCH", duration=120)
```

### Error Handling
All API interactions can raise `VioletPoolAPIError`. It is recommended to wrap calls in a try-except block.
```python
try:
    await api.get_readings()
except VioletPoolAPIError as e:
    print(f"API Error: {e}")
```

### Rate Limiting & Circuit Breaker
The API client comes with built-in protections:
- **Rate Limiter:** Prevents overwhelming the controller by queueing requests (e.g., max 10 requests per second).
- **Circuit Breaker:** Temporarily halts requests if multiple consecutive errors occur, allowing the controller to recover.
