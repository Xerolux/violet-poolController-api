# Improvement plan for violet-poolController-api

Audit date: 2026-09-08. Audited state: 0.0.38 (commit `b5b5adf`).

This is a **work order, not a change** — no code was modified while it was
written. It lists the defects found in this package during a joint audit with
the Home Assistant integration (`violet-hass`). The integration's plan lives at
`violet-hass/docs/IMPROVEMENT_PLAN.md` and references the packages below by
the same IDs (`API-A5`, `API-A6`, `API-B27`, `API-B28`, `API-B29`). Ship the
fixes as **0.0.39**; the integration then bumps its pin.

Baseline before writing this plan: `ruff check` clean, `mypy` clean,
`pytest -q tests` 250 passed. Every finding below is a logic, safety, or
documentation problem that the tooling cannot see.

Working rules: one package per PR; write the regression test first; run
`ruff check . && mypy violet_poolcontroller_api && pytest -q tests` before
pushing; everything written into the repository is English (`AGENTS.md`);
add a changelog bullet for every behaviour change. Line numbers are from the
audited commit — grep for the quoted code rather than trusting them.

---

## P0 — Safety-critical

### API-A5 — State-changing GET commands are retried (double actuation)

**Files:** `api.py` (`_request`: `should_retry = retryable if retryable is not None else method_upper in {"GET", "HEAD"}`),
`_api_outputs.py`, `_api_system.py`.

The controller uses GET for nearly every mutation, so `set_switch_state`,
`set_output_test_mode`, `set_omni_position`, `set_rs485_live`,
`end_rs485_live`, `reset_blocking`, `set_system_service`, `init_update` are
retried up to `max_retries` times on a timeout or 5xx. A timeout *after* the
controller applied the command re-sends it. `PUSH` actions (digital-rule
trigger, cover open/close/stop) are toggles: a retry flips the state back or
moves the cover twice. `initUpdate` and `setOutputTestmode` are not idempotent
either. v0.0.36 already made POSTs non-retryable for exactly this reason.

**Fix.**
1. Add `_NON_RETRYABLE_ENDPOINTS = frozenset({API_SET_FUNCTION_MANUALLY, API_SET_OUTPUT_TESTMODE, API_SET_RS485_LIVE, API_RESET_BLOCKING, API_INIT_UPDATE, <service enable/disable endpoints>})` in `api.py`.
2. `should_retry = retryable if retryable is not None else (method_upper in {"GET", "HEAD"} and endpoint.split("?")[0] not in _NON_RETRYABLE_ENDPOINTS)`.
3. Also pass `retryable=False` explicitly from every command method so the
   intent is visible at the call site.

**Test.** Mirror `test_manual_dosing_post_is_not_retried` for
`trigger_digital_input_rule` on a 500 and `init_update` on a 503: exactly one
request must be sent.

### API-A6 — Rate-limiter timeout is a bypass, not a back-off

**File:** `api.py` (`except TimeoutError:` after `wait_if_needed(..., timeout=10.0)`).

On timeout the code logs, sleeps 1 s and sends the request **without a
token**. Under sustained overload every caller that waited 10 s then hits the
controller at once.

**Fix.** Raise `VioletPoolAPIError(f"Rate limit wait for {endpoint} exceeded {API_RATE_LIMIT_WAIT_TIMEOUT}s") from err`;
make the timeout a named constant in `const_api.py`. If the old behaviour is
wanted anywhere, add an explicit constructor flag defaulting to off.

**Test.** Patch `RateLimiter.wait_if_needed` to raise `TimeoutError`; assert
`get_readings()` raises `VioletPoolAPIError` and zero HTTP requests were made.

---

## P1 — Functional bugs

### API-B27 — `aiohttp<3.15` upper bound will block installation inside Home Assistant

**File:** `pyproject.toml` `dependencies`.

HA core tracks aiohttp releases closely (2026.9 already ships 3.14.x). When
HA moves to 3.15, `pip` inside HA refuses this package and the integration
fails to set up. Drop the upper bound (or use `<4`) and keep the
`aioresponses` shim in `tests/conftest.py` as the compatibility layer.

