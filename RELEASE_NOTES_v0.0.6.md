## v0.0.6 - Standalone Dosing

### Feature

* Added standalone dosing mode via the new `dosing_standalone` API initialization parameter.
* In standalone mode, `DOS_*` operations remain available while base-module-dependent functions (for example pump/light/backwash) are blocked.

### Reliability

* Blocked operations now return explicit, user-facing error messages instead of failing implicitly.

### Tests and Documentation

* Added standalone-focused tests for manual dosing behavior and blocked base-module actions.
* Updated `README.md` and related docs to describe standalone initialization and behavior.

Installation:
```bash
pip install violet-poolController-api==0.0.6
```
