# TerraPi

Raspberry Pi terrarium control system with environmental monitoring and automated scheduling.

## Features

- 🌡️ **Temperature & Humidity Monitoring** - DHT22 sensor readings via GPIO
- 💡 **Relay Control** - Automated light and cooling system management
- 📅 **Planning Mode** - Time-based scheduling for environmental profiles
- 🌐 **Web Interface** - Real-time dashboard via MQTT WebSocket

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

Communication uses MQTT topics for sensor data, control states, and configuration sync.

## Deployment

See the [CI/CD and production setup guide](deploy/README.md) for Docker deployment, private GitHub Environment Secrets, Raspberry Pi releases and rollback.

## License

MIT