### API-B28 — Readings parsers raise `TypeError` on list/dict values

**File:** `readings.py` (`_parse_output_state`, `_parse_dmx_state`,
`_parse_rule_state`, `_parse_pv_surplus`).

`int(raw)` is guarded by `except (ValueError, KeyError)` only. The controller
does emit list values (`DOS_*_STATE` is "LIST, STRING" in
`docs/getReadings_clean.json`); `VioletReadings({"DMX_SCENE1": []}).dmx_scenes`
crashes the consumer. Also `"1.0"` returns `None` in these four parsers while
`get_system_services`/`is_dosage_enabled` accept decimal strings.

**Fix.** One helper `_opt_int(raw) -> int | None`:
`int(float(str(raw).split("|")[0].strip()))` inside
`except (ValueError, TypeError, OverflowError)`; use it in all four.
**Test.** Parametrise over `[]`, `{}`, `"1.0"`, `"4|X"`, `None`.

### API-B14 (shared with the integration) — H2O2 dosing is unreachable

`_api_dosing._trigger_dosing` hard-codes `"from": "1"`; the `const_api.py`
H2O2 block says H2O2 shares `DOS_1_CL` with `from=3`; `DOSING_CONFIG_PREFIX`
has H2O2 but `DOSING_FUNCTIONS`/`DOSING_OUTPUT_INDEX` do not, so
`manual_dosing("H2O2", …)` raises "Unknown dosing type" while
`set_dosage_enabled("H2O2", …)` works. Add `source: int = 1` to
`_trigger_dosing`, an `"H2O2": "DOS_1_CL"` entry with source 3, or document
H2O2 manual dosing as unsupported. Fix the misleading comment near
`const_api.py` line ~236.

### API-B29 — Smaller defects (one PR, or grouped by module)

`api.py`
- Invalid JSON (HTML login/captive page) raises `VioletPayloadError`, which the
  circuit breaker counts; six such 200-responses open the breaker and hide
  the real message. Add `VioletPayloadError` to `ignored_exceptions`.
- `ssl.create_default_context()` in `__init__` (when `use_ssl=True,
  verify_ssl=False`) loads the CA store from disk on the event loop only to
  set `CERT_NONE`. Return `ssl=False` from `_ssl_param` instead.
- Credentials in a `host` string leak into the `ValueError`
  (`"Invalid hostname format: admin:s3cret@…"`); use a fixed message.
- 4xx bodies are copied unbounded into exception text; truncate to ~200
  characters and collapse whitespace.
- `max_retries` is really "attempts" (`attempt_limit = self._max_retries`);
  either fix docs (`docs/API_REFERENCE.md`, docstring) or use `+ 1`; fix the
  wrong comment/mocks in `tests/test_api.py` around line 169.
- Only a total `ClientTimeout`; add `connect=min(total, 5.0)`, `sock_read=total`.
- `_build_secure_base_url`: the `"//" in host` check is dead after
  `host = parsed.netloc`; the regex rejects `_` (mDNS names such as
  `violet_pool.local`); `https://host` with `use_ssl=False` silently
  downgrades to http.
- `_sanitize_config_payload` sends `"None"` for `None`, `"1 2"` for lists and
  `0.0` for `nan`; raise `VioletPoolAPIError` for non-scalar/non-finite
  values.
- `_command_result` accepts a `dict` and returns it unchanged (no `success`
  key); remove the branch or normalise it.

`_api_outputs.py`, `_api_dosing.py`, `_api_system.py`
- Priorities contradict `const_api.py`'s own documentation:
  `set_switch_state`/`set_output_test_mode` should be `API_PRIORITY_CRITICAL`,
  `set_config` `HIGH`, `get_history`/`get_log`/`get_update_history` `LOW`.
  Today a pump-off command queues behind sensor polls.
- `get_log`: `has_more = lines and ...` returns `[]` for an empty body and
  `split("\n")` keeps `\r`. Use `splitlines()` and
  `bool(lines) and lines[-1].strip() == "LOAD_MORE"`.
