"""Run as the controller account using the staged interpreter, before taking GPIO."""
import json
import os
from pathlib import Path
import ssl
import sys
from threading import Event

import paho.mqtt.client as mqtt
import yaml


def check(release, path):
    # Older signed bundles use the schema installed alongside this helper.
    candidate = release / "terrapi"
    if (candidate / "config_schema.py").is_file():
        sys.path.insert(0, str(candidate))
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
    from config_schema import private_value, read_config

    config = read_config(path)
    settings = json.loads((release / "settings.json").read_bytes())
    if any(not isinstance(settings.get(k), str) or not settings[k] for k in ("host", "username", "password")):
        raise ValueError("Incomplete connection settings")
    port = settings.get("port")
    if type(port) is not int or not 1 <= port <= 65535:
        raise ValueError("Invalid native port")
    ready = Event()
    result = []
    probe = mqtt.Client()
    env = dict(os.environ, MQTT_HOST=settings["host"], MQTT_PORT=str(port),
               MQTT_USER=settings["username"], MQTT_PASSWORD=settings["password"])
    ca = private_value(config["mqtt"].get("ca_certs"), env)
    probe.tls_set_context(ssl.create_default_context(cafile=(release / ca) if ca else None))
    probe.username_pw_set(settings["username"], settings["password"])

    def connected(client, userdata, flags, rc):
        result.append(rc)
        ready.set()

    probe.on_connect = connected
    probe.connect(settings["host"], port)
    probe.loop_start()
    try:
        if not ready.wait(10):
            raise TimeoutError("Broker did not respond")
        if result[0] in (4, 5):
            raise ValueError("Broker rejected controller credentials")
        if result[0]:
            raise OSError("Broker unavailable")
    finally:
        probe.disconnect()
        probe.loop_stop()


if __name__ == "__main__":
    try:
        check(Path(sys.argv[1]), Path(sys.argv[2]))
    except (ValueError, TypeError, KeyError, yaml.YAMLError, ssl.SSLCertVerificationError, FileNotFoundError):
        sys.exit(2)
    except OSError:
        sys.exit(75)
