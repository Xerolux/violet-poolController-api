# Violet Pool Controller API

[![PyPI version](https://img.shields.io/pypi/v/violet-poolController-api.svg?style=for-the-badge)](https://pypi.org/project/violet-poolController-api/)
[![PyPI downloads](https://img.shields.io/pypi/dm/violet-poolController-api.svg?style=for-the-badge)](https://pypistats.org/packages/violet-poolcontroller-api)
[![Python versions](https://img.shields.io/pypi/pyversions/violet-poolController-api.svg?style=for-the-badge)](https://pypi.org/project/violet-poolController-api/)
[![License](https://img.shields.io/github/license/Xerolux/violet-poolController-api.svg?style=for-the-badge)](LICENSE)

[![Buy Me A Coffee](https://img.shields.io/badge/Buy%20Me%20A%20Coffee-xerolux-yellow?logo=buy-me-a-coffee&style=for-the-badge)](https://www.buymeacoffee.com/xerolux)
[![Tesla](https://img.shields.io/badge/Tesla-Referral-red?style=for-the-badge&logo=tesla)](https://ts.la/sebastian564489)

An asynchronous Python client for interacting with the **Violet Pool Controller**.

This library is primarily designed to power the official [Violet Pool Controller Home Assistant Integration](https://github.com/Xerolux/violet-hass), but it can be used independently for any Python project that needs to fetch readings or control a Violet Pool system.

## Features
* **Asynchronous:** Fully async operations using `aiohttp`.
* **Resilient:** Built-in Circuit Breaker and Rate Limiter to protect both the client and the controller from overload.
* **Sanitization:** Strict payload input sanitization to prevent injection and invalid settings.

## Installation

```bash
pip install violet-poolController-api
```

## Basic Usage

```python
import asyncio
import aiohttp
from violet_poolcontroller_api.api import VioletPoolAPI, VioletPoolAPIError

async def main():
    # Create an aiohttp ClientSession
    async with aiohttp.ClientSession() as session:
        # Initialize the API
        api = VioletPoolAPI(
            host="192.168.1.100",
            username="admin",
            password="your_password",
            session=session
        )

        try:
            # --- 1. Fetch current sensor readings ---
            readings = await api.get_readings()
            print("Current Pool Readings:")
            print(readings)

            # --- 2. Control the Filter Pump ---
            # Set pump speed to 2 (Normal) permanently (duration=0)
            await api.set_pump_speed(speed=2, duration=0)
            print("\nPump speed set to 2.")

            # --- 3. Set Target Temperature ---
            # Set the target temperature for the heater to 28.5 degrees
            await api.set_device_temperature("HEATER", 28.5)
            print("\nHeater target temperature set to 28.5°C.")

            # --- 4. Control Pool Lights ---
            # Trigger the color pulse animation for the pool light
            await api.set_light_color_pulse()
            print("\nLight color pulse triggered.")

        except VioletPoolAPIError as e:
            print(f"An error occurred while communicating with the Violet controller: {e}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Advanced Operations

The API client includes many more functions tailored to the Violet Controller:
- `get_config(["PUMP_SPEED_1", "PUMP_SPEED_2"])`: Fetch specific configuration values.
- `set_ph_target(7.2)`: Change the pH target value.
- `set_orp_target(750)`: Change the ORP (Redox) target value.
- `set_pv_surplus(active=True)`: Enable the PV-Surplus mode.
- `manual_dosing(dosing_type="Chlor", duration=120)`: Trigger manual chemical dosing.

For a full list of available commands, please refer to the source code in `api.py`.

## License
MIT License

---

## About the Violet Pool Controller

Der **VIOLET Pool Controller** von [PoolDigital GmbH & Co. KG](https://www.pooldigital.de/) ist ein Premium Smart Pool Automation System aus deutscher Entwicklung – mit JSON API für nahtlose Home Assistant Integration.

- **Offizieller Shop:** [pooldigital.de](https://www.pooldigital.de/)
- **Community:** [PoolDigital Forum](http://forum.pooldigital.de/)

**Disclaimer:**
*This is an unofficial, community-driven project. It is not affiliated with, endorsed by, or associated with PoolDigital GmbH & Co. KG in any way. "VIOLET" and any related trademarks are the property of their respective owners.*
