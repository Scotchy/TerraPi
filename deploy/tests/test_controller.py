"""Test deployment health against a real control loop with simulated GPIO and sensors."""
from contextlib import redirect_stdout
from datetime import datetime
import io
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
with patch.dict(sys.modules, {name: MagicMock() for name in ("board", "adafruit_dht", "RPi", "RPi.GPIO")}):
    from terrapi import terra_handler
    from terrapi.config_loader import Config
    from terrapi.terra_handler import TerraHandler
    from terrapi.thermostat import Thermostat
    from terrapi import client as mqtt_client
    from terrapi import monitoring


class ControllerHealth(unittest.TestCase):
    def setUp(self):
        self.sensor, self.relay, self.client = MagicMock(), MagicMock(), MagicMock()
        self.client.is_connected.return_value = True
        self.relay.get_state.return_value = True
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        config = Config({
            "planning": {"active": True, "default_mode": "off", "periods": {
                "night": {"start": "22:00", "end": "07:00", "mode": "night"}}},
            "log_interval": 5,
            "modes": {"night": {"lamp": True}, "off": {"lamp": False}},
        })
        terrarium = SimpleNamespace(sensors={"test": self.sensor}, controls={"lamp": self.relay})
        self.handler = TerraHandler(terrarium, self.client, config, str(Path(self.folder.name) / "config.yaml"))
        self.addCleanup(self.handler.close)

    def cycle(self, data):
        self.sensor.get_data.return_value = data
        with patch.object(terra_handler, "datetime") as clock, patch.dict(os.environ, TERRAPI_DEPLOYMENT="17"), \
             patch.object(terra_handler.time, "sleep", side_effect=KeyboardInterrupt), redirect_stdout(io.StringIO()):
            clock.now.return_value = datetime(2025, 1, 2, 1, 30)
            with self.assertRaises(KeyboardInterrupt):
                self.handler.run()

    def test_overnight_cycle_acknowledges_fresh_telemetry(self):
        self.cycle({"temperature": 24.0, "humidity": 55})
        self.relay.switch.assert_called_with(True)
        self.client.publish.assert_any_call("mode", "night")
        self.client.publish.assert_any_call("terrapi/deploy/controller/health", "17")

    def test_missing_sensor_does_not_confirm_deployment(self):
        self.cycle(None)
        self.assertNotIn("terrapi/deploy/controller/health", [c.args[0] for c in self.client.publish.call_args_list])
        batch = self.handler._monitor.batch
        sample, = json.loads(batch.payload)["samples"]
        self.assertIsNone(sample["temperature"])
        self.assertIsNone(sample["led"])
        self.assertTrue(sample["power"])

    def test_monitor_storage_failure_allows_control_and_reporting(self):
        self.handler._monitor.path = Path(self.folder.name) / "missing/queue.db"
        with self.assertLogs(level="WARNING"):
            self.cycle({"temperature": 24.0})
        self.relay.switch.assert_called_with(True)
        self.client.publish.assert_any_call("terrapi/deploy/controller/health", "17")

    def test_off_mode_records_power_and_individual_relay_states(self):
        self.handler._follow_planning = False
        self.handler._current_mode = "off"
        self.handler._terrarium.controls = {"light": self.relay}
        self.relay.get_state.return_value = False
        self.cycle({"temperature": 20.1, "humidity": 55})
        sample, = json.loads(self.handler._monitor.batch.payload)["samples"]
        self.assertIs(sample["power"], False)
        self.assertIs(sample["led"], False)
        self.assertIsNone(sample["cooling"])

    def test_thermostat_hysteresis(self):
        thermostat = Thermostat(target_temp=24, hysteresis=1)
        self.assertEqual([thermostat.compute_state(t) for t in (24, 25, 24, 23)], [False, True, True, False])


class MonitoringOutbox(unittest.TestCase):
    def setUp(self):
        folder = TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.path = Path(folder.name) / "queue.db"
        self.client = MagicMock()
        self.client.is_connected.return_value = False
        self.monitor = monitoring.Monitor(self.path, self.client)
        self.addCleanup(lambda: self.monitor.close())
        self.start = 1800000000

    def update(self, minute, seconds=0):
        moment = self.start + 60 * minute + seconds
        with patch.object(monitoring.time, "time", return_value=moment), \
             patch.object(monitoring.time, "monotonic", return_value=moment):
            self.monitor.update({"dht22": {"temperature": 23.3, "humidity": float("nan")}},
                                {"light": True, "cooling_system": False}, False)

    def test_replays_after_restart_and_only_deletes_after_commit(self):
        self.update(0)
        self.update(0, 1)
        self.client.publish.assert_not_called()
        self.monitor.close()
        self.monitor = monitoring.Monitor(self.path, self.client)
        self.client.is_connected.return_value = True
        self.update(2)
        topic, payload = self.client.publish.call_args.args
        self.assertEqual(topic, monitoring.SAMPLE_TOPIC)
        self.assertEqual(self.client.publish.call_args.kwargs, {"qos": 1})
        batch = json.loads(payload)
        live, recovered = batch["samples"]
        self.assertEqual(live["ts"], self.start + 120)
        self.assertFalse(live["recovered"])
        self.assertEqual(recovered, dict(ts=self.start, temperature=23.3, humidity=None,
                                         power=False, led=True, cooling=False, recovered=True))
        self.monitor.acknowledge("stale-batch")
        self.update(2, monitoring.RETRY_SECONDS)
        self.assertEqual(self.client.publish.call_args.args[1], payload)
        self.monitor.acknowledge(batch["id"])
        self.update(2, monitoring.RETRY_SECONDS + 1)
        self.assertEqual(self.monitor.db.execute("SELECT COUNT(*) FROM pending").fetchone()[0], 0)

    def test_expires_old_minutes_and_replays_in_bounded_batches(self):
        self.update(-monitoring.RETENTION_SECONDS // 60)
        for minute in range(monitoring.BATCH_SIZE + 1):
            self.update(minute)
        self.client.is_connected.return_value = True
        self.update(monitoring.BATCH_SIZE, 5)
        batch = json.loads(self.client.publish.call_args.args[1])
        self.assertEqual(len(batch["samples"]), monitoring.BATCH_SIZE)
        self.monitor.acknowledge(batch["id"])
        self.update(monitoring.BATCH_SIZE, 6)
        last, = json.loads(self.client.publish.call_args.args[1])["samples"]
        self.assertEqual(last["ts"], self.start)

    def test_network_thread_retries_initial_connection_independently(self):
        with patch.object(mqtt_client.mqtt, "Client") as constructor:
            wrapper = mqtt_client.MosquittoClient("localhost", 1883)
            underlying = constructor.return_value
            wrapper.subscribe(monitoring.ACK_TOPIC, qos=1)
            wrapper.connect("test", "test")
            underlying.connect_async.assert_called_once()
            underlying.loop_start.assert_called_once()
            self.assertFalse(wrapper.is_connected())
            underlying.on_connect(underlying, None, {}, 0)
            underlying.subscribe.assert_called_with(monitoring.ACK_TOPIC, qos=1)
            self.assertTrue(wrapper.is_connected())
            underlying.on_disconnect(underlying, None, 1)
            self.assertFalse(wrapper.is_connected())
