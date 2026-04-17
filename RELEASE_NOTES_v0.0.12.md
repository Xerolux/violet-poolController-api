## v0.0.12

### Bugfixes

- **Hardware profile detection – phantom EXT2 modules fixed**
  The Violet controller returns relay keys (`EXT1_*`, `EXT2_*`) with a default value of `0` even when the physical extension module is **not** connected. The previous implementation checked whether the key existed and was not `"N/A"`, which incorrectly reported EXT2 as present.

  The new detection uses the controller's module alive-counters (`SYSTEM_ext1module_alive_count`, `SYSTEM_ext2module_alive_count`) for reliable identification. A fallback checks for non-zero `_LAST_ON` timestamps to support older firmware versions that may not expose these counters.

### Installation
```bash
pip install violet-poolController-api==0.0.12
```
