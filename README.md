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
export MQTT_USER=your_username
export MQTT_PASSWORD=your_password

# Run the service
python run.py --conf conf/main.yaml
```

**Requirements:** Raspberry Pi with GPIO access, Python 3.7+, MQTT broker

### Frontend

```bash
cd frontend
npm install
npm start
```

Opens at http://localhost:3000

## Configuration

Edit `backend/conf/main.yaml` to configure:
- MQTT broker connection
- Sensor pins (DHT22)
- Control pins (relays)
- Logging interval

Edit `backend/conf/modes.yaml` for environmental profiles.

Edit `backend/conf/planning.yaml` for scheduling.

## Architecture

```
RPi GPIO Sensors → TerraHandler → MQTT Broker ↔ React Frontend
                        ↓
                  GPIO Relays
```

Communication uses MQTT topics for sensor data, control states, and configuration sync.

## License

MIT
