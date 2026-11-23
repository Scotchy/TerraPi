# TerraPi

Raspberry Pi terrarium control system with environmental monitoring and automated scheduling.

## Features

- 🌡️ **Temperature & Humidity Monitoring** - DHT22 sensor readings via GPIO
- 💡 **Relay Control** - Automated light and cooling system management
- 📅 **Planning Mode** - Time-based scheduling for environmental profiles
- 🌐 **Web Interface** - Real-time dashboard via MQTT WebSocket
- **Monitoring history** — Temperature, humidity, connection quality and equipment runtime, with minute detail and up to five years of history.

## Project Structure

```
TerraPi/
├── backend/           # Python MQTT sensor/control service
│   ├── run.py         # Entry point
│   ├── conf/          # YAML configuration files
│   └── terrapi/       # Core Python package
├── frontend/          # React TypeScript web UI
│   ├── src/           # Source components
│   └── package.json
├── monitoring/        # VPS MQTT recorder, SQLite store and history API
└── .github/           # AI coding instructions
```

## Quick Start

### Backend (Raspberry Pi)

```bash
cd backend

# Set MQTT credentials
export MQTT_HOST=broker.example.invalid
export MQTT_USER=your_username
export MQTT_PASSWORD=your_password

# Run the service
python run.py --conf conf/config.yaml
```

**Requirements:** Raspberry Pi with GPIO access, Python 3.9 on the supported managed Pi, MQTT broker

### Frontend

```bash
cd frontend
npm install
npm start
```

Opens at http://localhost:3000. For local development, set `REACT_APP_DEV_MQTT_URL` to a WebSocket URL for your development broker. The browser can read this URL. Supply credentials through the login screen.

## Monitoring history

Open **Monitoring** at the top right of the live controls. Bookmark `/terra/#monitoring` to open recorded history during a broker outage. Choose a preset or enter a custom time range. Drag across a chart to zoom, use the arrows to move through time, or turn on **Follow latest** to track the most recent complete minute. The charts share a time axis. Zooming in retrieves finer detail from the recorder.

Green indicates a connected minute or an active device. Grey indicates a reported off state. Orange marks readings captured while the Pi was disconnected and recovered later. Red marks a minute with missing evidence. The terrarium power row follows the controller's operating mode. LED and cooling rows show their individual relay states. Runtime is estimated from one sample per minute.

The Pi keeps up to 14 days of pending samples and retries until the recorder confirms a database commit. The VPS retains minute samples and compact hourly statistics in a persistent volume. A five-year test with 2.63 million samples used about 43 MiB for the database after checkpointing. Retention can be shortened with `history_days`.

For local development, install `paho-mqtt==1.6.1` in a Python environment and run the recorder from the repository root. The React development server proxies history requests to port 8081.

```sh
python -m monitoring.server --host 127.0.0.1 --settings /path/to/dev-settings.json --db /path/to/history.sqlite3
```

Use a private settings file with `mqtt_host`, `mqtt_port` (the broker's local WebSocket listener), `mqtt_user`, and `mqtt_password` for the collector. Set `dashboard_user` to the browser login and `dashboard_hash` to that user's Mosquitto PBKDF2 password hash. The production deployment generates the recorder settings from environment secrets. [Deployment guide](deploy/README.md)

## Configuration

Edit `backend/conf/config.yaml` to configure:
- MQTT broker connection
- Sensor pins (DHT22)
- Control pins (relays)
- Logging interval

The same file contains the mode profiles and schedule. A missing thermostat sample holds the current output for up to `sensor_timeout` seconds (default 30). A longer gap switches the output off until a valid reading calls for it again. The dashboard shows temperature and humidity from the first configured sensor. Settings and manual selections survive controller restarts.

Sign in for each browser session. The dashboard clears cookies and biometric password copies left by older versions. Its status indicates when the broker or controller stops reporting.

## Architecture

```
RPi GPIO Sensors → TerraHandler → MQTT Broker ↔ React Frontend
                        ↓
                  GPIO Relays
```

The Pi publishes live sensor data and control states over MQTT. The VPS recorder consumes timestamped monitoring batches and serves authenticated history queries through the frontend's same-origin HTTP route.

## Deployment

See the [CI/CD and production setup guide](deploy/README.md) for Docker deployment, private GitHub Environment Secrets, Raspberry Pi releases and rollback.

## License

MIT
