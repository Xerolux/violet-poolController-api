## v0.0.9

- **Feat**: Automatically detect standalone dosing setup from the `getReadings` response shape. The library no longer strictly requires manually setting `dosing_standalone=True` for the standalone units, as it now infers it correctly from the controller's payload format.

### Installation
```bash
pip install violet-poolController-api==0.0.9
```