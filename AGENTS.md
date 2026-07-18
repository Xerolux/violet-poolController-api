# AGENTS.md - Instructions for AI Agents & Chatbots

This file provides context and guidelines for AI assistants working on this project.

## Project Overview

**violet-poolController-api** is an async Python client library for the Violet Pool Controller HTTP API. It communicates with the controller hardware via HTTP (JSON and text/plain responses).

- **Language:** Python 3.12+
- **Framework:** `aiohttp` (async HTTP client)
- **Package:** `violet-poolcontroller-api` on PyPI
- **License:** AGPL-3.0-or-later

## Repository Structure

```
violet_poolcontroller_api/     # Main package
  api.py                       # VioletPoolAPI client class - all public methods
  const_api.py                 # API endpoints, actions, error codes, constants
  const_devices.py             # Device parameters, state mappings, VioletState class
  circuit_breaker.py           # Circuit breaker pattern for resilience
  utils_rate_limiter.py        # Token bucket rate limiter
  utils_sanitizer.py           # Input sanitization (XSS, path traversal, etc.)
  __init__.py                  # Public exports

tests/
  test_api.py                  # Unit tests (uses aioresponses for HTTP mocking)
  mock_server.py               # Full mock server simulating the controller
  test_api_smoke.py            # End-to-end smoke test against mock server
  test_mock_server.py          # Integration test (auth, full workflow)
```

## Commands

```bash
# Lint
python -m ruff check .

# Run unit tests
pytest tests/test_api.py

# Run mock server (for manual testing)
python tests/mock_server.py --user admin --password secret --port 8480

# Run full smoke test (starts mock server automatically)
python tests/test_api_smoke.py --user admin --password secret
```

## Architecture Notes

- All API methods are async and use `aiohttp.ClientSession`
- The controller uses Basic Auth (optional, configured by user)
- Controller responses are either JSON (`application/json`) or plain text (`text/plain`)
- Switch commands return multi-line text: `"OK\nPUMP\nON"` - parsed by `_command_result()`
- Dosing pumps (`DOS_*`) use `/triggerManualDosing` (POST), all other functions use `/setFunctionManually` (GET)
- Readings come in two formats: dict (base module) or list (dosing-standalone) - automatically normalized
- Extension relay keys (`EXT1_*`, `EXT2_*`) are filtered based on alive counters

## Mock Server

The mock server (`tests/mock_server.py`) simulates all controller endpoints for testing without real hardware.

Features:
- All 15 API endpoints with realistic responses
- Stateful: switch/dosing state changes are reflected in getReadings
- Basic Auth support (`--user` / `--password`)
- Simulated network latency (`--delay`)
- Dosing-standalone mode (`--standalone`)
- Sensor drift (pH, ORP, chlorine values change slowly over time)
- Error simulation via `/mock/error?code=500&count=3`
- State inspection via `/mock/state`
- Reset via `/mock/reset`

## Coding Conventions

- Line length: 100 (ruff config)
- Target: Python 3.12+
- Ruff rules: E, F, W, I, UP
- No comments unless explicitly requested
- All public methods have docstrings with Args/Returns/Raises
- German error messages from the controller are preserved as-is

## When Making Changes

1. Run `python -m ruff check .` after edits
2. Run `pytest tests/test_api.py` to verify unit tests pass
3. If adding new API methods: add corresponding mock server handler AND smoke test
4. If modifying endpoints: update both `const_api.py` constants and mock server
5. Never commit secrets, passwords, or real IP addresses

## Backward Compatibility & Deprecation Policy

This library has downstream consumers — most notably the Home Assistant
integration at [Xerolux/violet-hass](https://github.com/Xerolux/violet-hass),
but also any third-party user importing `violet_poolcontroller_api`. A
"minor" removal in this repo can break a downstream release days later,
because consumers pin `>=` and resolve the latest version at install time.

**Background.** v0.0.36 removed `InputSanitizer.validate_speed` and
`InputSanitizer.validate_duration` (faulty duplicates of the canonical
validators in `_api_model`). The HA integration still called them, so the
next integration release failed its CI on Python 3.12/3.13 (which resolved
0.0.36) while the maintainer's local venv still had 0.0.35 pinned. The fix
required a same-day migration of the integration. This policy exists to
prevent that class of breakage.

### What counts as a breaking change

Treat any of these as breaking, regardless of how small it looks:

- Removing or renaming a public symbol (class, function, method, constant,
  module attribute) — including ones you believe are "unused".
- Changing a function/method signature (parameter names, positional↔keyword,
  adding required params, removing kwargs consumers pass).
- Changing documented behavior in a way consumers may rely on (e.g.
  "silently clamps" → "raises").
- Changing the wire format, error type, or return-type shape of a public
  method that consumers assert on.

### Procedure for breaking changes

Do **not** remove in the same release you deprecate. Follow this sequence:

1. **Deprecate first.** Keep the old symbol callable. Emit a
   `DeprecationWarning` with a clear message naming the replacement and
   the version where removal is planned. Update docstrings to say
   *"Deprecated since vX.Y.Z, use <replacement>. Will be removed in
   vX.Y+2."*
2. **Update every known consumer.** Open the matching PR in
   `Xerolux/violet-hass` (and any other tracked consumer) that migrates off
   the deprecated symbol. Wait for it to merge and ship a release before
   proceeding to step 3.
3. **Document in CHANGELOG.** Mark the deprecation under a `Deprecated`
   heading in the library's `CHANGELOG.md` so it is visible at release time.
4. **Remove in a later release.** Only after at least one full release cycle
   with the deprecation live AND the consumer migration shipped. Record the
   removal under a `Removed` heading.

### Versioning

While the major version is still `0.x`, treat the **minor** digit as the
compatibility boundary (i.e. SemVer-0.0 rules): breaking changes bump the
minor version (`0.0.36` → `0.1.0`), deprecations and additive changes may
ship in a patch. Once the library reaches `1.0.0`, switch to full SemVer.

### Additive changes (non-breaking)

Adding new methods, new constants, new optional parameters with defaults,
or loosening validation is **non-breaking** and may ship in any release.
Still note them under `Added` in `CHANGELOG.md`.

### Quick checklist before cutting a release

- [ ] No public symbol removed or renamed in this release without a prior
      deprecation cycle.
- [ ] If a signature changed, the known consumers have already shipped a
      release that works with the new signature.
- [ ] `CHANGELOG.md` has `Deprecated` / `Removed` / `Added` sections
      matching the actual changes.
