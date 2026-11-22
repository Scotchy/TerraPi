"""Exercise controller cycles and dashboard commands with simulated hardware."""
import copy
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import yaml

BACKEND = Path(__file__).resolve().parents[2] / "backend"
sys.path.insert(0, str(BACKEND))
from terrapi.client import MosquittoClient
from terrapi.config_loader import connection_settings
from terrapi.config_manager import public_config, revision, update_config
from terrapi.config_schema import read_config
from terrapi.terra_handler import TerraHandler, planned_mode
from terrapi.thermostat import Thermostat


class ControllerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "config.yaml"
        self.path.write_bytes((BACKEND / "conf/config.yaml").read_bytes())
        self.config = read_config(self.path)
        self.sensor, self.relay, self.client = MagicMock(), MagicMock(), MagicMock()
        self.cooler = MagicMock()
        self.relay.get_state.return_value = True
        self.cooler.get_state.return_value = False
        self.terra = SimpleNamespace(sensors={"dht22": self.sensor},
                                     controls={"light": self.relay, "cooling_system": self.cooler})
        with patch.dict(os.environ, TERRAPI_DEPLOYMENT="17"):
            self.handler = TerraHandler(self.terra, self.client, self.config, self.path)

    def cycle(self, reading, at=100):
        self.sensor.get_data.return_value = reading
        with patch("terrapi.terra_handler.datetime") as clock, patch("terrapi.terra_handler.time.monotonic", return_value=at):
            clock.now.return_value = datetime(2025, 1, 2, 10, 30)
            self.handler.cycle()

    def command(self, topic, payload):
        message = SimpleNamespace(topic=topic, payload=payload.encode())
        self.handler.on_message(None, None, message)
        name, value = self.client.publish.call_args.args
        self.assertEqual(name, "config/status")
        return json.loads(value)

    def test_cycle_reports_once_and_uses_real_thermostat_input(self):
        self.cycle({"temperature": 29.0})
        self.cooler.switch.assert_called_with(True)
        self.client.publish.assert_any_call("terrapi/deploy/controller/health", "17")
        self.assertEqual(sum(c.args[0] == "controls/state" for c in self.client.publish.call_args_list), 1)
        self.terra.sensors["spare"] = MagicMock()
        self.terra.sensors["spare"].get_data.return_value = {"temperature": 25}
        self.client.reset_mock()
        self.cycle(None, 106)
        self.assertNotIn("terrapi/deploy/controller/health", [c.args[0] for c in self.client.publish.call_args_list])
        self.config["modes"]["day"]["cooling_system"] = False
        self.cycle(None, 112)
        self.client.publish.assert_any_call("terrapi/deploy/controller/health", "17")

    def test_transient_and_prolonged_sensor_loss(self):
        for at, reading, expected in ((100, 29, True), (101, None, True), (102, 25, True),
                                      (132, float("nan"), False), (133, 25, False), (134, 29, True)):
            self.cycle({"temperature": reading}, at)
            self.cooler.switch.assert_called_with(expected)

    def test_overnight_and_hysteresis(self):
        plan = self.config["planning"]
        self.assertEqual(planned_mode(plan, datetime(2025, 1, 2, 1, 30)), "night")
        self.assertEqual(planned_mode(plan, datetime(2025, 1, 2, 7, 0)), "day")
        thermostat = Thermostat(target_temp=24, hysteresis=1)
        self.assertEqual([thermostat.compute_state(t) for t in (24, 25, 24, 23)], [False, True, True, False])

    def test_atomic_rename_conflict_and_explicit_off(self):
        request = {"section": "settings", "request_id": "first", "revision": revision(self.config),
                   "data": {key: copy.deepcopy(self.config[key]) for key in ("modes", "planning")}}
        modes, plan = request["data"]["modes"], request["data"]["planning"]
        modes["daytime"] = modes.pop("day")
        self.assertFalse(self.command("config/update", json.dumps(request))["success"])
        plan["periods"]["day"]["mode"] = "daytime"
        status = self.command("config/update", json.dumps(request))
        self.assertTrue(status["success"])
        self.assertEqual(status["request_id"], "first")
        self.assertEqual(read_config(self.path)["modes"], modes)
        self.cycle({"temperature": 29})
        self.cooler.switch.assert_called_with(True)
        self.assertFalse(self.command("config/update", json.dumps(request))["success"])
        plan["periods"]["day"]["mode"] = ""
        self.assertTrue(self.command("config/update", json.dumps({"section": "planning", "data": plan}))["success"])
        self.cycle({"temperature": 29})
        self.cooler.switch.assert_called_with(False)

    def test_manual_and_planning_survive_restart(self):
        self.assertTrue(self.command("planning/active", "0")["success"])
        self.assertTrue(self.command("mode/set", "night")["success"])
        restart = TerraHandler(self.terra, self.client, read_config(self.path), self.path)
        self.assertEqual(restart.get_mode(), "night")
        self.assertTrue(self.command("planning/active", "1")["success"])
        self.assertTrue(read_config(self.path)["planning"]["active"])

    def test_failed_write_preserves_bytes_mode_and_memory(self):
        self.path.chmod(0o640)
        before = self.path.read_bytes()
        with patch("terrapi.config_manager.yaml.safe_dump", side_effect=OSError), self.assertLogs(level="WARNING"):
            self.assertFalse(self.command("planning/active", "0")["success"])
        self.assertTrue(self.handler.config["planning"]["active"])
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        self.command("planning/active", "0")
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o640)

    def test_legacy_empty_schedule_and_strict_updates(self):
        for value in (None, "", "None", "removed"):
            self.config["planning"] = {"active": True, "default_mode": value}
            self.path.write_text(yaml.safe_dump(self.config))
            normalized = read_config(self.path)["planning"]
            self.assertEqual(normalized, {"active": True, "default_mode": "", "periods": {}})
        with self.assertRaises(ValueError):
            update_config(self.path, {"planning": {"active": "yes", "default_mode": ""}}, "")
        with self.assertRaises(ValueError):
            update_config(self.path, {"planning": {"active": True, "default_mode": "unknown"}}, "")

    def test_only_private_connection_fields_expand(self):
        marker = "${TEST_VALUE}"
        self.config["modes"][marker] = {"light": False}
        self.config["planning"]["default_mode"] = marker
        self.config["mqtt"]["password"] = marker
        self.path.write_text(yaml.safe_dump(self.config))
        with patch.dict(os.environ, TEST_VALUE="private-fixture"):
            loaded = read_config(self.path)
            self.assertEqual(connection_settings(loaded)["password"], "private-fixture")
            public = json.dumps(public_config(loaded, marker))
            self.assertNotIn("private-fixture", public)
            self.assertIn(marker, public)

    def test_callbacks_are_installed_before_async_connection_and_resubscribe(self):
        with patch("terrapi.client.mqtt.Client") as factory:
            mqtt = factory.return_value
            client = MosquittoClient(connection_settings(self.config))
            ready = MagicMock()
            mqtt.loop_start.side_effect = lambda: mqtt.on_connect(mqtt, None, {}, 0)
            client.start(MagicMock(), ready)
            mqtt.connect_async.assert_called_once()
            mqtt.connect.assert_not_called()
            mqtt.on_subscribe(mqtt, None, 1, [0] * 4)
            self.assertTrue(client.ready)
            mqtt.on_disconnect(mqtt, None, 1)
            self.assertFalse(client.ready)
            mqtt.on_connect(mqtt, None, {}, 0)
            mqtt.on_subscribe(mqtt, None, 2, [0] * 4)
            self.assertEqual(mqtt.subscribe.call_args.args[0], [(t, 0) for t in client.topics])
            self.assertEqual(mqtt.subscribe.call_count, 2)
            self.assertEqual(ready.call_count, 2)

    def test_failed_attempt_releases_hardware_and_next_attempt_sets_bcm_again(self):
        import importlib.util
        devices = {name: MagicMock() for name in ("adafruit_dht", "board", "RPi", "RPi.GPIO")}
        with patch.dict(sys.modules, devices):
            spec = importlib.util.spec_from_file_location("runner", BACKEND / "run.py")
            runner = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(runner)
            with patch.object(runner, "MosquittoClient") as transport, patch.object(runner, "TerraHandler") as handler:
                handler.return_value.run.side_effect = [RuntimeError("interruption"), KeyboardInterrupt]
                for error in (RuntimeError, KeyboardInterrupt):
                    with self.assertRaises(error):
                        runner.run_once(self.path)
                self.assertEqual(runner.GPIO.setmode.call_count, 2)
                self.assertEqual(runner.GPIO.cleanup.call_count, 2)
                self.assertEqual(devices["adafruit_dht"].DHT22.return_value.exit.call_count, 2)
                self.assertEqual(transport.return_value.disconnect.call_count, 2)
