"""Test deployment health against a real control loop with simulated GPIO and sensors."""
from contextlib import redirect_stdout
from datetime import datetime
import io
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
with patch.dict(sys.modules, {name: MagicMock() for name in ("board", "adafruit_dht", "RPi", "RPi.GPIO")}):
    from terrapi import terra_handler
    from terrapi.config_loader import Config
    from terrapi.terra_handler import TerraHandler
    from terrapi.thermostat import Thermostat


class ControllerHealth(unittest.TestCase):
    def setUp(self):
        self.sensor, self.relay, self.client = MagicMock(), MagicMock(), MagicMock()
        self.relay.get_state.return_value = True
        config = Config({
            "planning": {"active": True, "default_mode": "off", "periods": {
                "night": {"start": "22:00", "end": "07:00", "mode": "night"}}},
            "log_interval": 5,
            "modes": {"night": {"lamp": True}, "off": {"lamp": False}},
        })
        terrarium = SimpleNamespace(sensors={"test": self.sensor}, controls={"lamp": self.relay})
        self.handler = TerraHandler(terrarium, self.client, config)

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

    def test_thermostat_hysteresis(self):
        thermostat = Thermostat(target_temp=24, hysteresis=1)
        self.assertEqual([thermostat.compute_state(t) for t in (24, 25, 24, 23)], [False, True, True, False])
