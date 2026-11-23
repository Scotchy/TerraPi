"""Apply one local control cycle independently of the MQTT connection."""
from datetime import datetime
import json
import logging
import math
import os
from threading import RLock
import time

import yaml

from .config_manager import public_config, update_config
from .config_schema import read_config
from .thermostat import Thermostat


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def planned_mode(planning, now):
    clock = now.strftime("%H:%M")
    for period in planning["periods"].values():
        start, end = period["start"], period["end"]
        if start <= clock < end or (start > end and (clock >= start or clock < end)):
            return period["mode"]
    return planning["default_mode"]


class TerraHandler:
    def __init__(self, terra, mqtt_client, conf, config_path="conf/config.yaml"):
        self.terra = terra
        self.client = mqtt_client
        self.config = conf
        self.path = config_path
        self.lock = RLock()
        self.thermostats = {}
        self.next_report = 0
        self.deployment = os.environ.get("TERRAPI_DEPLOYMENT")

    def get_mode(self):
        planning = self.config["planning"]
        if planning["active"]:
            return planned_mode(planning, datetime.now())
        return self.config.get("manual_mode", "")

    def publish_config(self):
        with self.lock:
            snapshot = public_config(self.config, self.get_mode())
            self.client.publish("config/full", json.dumps(snapshot))

    def command_changes(self, topic, payload, request):
        if topic == "config/update":
            section = request.get("section")
            data = request.get("data")
            if section in ("modes", "planning"):
                return {section: data}  # Single-section protocol used by existing dashboards.
            if section != "settings" or not isinstance(data, dict) or set(data) != {"planning", "modes"}:
                raise ValueError("Settings must include modes and planning")
            if not isinstance(request.get("revision"), str) or not isinstance(request.get("request_id"), str):
                raise ValueError("A revision and request ID are required")
            return data
        if topic == "planning/active" and payload in ("0", "1"):
            return {"planning": dict(self.config["planning"], active=payload == "1")}
        if topic == "mode/set":
            if self.config["planning"]["active"]:
                raise ValueError("Turn off planning to select a mode")
            if payload not in ("", "None") and payload not in self.config["modes"]:
                raise ValueError("Unknown manual mode")
            return {"manual_mode": "" if payload == "None" else payload}
        raise ValueError("Unknown command")

    def on_message(self, client, userdata, message):
        if message.topic == "config/get":
            self.publish_config()
            return
        with self.lock:
            request = {}
            try:
                payload = message.payload.decode("utf-8")
                if message.topic == "config/update":
                    decoded = json.loads(payload)
                    if not isinstance(decoded, dict):
                        raise ValueError("Expected a settings update")
                    request = decoded
                changes = self.command_changes(message.topic, payload, request)
                self.config = update_config(self.path, changes, self.get_mode(), request.get("revision"))
                status = {"success": True, "message": "Settings saved"}
            except (ValueError, OSError, yaml.YAMLError) as error:
                message_text = str(error) if isinstance(error, ValueError) else "Unable to save settings"
                logging.warning("Settings update rejected (%s)", type(error).__name__)
                status = {"success": False, "message": message_text}
                # An external edit or a failed directory sync can leave a newer file on disk.
                try:
                    self.config = read_config(self.path)
                except (OSError, ValueError, yaml.YAMLError):
                    pass  # Continue controlling with the last validated configuration.
            self.publish_config()
            status.update(request_id=request.get("request_id"), section=request.get("section"))
            self.client.publish("config/status", json.dumps(status))

    def relay_state(self, name, mode, settings, temperature, now):
        if isinstance(settings, bool) or not settings["enabled"]:
            self.thermostats.pop(name, None)
            return settings if isinstance(settings, bool) else False

        # A changed profile starts with a fresh hysteresis state.
        key = (mode, settings["sensor"], settings["action"],
               settings["target_temperature"], settings["hysteresis"])
        previous = self.thermostats.get(name)
        if previous is None or previous[0] != key:
            thermostat = Thermostat(settings["target_temperature"], settings["hysteresis"], settings["action"])
            last_valid = None
        else:
            _, thermostat, last_valid = previous

        if finite(temperature):
            thermostat.compute_state(temperature)
            last_valid = now
        elif last_valid is None or now - last_valid >= self.config.get("sensor_timeout", 30):
            thermostat.set_state(False)
        self.thermostats[name] = (key, thermostat, last_valid)
        return thermostat.relay_state

    def cycle(self):
        readings = {name: sensor.get_data() or {} for name, sensor in self.terra.sensors.items()}
        temperatures = {name: values.get("temperature") for name, values in readings.items()}
        now = time.monotonic()
        with self.lock:
            mode = self.get_mode()
            profile = self.config["modes"].get(mode, {})
            required = set()
            states = {}
            for name, relay in self.terra.controls.items():
                settings = profile.get(name, False)
                temperature = None
                if isinstance(settings, dict) and settings["enabled"]:
                    sensor = settings["sensor"]
                    required.add(sensor)
                    temperature = temperatures.get(sensor)
                relay.switch(self.relay_state(name, mode, settings, temperature, now))
                states[name] = relay.get_state()
            self.client.publish("controls/state", json.dumps(states))
            if now < self.next_report:
                return
            self.next_report = now + self.config["log_interval"]
            for name, values in readings.items():
                for field, value in values.items():
                    if finite(value):
                        self.client.publish(f"sensor/{name}/{field}", str(value))
            self.client.publish("mode", mode or "None")
            valid = {name for name, value in temperatures.items() if finite(value)}
            if self.deployment and self.client.ready and states and valid and required <= valid:
                self.client.publish("terrapi/deploy/controller/health", self.deployment)

    def run(self):
        while True:
            self.cycle()
            time.sleep(1)
