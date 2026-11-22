# TerraPi contributor guide

TerraPi runs a Python controller on a Raspberry Pi and a React dashboard over MQTT. Start the controller with `cd backend && python run.py --conf conf/config.yaml`. The supported managed device is a 32-bit ARMv7 Pi on Python 3.9. Local relay control starts even if the broker is offline.

## Controller

- `backend/terrapi/config_schema.py` validates the live YAML for startup, edits and release preflight. Keep this module independent of GPIO.
- `terrarium.py` constructs the sensor and control classes named in YAML. Register resource cleanup as devices are acquired. The controller uses BCM pin numbering.
- `terra_handler.py` applies local-time schedules, including overnight periods, and publishes one relay-state snapshot per cycle. The thermostat retains its last output during transient misses and switches off at the configured timeout.
- `config_manager.py` validates both modes and planning together, checks the editor revision and atomically replaces the private live YAML. Resolve private MQTT placeholders only when opening a connection. Keep public fields literal.

## Dashboard protocol

The React dashboard uses `paho-mqtt` directly. Production connects to the same-origin WebSocket route at `/terra/mqtt`. Credentials live in the active connection. For local development, set `REACT_APP_DEV_MQTT_URL`.

- The Pi publishes `sensor/<name>/<measurement>`, `controls/state`, `mode` and `config/full`. The public snapshot includes the editable settings, sensor and control types, current mode and revision.
- The browser requests a snapshot with `config/get`. It saves both sections in a `config/update` message with `section: "settings"`, `data: {modes, planning}`, `revision` and `request_id`. The Pi answers on `config/status` with the matching ID and broadcasts the accepted snapshot.
- Legacy single-section updates and `planning/active` commands remain supported on the controller. `mode/set` applies in manual mode. Both planning and manual selections persist across restarts. An empty selection switches all relays off.

## Verification

Run `python -m unittest discover -s deploy/tests -v` with PyYAML and Paho MQTT 1.6.1 installed. The controller tests simulate hardware, clock and network callbacks. In `frontend`, run `npm ci`, `npm test -- --watchAll=false --runInBand` and `npm run build` on Node 22. The React tests drive the dashboard with a simulated MQTT client.

CI also builds both images and runs `bash deploy/tests/containers.sh` on an isolated Docker network. The smoke test checks dashboard assets, both broker transports, the proxied WebSocket path and MQTT exchanges under the example roles. Production setup, rollback and Pi-specific verification are in [the deployment guide](../deploy/README.md).
