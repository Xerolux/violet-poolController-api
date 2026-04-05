## v0.0.5 - Bugfix Release

### Bug Fixes

* **Circuit Breaker stale timestamp**: `last_failure_time` used a cached timestamp from before the function call instead of `time.monotonic()` at the actual failure moment. This caused the circuit breaker to transition to HALF_OPEN too early.
* **4xx errors counted as circuit breaker failures**: HTTP 4xx client errors (400, 404, etc.) incorrectly triggered `VioletPoolAPIError`, which incremented the circuit breaker failure counter. They now raise `ClientResponseError` instead, leaving the circuit breaker unaffected.
* **Dead code removed**: Unreachable fallback exception in `_request()` replaced with a clearer message.
* **Missing `DEVICE_PARAMETERS` for ECO and REFILL**: `ECO` and `REFILL` were defined in `SWITCH_FUNCTIONS` but had no corresponding `DEVICE_PARAMETERS` entry, causing `set_switch_state()` to fall back to a generic template.

### Improvements

* CI matrix now tests Python 3.12 and 3.14 via tox.
* Connect timeout calculation corrected.
* Removed unnecessary async methods.

Installation:
```bash
pip install violet-poolController-api==0.0.5
```