- `get_live_trace` docstring promises float parsing; the code only swaps
  `,`→`.` in every column. Either parse (`float(txt)` in a `try`, return type
  `dict[str, str | float]`) or drop the sentence.
- `parse_error_notification` emits `"Unbekannter Fehlercode {code}"` (German
  library prose); use `"Unknown error code {code}"`.
- `set_target_value` validates `numeric_value` but posts the original value;
  send `numeric_value`.
- `set_switch_state` accepts `OMNI_DC*` keys but formats them wrongly
  (`OMNI_DC1,ON,0,0` instead of `OMNI,OMNI_DC1,0,0`); route them to
  `set_omni_position`. Normalise `key`/`action` with `.strip().upper()`;
  clamp `last_value` for speed-capable keys.
- `manual_dosing`: call `validate_duration` before `duration <= 0`
  (non-numeric input raises `TypeError` today).
- `_api_readings`: an un-wrapped `getReadings` payload (no `"getReadings"`
  key) skips orphan-EXT filtering and the `_dosing_standalone` refresh —
  *needs verification* whether any firmware returns a flat dict; if not,
  raise `VioletPayloadError` instead of returning it unfiltered.
- `get_hardware_profile` issues a full `?ALL` poll; add a pure
  `hardware_profile_from(readings)` helper so consumers can reuse their
  snapshot.

`circuit_breaker.py`
- Half-open probe failure logs "OPENED due to {failure_threshold} failures"
  instead of the actual count.
- `get_stats()` "lock held" branch is unreachable in asyncio; remove it and
  the `pytest.skip` guards in `tests/test_api.py` (~lines 1849, 1913).
- `recovery_timeout` is documented as time spent half-open but is a probe
  timeout; fix the docstring.

`utils_rate_limiter.py`
- `request_history`, `_last_known_tokens`, `history_cleanup_interval` are
  written and never read; delete (not in `__all__`).
- `get_stats()["current_tokens"]` is stale (no refill before read); compute
  `min(max_tokens, tokens + elapsed * rate)` locally.
