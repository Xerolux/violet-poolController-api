# Fetching Data

## All Readings
To retrieve all current sensor and device states:
```python
readings = await api.get_readings()
print(readings)
```

## Specific Readings
To optimize data transfer, you can fetch only specific categories (e.g., `ADC`, `DOSAGE`, `SYSTEM`):
```python
readings = await api.get_specific_readings(["ADC", "SYSTEM"])
```

## History & Statistics
```python
# Fetch history for the last 24 hours
history = await api.get_history(hours=24, sensor="ALL")

# Fetch overall dosing statistics
dosing_stats = await api.get_overall_dosing()

# Fetch output states
output_states = await api.get_output_states()
```

## Weather Data
If configured on the controller, fetch current weather data:
```python
weather = await api.get_weather_data()
```