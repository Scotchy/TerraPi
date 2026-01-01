# TerraPi - AI Coding Instructions

## Project Overview
TerraPi is a **Raspberry Pi terrarium control system** with a unified monorepo structure:
- **Backend** (`/backend/`): Python MQTT-based sensor monitoring and relay control
- **Frontend** (`/frontend/`): React/TypeScript web UI for temperature/humidity display and mode management

## Project Structure
```
TerraPi/
├── backend/
│   ├── run.py              # Entry point
│   ├── conf/
│   │   └── config.yaml     # Unified YAML configuration
│   └── terrapi/            # Core Python package
│       ├── terrarium.py
│       ├── terra_handler.py
│       ├── sensor.py
│       ├── control.py
│       ├── client.py
│       ├── config_loader.py   # Custom YAML loader with env var substitution
│       └── config_manager.py  # Runtime config updates
├── frontend/
│   ├── src/
│   │   └── components/
│   │       ├── terra.tsx       # Main dashboard
│   │       ├── control.tsx     # Relay visualization
│   │       ├── SettingsModal.tsx  # Config editor modal
│   │       ├── Toast.tsx       # Notifications
│   │       └── settings.css    # Settings styles
│   └── package.json
└── .github/
    └── copilot-instructions.md
```

## Architecture

### Data Flow
```
RPi GPIO Sensors (DHT22) → TerraHandler → MQTT Broker ↔ React Frontend
                               ↓
                          RPi Relays (GPIO)
```

### Key Components

**Backend** (`/backend/terrapi/`):
- `terrarium.py`: Initializes sensors and controls from config
- `terra_handler.py`: Main loop collecting sensor data, publishing to MQTT, handling planning/modes
- `sensor.py`: DHT22 sensor wrapper
- `control.py`: GPIO relay wrapper
- `client.py`: MQTT client (Paho)
- `config_loader.py`: Custom YAML loader with `${ENV_VAR}` substitution and dynamic class instantiation
- `config_manager.py`: Runtime configuration updates—validates and persists changes to YAML

**Frontend** (`/frontend/src/components/`):
- `terra.tsx`: Main component with MQTT connection, sensor display, control toggles, planning checkbox, mode selector, settings button
- `control.tsx`: Presentational component for relay state visualization
- `SettingsModal.tsx`: Modal with tabbed interface for editing modes and planning
- `Toast.tsx`: Success/error notification component

### Config System
Single unified YAML configuration file (`backend/conf/config.yaml`) with:
- `mqtt`: Connection settings (host, port, user, password with `${ENV_VAR}` substitution)
- `log_interval`: Seconds between sensor data logs
- `sensors`: Sensor definitions with `type` (class name) and `pin` (GPIO BCM pin)
- `controls`: Control definitions with `type` (class name) and `pin` (GPIO BCM pin)
- `modes`: Mode profiles defining control states (e.g., `day: {light: true, cooling_system: false}`)
- `planning`: Scheduling with `active`, `default_mode`, and `periods` (start/end times and mode)

## MQTT Topics Architecture

**Publishing** (Backend → Frontend):
- `sensor/dht22/temperature`, `sensor/dht22/humidity`: Float values
- `controls/state`: JSON `{"light": bool, "cooling_system": bool}`
- `config/full`: Complete configuration JSON (modes, planning, sensors, controls)
- `config/status`: JSON `{"success": bool, "message": string}` after config update

**Subscribing** (Frontend → Backend):
- `planning/active`: "1" or "0" (enable/disable schedule)
- `mode/set`: String mode name (only applied if planning inactive)
- `config/get`: Request full configuration refresh
- `config/update`: JSON `{"section": "modes"|"planning", "data": {...}}` to update config

## Developer Workflows

### Running Backend
```bash
cd backend
python run.py  # Uses conf/config.yaml by default
# Or specify a different config:
python run.py --conf path/to/config.yaml
```
Requires GPIO access (RPi only) and MQTT broker connectivity.

### Running Frontend
```bash
cd frontend
npm install     # First time only
npm start       # Dev server on http://localhost:3000
npm run build   # Production build
```
Hardcoded MQTT broker: `plantescarnivores.net:9001` (see `frontend/src/components/terra.tsx`)

### Configuration
- Sensors/controls defined in `config.yaml` with `type` (class name) and `pin` (GPIO pin)
- New sensor types extend `Sensor` base class, implement `get_data()` returning dict
- New control types extend `Control` base class, implement `switch_on()`, `switch_off()`, `switch(bool)`
- Backend loops every 1 second, logs every N seconds (configurable via `log_interval`)

## Key Patterns & Conventions

1. **Dynamic Object Initialization**: Config uses `type` field to specify Python class name—adding a new sensor requires:
   - Extending `Sensor` class in `sensor.py`
   - Adding entry in `conf/config.yaml` with `type: YourSensorClass` and appropriate pins
   - Publishing data to matching MQTT topics in `terra_handler.py`

2. **Planning/Mode Logic**: `TerraHandler` reads `planning.active`. If true, uses schedule; if false, respects `mode/set` commands.

3. **Frontend State Management**: React class component (not hooks) with MQTT message handler calling `setState()` on topic match.

4. **GPIO Cleanup**: Backend wraps main loop in try/except calling `GPIO.cleanup()` on exit.

## Integration Points

- **Custom Config Loader**: `config_loader.py` handles YAML loading with `${ENV_VAR}` substitution (no external dependencies)
- **Paho MQTT**: Python backend and `react-paho-mqtt` frontend (similar APIs)
- **Adafruit DHTlib**: For DHT22 sensor reads (requires `board` and `adafruit_dht` modules)
- **RPi.GPIO**: For relay control (hardcoded BCM mode in `run.py`)

## Important Context
- MQTT credentials stored in browser cookies (username/password prompt on first load)
- Frontend hostname hardcoded (`plantescarnivores.net`)—for local development, modify connection URL in `terra.tsx`
- Environment variables for MQTT credentials: `MQTT_USER`, `MQTT_PASSWORD`
- No test files present; manual testing or integration tests recommended before deployment
