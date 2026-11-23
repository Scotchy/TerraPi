"""Exercise Pi offline replay through Mosquitto, the recorder process and its HTTP API."""
import base64
from contextlib import ExitStack
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
with patch.dict(sys.modules, {name: MagicMock() for name in ("board", "adafruit_dht", "RPi", "RPi.GPIO")}):
    from terrapi.client import MosquittoClient
    from terrapi import monitoring


def free_ports(count):
    with ExitStack() as stack:
        sockets = [stack.enter_context(socket.socket()) for _ in range(count)]
        for sock in sockets:
            sock.bind(("127.0.0.1", 0))
        return [sock.getsockname()[1] for sock in sockets]


def stop(process):
    if process.poll() is None:
        process.terminate()
        process.wait(timeout=8)


@unittest.skipUnless(shutil.which("mosquitto") and shutil.which("mosquitto_passwd"),
                     "Mosquitto is required for the MQTT integration test")
class MonitoringPipeline(unittest.TestCase):
    def wait_for(self, predicate, description):
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline:
            for process, log in self.processes:
                if process.poll() not in (None, -15, 0):
                    self.fail(f"{description}: {log.read_text()}")
            try:
                if predicate():
                    return
            except OSError:
                pass
            time.sleep(0.05)
        self.fail(f"Timed out waiting for {description}")

    def launch(self, name, command):
        log = self.directory / (name + ".log")
        with log.open("ab") as output:
            process = subprocess.Popen(command, stdout=output, stderr=output, cwd=ROOT)
        self.processes.append((process, log))
        self.addCleanup(stop, process)
        return process

    def start_recorder(self):
        process = self.launch("recorder", [
            sys.executable, "-m", "monitoring.server", "--settings", str(self.settings),
            "--db", str(self.directory / "history.db"), "--host", "127.0.0.1",
            "--port", str(self.http),
        ])

        def healthy():
            with urlopen(f"http://127.0.0.1:{self.http}/health", timeout=1) as response:
                return response.status == 200

        self.wait_for(healthy, "the recorder's MQTT subscription")
        return process

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)
        self.processes = []
        self.native, ws, self.http = free_ports(3)
        passwords = self.directory / "passwords"
        self.password = secrets.token_hex(16)
        for user in ("dashboard", "monitoring", "controller"):
            command = ["mosquitto_passwd", "-b"]
            if not passwords.exists():
                command.append("-c")
            subprocess.run(command + [str(passwords), user, self.password], check=True)
        config = self.directory / "mosquitto.conf"
        config.write_text(f"allow_anonymous false\npassword_file {passwords}\n"
                          f"acl_file {ROOT / 'deploy/vps/acl.example'}\n"
                          f"listener {self.native} 127.0.0.1\nprotocol mqtt\n"
                          f"listener {ws} 127.0.0.1\nprotocol websockets\n")
        # Mosquitto drops privileges when invoked as root; a fixture under /tmp
        # must stay accessible in root-run CI/container environments.
        if os.getuid() == 0:
            config.write_text("user root\n" + config.read_text())
        self.launch("broker", ["mosquitto", "-c", str(config)])
        self.settings = self.directory / "settings.json"
        digest = dict(line.split(":", 1) for line in passwords.read_text().splitlines())["dashboard"]
        self.settings.write_text(json.dumps({
            "mqtt_host": "127.0.0.1", "mqtt_port": ws, "mqtt_user": "monitoring",
            "mqtt_password": self.password, "dashboard_user": "dashboard", "dashboard_hash": digest,
        }))

    def test_restart_and_replay_preserve_connection_and_equipment_history(self):
        recorder = self.start_recorder()
        client = MosquittoClient(dict(host="127.0.0.1", port=self.native, user="controller", password=self.password))
        queue = self.directory / "pi.db"
        device = monitoring.Monitor(queue, client)
        self.addCleanup(lambda: device.close())
        start = (int(time.time()) // 60 - 5) * 60

        def cycle(offset, temperature, humidity, power, light, cooling):
            # Advance only the sampling clock; MQTT and retry deadlines use real time.
            clock = SimpleNamespace(time=lambda: start + 60 * offset, monotonic=time.monotonic)
            with patch.object(monitoring, "time", clock):
                device.update({"dht22": {"temperature": temperature, "humidity": humidity}},
                              {"light": light, "cooling_system": cooling}, power)

        cycle(0, 21, 54, True, True, False)  # Offline; leave the next minute unobserved.
        device.close()
        device = monitoring.Monitor(queue, client)
        client.start(lambda _c, _u, msg: device.acknowledge(msg.payload.decode()), lambda: None)
        self.addCleanup(client.disconnect)
        self.wait_for(client.is_connected, "the controller's connection")
        cycle(2, 23, 58, False, False, False)
        self.wait_for(lambda: device.batch and device.batch.committed.is_set(), "the commit acknowledgment")

        # Restart after the ACK reaches the device but before it removes the samples.
        # The new sender replays both readings under a different batch id.
        stop(recorder)
        device.close()
        device = monitoring.Monitor(queue, client)
        self.start_recorder()
        cycle(3, 25, 62, True, True, True)
        self.wait_for(lambda: device.batch and device.batch.committed.is_set(), "the replay acknowledgment")
        cycle(3, 25, 62, True, True, True)
        with sqlite3.connect(queue) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM pending").fetchone()[0], 0)

        path = f"http://127.0.0.1:{self.http}/terra/api/monitoring/history?start={start}&end={start+240}&points=4"
        with self.assertRaises(HTTPError) as denied:
            urlopen(path, timeout=2)
        self.assertIn(denied.exception.code, (401, 403))
        credentials = base64.b64encode(f"dashboard:{self.password}".encode()).decode()
        request = Request(path, headers={"Authorization": "Basic " + credentials})
        with urlopen(request, timeout=2) as response:
            history = json.load(response)
        summary = history["summary"]
        self.assertEqual([summary[k] for k in ("online", "recovered", "unknown")], [2, 1, 1])
        self.assertEqual(summary["temperature"], {"min": 21, "max": 25, "avg": 23, "count": 3})
        self.assertEqual(summary["humidity"]["avg"], 58)
        self.assertEqual(summary["power"], {"on": 2, "off": 1, "unknown": 1})
        self.assertEqual(summary["led"], {"on": 2, "off": 1, "unknown": 1})
        self.assertEqual(summary["cooling"], {"on": 1, "off": 2, "unknown": 1})
        self.assertEqual([b["unknown"] for b in history["buckets"]], [0, 1, 0, 0])