- Four German log lines remain ("Rate Limiter initialisiert", "Warte bis ein
  Token verfügbar ist", "timeout nach", "zurückgesetzt") although the 0.0.38
  changelog says the file was translated.

`utils_sanitizer.py`
- `validate_device_key` upper-cases case-sensitive keys (`pH_value` →
  `PH_VALUE`); validate with `^[A-Za-z0-9_]+$` and return the input unchanged.
- `validate_api_parameter` silently rewrites keys (`"DOSAGE_ph.minus"` →
  `"DOSAGE_phminus"`, codified in a test); raise when `sanitized != param`
  and update the test.
- `sanitize_numeric` turns `"1,5"` into `15.0` and `"1.2.3"` into `0.0`;
  treat a single comma as decimal separator, return the default otherwise.
- `sanitize_string` applies NFKD and silently truncates at 1000 chars for
  config *values* (names with `ü` are decomposed); prefer NFC and raise on
  over-length.
- ~20 German docstrings/log lines remain ("Sanitize einen …", "Gefährliche
  Zeichen entfernt", "Ungültiger …, verwende default"); the language test
  misses them because its word list lacks `einen, verwende, ungültig,
  verfügbar, erlaubt, Wert`. Translate and extend `GERMAN_WORDS`.
- Unused regex constants (`ALPHANUMERIC*`, `NUMERIC`, `INTEGER`, `FLOAT`,
  `DANGEROUS_CHARS`, `COMMAND_INJECTION`) and unused helpers
  (`sanitize_boolean`, `validate_temperature/orp/chlorine`, module-level
  shortcuts); mark deprecated or remove in a minor release.

`readings.py`, `parsers.py`, constants, exports
- `CoverState` accepts only strings while `COVER_STATE_MAP` documents numeric
  states (`"0"`…); `_parse_cover_state("2")` → `None`. *Needs verification*
  of the wire format; if numeric occurs, map through `COVER_STATE_MAP` first.
- `parse_uptime_string` returns 0 if the firmware ever includes seconds;
  delegate to `parse_runtime_string`. `parse_epoch_seconds` should treat
  `ts <= 0` as unset (negative epochs currently produce 1969 dates).
- `VioletReadings.raw` allocates a new `MappingProxyType` per access; cache
  it in `__init__`.
- `OnewireState` docstring says `OW*_state`; the keys are `onewire{n}_state`.
- `validate_duration(True)` returns 1; reject `bool` explicitly.
- `SWITCH_FUNCTIONS` labels are German library-authored text
  ("Erweiterung …", "DMX Szene …", "Schaltregel …"); English them and note the
  change in the changelog.
- Symbols the changelog promised as public are missing from `__init__.py` /
  `__all__`: `validate_duration` (v0.0.36), `RS485_PUMP_NAMES`,
  `RS485_PUMP_MODES` (v0.0.31), plus `DEVICE_STATE_MAPPING`, `STATE_MAP`,
  `SWITCH_FUNCTIONS`, `DOSING_FUNCTIONS`, `DOSING_OUTPUT_INDEX`,
  `DOSING_CONFIG_PREFIX`, `OMNI_POSITIONS`, `SYSTEM_SERVICES`, `LOG_TYPES`,
  `API_PRIORITY_*`, `CircuitBreakerState`, `get_device_state_info`,
  `get_device_mode_from_state`. Add them (additive) and a test asserting
  `set(__all__) >= {...}`.
- Unused constants (`ACTION_MAN`, `QUERY_ALL`, `KEY_MAINTENANCE`,
  `KEY_PVSURPLUS`, `SPECIFIC_FULL_REFRESH_INTERVAL`, `STATE_ICONS`,
  `STATE_COLORS`) need an owner or removal; `API_PRIORITY_HIGH/LOW` should
  actually be used (see priorities above).
- ORP range is 500-900 mV in `_api_model.py`/`utils_sanitizer.py` but 300-925
  in `docs/HA_ADDON_REFERENCE.md`; align with the controller's own limits
  (*needs verification*).

---

## P3 — Tests

- `tox.ini` runs only `tests/test_api.py`; CI runs `pytest -q tests`. Align
  on the latter (or delete `tox.ini`).
- Missing tests: retry/back-off timing and `Retry-After` parsing;
  `VioletTimeoutError`; `VioletAuthError` type (only `match="HTTP 401"` on the
  base class today); `_build_secure_base_url` rejections (userinfo, path, bad
  port, IPv6, underscore); `use_ssl`/`verify_ssl` → `_ssl_param`;
  `set_cover_command`; `get_log(page=-1)`; `get_notifications`,
  `init_update`, `get_update_state`, `get_update_history`,
  `set_dosage_enabled`; `get_specific_readings` happy path;
  `set_switch_state` on `OMNI_DC*`; A5/A6 behaviour; invalid-JSON breaker
  accounting.
- `RateLimiter`: token refill math, `acquire()`, `wait_if_needed` timeout,
  cancellation cleanup. `CircuitBreaker`: OPEN→HALF_OPEN via elapsed timeout
  with a real success, `ignored_exceptions` inside half-open,
  `CancelledError`; `test_negative_recovery_timeout` asserts only
  `cb is not None`.
- `tests/test_readings.py` is largely vacuous (fixtures use keys the model
  does not expose, `assert x is not None`); rewrite against `pump`, `cover`,
  `onewire_*`, `dmx_scenes`, `extension_relays`, `digital_rules`,
  `digital_inputs`, composite `"3|PUMP_ANTI_FREEZE"`, `__repr__`.
- `VioletState`/`get_device_state_info`: composite states, `"[]"`, unknown
  values, `icon`. `InputSanitizer`: truncation/NFKD, traversal,
  `validate_device_key`, `sanitize_boolean`.
- Hygiene: `tests/conftest.py` creates an event loop at import that is never
  closed; `tests/test_mock_server.py` uses a fixed port 8499;
  `tests/test_api_smoke.py` uses `time.sleep(2)` instead of the readiness poll
  `test_mock_server.py` already has; `tests/mock_server.py` serves
  `/setTargetValues` and `/setDosingParameters`, endpoints the controller does
  not have (`_api_dosing.py` says so) — remove; its category filter is
  substring-based while `const_api.py` documents regex + feature-flag
  semantics.

---

## P4 — Documentation, CI, packaging

- `pyproject.toml`: see API-B27. Add a `MANIFEST.in` so the sdist ships a
  runnable `tests/` (with `conftest.py` and `mock_server.py`) or none of it —
  today it ships `test_*.py` without their fixtures.
- `SECURITY.md` support table says only `>= 1.0` is supported; the package is
  0.0.x. Say "latest 0.0.x release".
- `CHANGELOG.md`: sections 0.0.38, 0.0.36, 0.0.35 have no dates; 0.0.38 claims
  `sanitize_device_key()`/`sanitize_api_parameter()` (the functions are
  `InputSanitizer.validate_device_key`/`validate_api_parameter`) and that the
  sanitizer/rate-limiter German was translated (it was not); v0.0.5 claims a
  connect timeout that no longer exists.
- `AGENTS.md`: repository tree omits `_api_dosing.py`, `_api_mixin.py`,
  `_api_model.py`, `_api_outputs.py`, `_api_readings.py`, `_api_system.py`,
  `parsers.py`, `readings.py`, `py.typed` and seven test files; says `api.py`
  holds "all public methods"; says the mock server has "all 15 API endpoints"
  (~40 routes); test command `pytest tests/test_api.py` vs CI's
  `pytest -q tests`; PyPI name spelled `violet-poolcontroller-api` (canonical
  is `violet-poolController-api`).
- `README.md`: `get_readings()` "returns a flattened dictionary" (it returns
  `VioletReadings`, a `Mapping`; `dict(readings)` is needed for JSON);
  hardware detection described via `SYSTEM_dosagemodule_cpu_temperature`,
  `EXT1_1`, `EXT2_1` (it uses `SYSTEM_*_alive_count` since 0.0.12); "source
  code in `api.py`" (methods live in `_api_*.py`); line ~202 "Offizieller
  Shop:" and line ~13 "the official … integration" (the disclaimer says
  unofficial).
- `docs/API_REFERENCE.md` and `docs/violet_standalone_manual.md` are German
  files in the English docs root (`AGENTS.md` exempts only `docs/de/`);
  `API_REFERENCE.md` has ~150 mojibake sequences (`├£`, `├╝` — CP437-decoded
  UTF-8) and header v0.0.23, and `duration`/`last_value` typed `float | None`
  (they are `int | None` since 0.0.36). Regenerate from source; move the
  vendor manual to `docs/de/` or mark it as vendor material.
- `docs/index.html` links `../README.md` (404 on Pages); `docs/de/` has no
  `_Sidebar.md`; `docs/HA_ADDON_REFERENCE.md` is linked from nowhere;
  `docs/_Sidebar.md` links the German standalone manual.
- `.github/workflows/docs.yml` wiki sync (`rsync … docs/ /tmp/wiki/`) pushes
  `index.html`, `de/index.html`, `getReadings_clean.json`, and `docs/de/Home.md`
  collides with `docs/Home.md` because the GitHub wiki resolves pages by file
  name regardless of directory (*needs verification* on the live wiki).
  Exclude `*.html`/`*.json` and rename German pages to `<Page>.de.md` at the
  root, as `violet-hass` does.
- `.github/workflows/*.yml`: `actions/setup-python@v6` while `checkout`/
  `upload-artifact` are v7; Dependabot is monthly+grouped (the integration
  repo is weekly); `release.yml` pushes with `--atomic origin HEAD:main`,
  which needs a branch-protection bypass for `github-actions[bot]`.

## Suggested PR sequence

1. API-A5 → 2. API-A6 → 3. API-B28 → 4. API-B27 + release 0.0.39 (so the
integration can bump its pin) → 5. API-B14 → 6. API-B29 grouped by module →
7. tests → 8. docs/CI.
