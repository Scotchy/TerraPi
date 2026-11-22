"""Run the selected release with private settings and the operator's writable YAML."""
import json
import os
from pathlib import Path

current = Path("/var/lib/terrapi/current").resolve(strict=True)
settings = json.loads((current / "settings.json").read_text())
env = dict(os.environ, MQTT_HOST=settings["host"], MQTT_PORT=str(settings["port"]),
           MQTT_USER=settings["username"], MQTT_PASSWORD=settings["password"],
           TERRAPI_MANAGED_TLS="1", TERRAPI_DEPLOYMENT=current.name)
python = str(current / "venv/bin/python3")
os.execve(python, [python, str(current / "run.py"), "--conf",
                   "/var/lib/terrapi/config/config.yaml"], env)
