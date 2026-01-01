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
│   ├── conf/               # YAML configuration
│   │   ├── main.yaml
│   │   ├── modes.yaml
│   │   └── planning.yaml
│   └── terrapi/            # Core Python package
│       ├── terrarium.py
│       ├── terra_handler.py
│       ├── sensor.py
│       ├── control.py
│       ├── client.py
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
- `config_manager.py`: Runtime configuration updates—validates and persists changes to YAML

**Frontend** (`/frontend/src/components/`):
- `terra.tsx`: Main component with MQTT connection, sensor display, control toggles, planning checkbox, mode selector, settings button
- `control.tsx`: Presentational component for relay state visualization
- `SettingsModal.tsx`: Modal with tabbed interface for editing modes and planning
- `Toast.tsx`: Success/error notification component

### Config System
YAML-based with `xpipe.config` (custom config loader):
- `backend/conf/main.yaml`: MQTT connection, sensor/control pin mappings, log interval
- `backend/conf/modes.yaml`: Environmental mode profiles (temperature/humidity targets)
- `backend/conf/planning.yaml`: Time-based scheduling (default mode, active periods)

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
python run.py --conf conf/main.yaml
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
- Sensors/controls added in `main.yaml` with class references: `!obj terrapi.sensor.DHT22`
- New sensor types extend `Sensor` base class, implement `get_data()` returning dict
- New control types extend `Control` base class, implement `switch_on()`, `switch_off()`
- Backend loops every 1 second, logs every N seconds (configurable)

## Key Patterns & Conventions

1. **Dynamic Object Initialization**: YAML uses `!obj` tags to instantiate Python classes—adding a new sensor requires:
   - Extending `Sensor` class in `sensor.py`
   - Adding entry in `conf/main.yaml` with `!obj terrapi.sensor.YourSensor`
   - Publishing data to matching MQTT topics in `terra_handler.py`

2. **Planning/Mode Logic**: `TerraHandler` reads `planning.active()`. If true, uses schedule; if false, respects `mode/set` commands.

3. **Frontend State Management**: React class component (not hooks) with MQTT message handler calling `setState()` on topic match.

4. **GPIO Cleanup**: Backend wraps main loop in try/except calling `GPIO.cleanup()` on exit.

## Integration Points

- **Xpipe Config**: External dependency for YAML loading with environment variable substitution (`!env`)
- **Paho MQTT**: Python backend and `react-paho-mqtt` frontend (similar APIs)
- **Adafruit DHTlib**: For DHT22 sensor reads (requires `board` and `adafruit_dht` modules)
- **RPi.GPIO**: For relay control (hardcoded BCM mode in `run.py` line 7)

## Important Context
- MQTT credentials stored in browser cookies (username/password prompt on first load)
- Frontend hostname hardcoded (`plantescarnivores.net`)—for local development, modify connection URL in `terra.tsx`
- Config files support YAML includes (`!include`) for modular setup
- No test files present; manual testing or integration tests recommended before deployment
