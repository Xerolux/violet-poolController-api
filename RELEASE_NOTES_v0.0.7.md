## v0.0.7

### Features
* **Seamless Standalone Firmware Support:** The `getReadings` API responses now automatically parse and flatten the newer, list-based JSON payloads provided by the Violet Standalone controller format. This change is fully backwards-compatible, allowing downstream applications (like Home Assistant) to handle both Base Module and Standalone outputs identically without additional configuration.

### Fixes & Chores
* **GitHub Actions:** Resolved Node 20 deprecation warnings by forcing actions to run on Node 24 (`FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true`).
* Bumped project version to `0.0.7` across `pyproject.toml` and `setup.py`.

### Installation
```bash
pip install violet-poolController-api==0.0.7
```
