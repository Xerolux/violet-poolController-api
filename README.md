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
from violet_poolcontroller_api.api import VioletPoolAPI

async def main():
    # Initialize the API
    api = VioletPoolAPI(
        host="192.168.1.100",
        username="admin",
        password="your_password"
    )

    try:
        # Fetch current sensor readings
        readings = await api.get_readings()
        print(readings)
    finally:
        await api.close()

if __name__ == "__main__":
    asyncio.run(main())
```

## License
MIT License
