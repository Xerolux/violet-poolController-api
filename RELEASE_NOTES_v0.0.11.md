## v0.0.11

### Bugfixes
- fix: clean up import order (PEP 8), deduplicate hardware detection into `_build_hardware_profile()`, export `VioletPoolAPI` and `VioletPoolAPIError` from `__init__.py`
- fix: rate limiter now records blocked requests in history so `get_stats()` correctly reports `recent_blocked_1min` (was always 0)
- fix: make `CircuitBreaker.reset()` async and acquire the internal lock before mutating state
- fix: introduce `DMX_SCENE_COUNT = 12` constant in `const_api.py` and replace hardcoded `range(1, 13)` in `set_all_dmx_scenes()`
- fix: cap duration in `set_output_test_mode()` to 86 400 s (24 h) to prevent controller firmware overflow on unconstrained input
- fix: restore `setup.py` which is required by the release workflow for version bumping

### Installation
```bash
pip install violet-poolController-api==0.0.11
```
