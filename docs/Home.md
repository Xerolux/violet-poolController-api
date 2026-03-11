# Violet Pool Controller API - Wiki

Welcome to the official documentation for the **Violet Pool Controller API** Python library. This library is designed to facilitate asynchronous interaction with your Violet Pool Controller.

## Introduction
The `violet_poolcontroller_api` provides an asynchronous `VioletPoolAPI` class to communicate with the Violet Pool Controller. It uses `aiohttp` for robust and non-blocking HTTP requests.

## Table of Contents

1. [Installation](Installation)
2. [Initialization & Authentication](Initialization-&-Authentication)
3. [Fetching Data](Fetching-Data)
   - All Readings
   - Specific Readings
   - History & Statistics
   - Weather Data
4. [Controlling Devices](Controlling-Devices)
   - Pump Control
   - Climate / Heating Control
   - Light Control
   - Relays & Switches
   - DMX Scenes
   - Digital Input Rules
5. [Dosing & Targets](Dosing-&-Targets)
   - Target Values (pH, ORP, Chlorine)
   - Manual Dosing
   - Dosing Parameters
6. [Configuration & Calibration](Configuration-&-Calibration)
   - Reading Configuration
   - Setting Configuration
   - Calibration Data
7. [Advanced Topics](Advanced-Topics)
   - PV Surplus Mode
   - Test Mode
   - Error Handling
   - Rate Limiting & Circuit Breaker
