"""Authenticated history API and MQTT recorder for one TerraPi controller."""
import argparse
import base64
import binascii
import hashlib
import hmac
import json
import logging
import sqlite3
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

import paho.mqtt.client as mqtt

from .store import Store

SAMPLES = "terrapi/monitor/samples"
ACK = "terrapi/monitor/ack"
HISTORY = "/terra/api/monitoring/history"


class DashboardLogin:
    """Verify the selected dashboard account against its Mosquitto PBKDF2 record."""
    def __init__(self, username, encoded):
        empty, algorithm, iterations, salt, digest = encoded.split("$")
        if empty or algorithm != "7" or not username:
            raise ValueError("Expected Mosquitto PBKDF2 dashboard credentials")
        self.username = username.encode()
        self.iterations = int(iterations)
        self.salt = base64.b64decode(salt, validate=True)
        self.digest = base64.b64decode(digest, validate=True)
        if not self.salt or len(self.digest) != 64 or not 1 <= self.iterations <= 10000000:
            raise ValueError("Invalid dashboard password hash")

    def allows(self, header):
        scheme, _, token = (header or "").partition(" ")
        if scheme.lower() != "basic" or len(token) > 4096:
            return False
        try:
            username, password = base64.b64decode(token, validate=True).split(b":", 1)
        except (ValueError, binascii.Error):
            return False
        if not hmac.compare_digest(username, self.username):
            return False
        digest = hashlib.pbkdf2_hmac("sha512", password, self.salt, self.iterations)
        return hmac.compare_digest(digest, self.digest)


class Recorder:
    def __init__(self, store, settings):
        self.store = store
        self.subscribed = threading.Event()
        # The controller's durable queue retains each batch until our application
        # ACK. A clean broker session avoids a second disk queue on the VPS.
        self.client = mqtt.Client(client_id="terrapi-history", transport="websockets")
        self.client.username_pw_set(settings["mqtt_user"], settings["mqtt_password"])
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message
        self.client.connect_async(settings.get("mqtt_host", "broker"), settings.get("mqtt_port", 9002))

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            client.subscribe(SAMPLES, qos=1)
        else:
            logging.warning("Recorder broker login failed (code %s)", rc)

    def on_disconnect(self, client, userdata, rc):
        self.subscribed.clear()

    def on_subscribe(self, client, userdata, mid, granted_qos):
        if granted_qos == (1,) or granted_qos == [1]:
            self.subscribed.set()
        else:
            logging.warning("Recorder subscription refused")

    def on_message(self, client, userdata, message):
        try:
            if message.topic != SAMPLES or len(message.payload) > 65536:
                return
            batch_id = self.store.ingest(json.loads(message.payload))
        except (ValueError, OverflowError, RecursionError):
            logging.warning("Invalid monitoring batch")
            return
        except sqlite3.Error:
            logging.exception("Could not persist monitoring batch")
            return
        client.publish(ACK, batch_id, qos=1)


class HistoryServer(ThreadingHTTPServer):
    def __init__(self, address, store, login, recorder):
        super().__init__(address, HistoryHandler)
        self.store, self.login, self.recorder = store, login, recorder
        self.last_prune = time.monotonic()

    def service_actions(self):
        if time.monotonic() - self.last_prune >= 3600:
            self.last_prune = time.monotonic()
            try:
                self.store.prune()
            except sqlite3.Error:
                logging.exception("Could not prune monitoring history")


class HistoryHandler(BaseHTTPRequestHandler):
    def reply(self, status, data):
        body = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == "/health":
            ok = self.server.recorder.subscribed.is_set()
            self.reply(200 if ok else 503, {"connected": ok})
            return
        if url.path != HISTORY:
            self.reply(404, {"error": "Unknown route"})
            return
        if not self.server.login.allows(self.headers.get("Authorization")):
            self.reply(401, {"error": "Dashboard login required"})
            return
        try:
            query = parse_qs(url.query, max_num_fields=3, strict_parsing=True)
            start, end = int(query["start"][0]), int(query["end"][0])
            points = int(query.get("points", ["480"])[0])
            history = self.server.store.history(start, end, points)
        except (KeyError, ValueError, OverflowError):
            self.reply(400, {"error": "Invalid time range or resolution"})
            return
        except sqlite3.Error:
            logging.exception("Could not read monitoring history")
            self.reply(503, {"error": "History temporarily unavailable"})
            return
        self.reply(200, history)

    def log_request(self, *args):
        # The dashboard polls while open. Avoid filling container logs with successes.
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", default="/run/monitoring/settings.json")
    parser.add_argument("--db", default="/data/history.sqlite3")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8081)
    args = parser.parse_args()
    with open(args.settings, encoding="utf-8") as config:
        settings = json.load(config)
    login = DashboardLogin(settings["dashboard_user"], settings["dashboard_hash"])
    store = Store(args.db, settings.get("history_days", 1825))
    recorder = Recorder(store, settings)
    with HistoryServer((args.host, args.port), store, login, recorder) as server:
        recorder.client.loop_start()
        try:
            server.serve_forever()
        finally:
            recorder.client.disconnect()
            recorder.client.loop_stop()


if __name__ == "__main__":
    main()
