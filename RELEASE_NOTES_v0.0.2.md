🚀 Initial Release of the Violet Pool Controller API

This is the first official release of the asynchronous Python client for the VIOLET Pool Controller by PoolDigital.

Features included in this release:

* Fully asynchronous operations using aiohttp.
* Built-in Circuit Breaker and Rate Limiter to protect the controller.
* Strict payload input sanitization.
* Support for reading all pool sensors and states.
* Support for controlling pumps, relays, heating targets, and light scenes (DMX/LED).
* Support for triggering manual chemical dosing.

Installation:
```bash
pip install violet-poolController-api==0.0.2
```

Note: This API is actively used by the official Violet Home Assistant Integration.