"""Minute snapshots and a bounded, durable MQTT outbox for one terrarium."""
from dataclasses import dataclass, field
import json
import logging
import math
import sqlite3
from threading import Event
import time
from uuid import uuid4


SAMPLE_TOPIC = "terrapi/monitor/samples"
ACK_TOPIC = "terrapi/monitor/ack"
RETENTION_SECONDS = 14 * 24 * 3600
BATCH_SIZE = 120
RETRY_SECONDS = 15


def reading(values, name, minimum, maximum):
    value = values.get(name)
    if type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum:
        return value
    return None


@dataclass
class Batch:
    identifier: str
    timestamps: list
    payload: str
    committed: Event = field(default_factory=Event)
    retry_at: float = 0


class Monitor:
    def __init__(self, path, client):
        self.path = path
        self.client = client
        self.db = None
        self.last_minute = None
        self.batch = None
        self.empty = False
        self.retry_at = 0

    def _open(self):
        self.db = sqlite3.connect(self.path, timeout=0.1)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.execute("PRAGMA wal_autocheckpoint=32")
        self.db.execute("PRAGMA journal_size_limit=131072")
        self.db.execute("""CREATE TABLE IF NOT EXISTS pending (
            ts INTEGER PRIMARY KEY, temperature REAL, humidity REAL,
            power INTEGER, led INTEGER, cooling INTEGER, recovered INTEGER NOT NULL
        )""")

    def acknowledge(self, identifier):
        # Paho calls this from its network thread. Only the control thread uses SQLite.
        batch = self.batch
        if batch is not None and identifier == batch.identifier:
            batch.committed.set()

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    def update(self, sensors, states, power):
        now = time.monotonic()
        if now < self.retry_at:
            return
        try:
            if self.db is None:
                self._open()
            minute = int(time.time()) // 60 * 60
            connected = self.client.is_connected()
            if minute != self.last_minute:
                self._capture(minute, connected, sensors, states, power)
            self._deliver(now, connected)
        except (sqlite3.Error, OSError) as exc:
            # Monitoring failures (including a full/read-only disk) must allow control to continue.
            logging.warning("Terrarium history unavailable: %s. Retrying in %ss.", exc, RETRY_SECONDS)
            self.close()
            self.retry_at = now + RETRY_SECONDS

    def _capture(self, minute, connected, sensors, states, power):
        # Prefer the same DHT22 shown on the live dashboard; support renamed sensors.
        values = sensors.get("dht22", next(iter(sensors.values()), None)) or {}
        cutoff = minute - RETENTION_SECONDS
        with self.db:
            # A Pi can correct its wall clock after boot. Discard invalid future
            # stamps too, so that a bad clock cannot hold up a later batch.
            self.db.execute("DELETE FROM pending WHERE ts <= ? OR ts > ?", (cutoff, minute))
            self.db.execute("INSERT OR IGNORE INTO pending VALUES (?,?,?,?,?,?,?)", (
                minute, reading(values, "temperature", -40, 80), reading(values, "humidity", 0, 100),
                power, states.get("light"), states.get("cooling_system"), not connected,
            ))
        if self.batch and any(ts <= cutoff or ts > minute for ts in self.batch.timestamps):
            self.batch = None
        self.last_minute = minute
        self.empty = False

    def _deliver(self, now, connected):
        if self.batch and self.batch.committed.is_set():
            with self.db:
                self.db.executemany("DELETE FROM pending WHERE ts = ?",
                                    ((ts,) for ts in self.batch.timestamps))
            self.batch = None
        if not connected or self.empty:
            return
        if self.batch is None:
            # Send recent samples first so that a long outage does not delay live status.
            rows = self.db.execute("SELECT * FROM pending ORDER BY ts DESC LIMIT ?", (BATCH_SIZE,))
            samples = []
            for row in rows:
                sample = dict(row)
                for key in ("power", "led", "cooling", "recovered"):
                    if sample[key] is not None:
                        sample[key] = bool(sample[key])
                samples.append(sample)
            if not samples:
                self.empty = True
                return
            identifier = uuid4().hex
            payload = json.dumps({"id": identifier, "samples": samples}, separators=(",", ":"))
            self.batch = Batch(identifier, [s["ts"] for s in samples], payload)
        if now >= self.batch.retry_at:
            self.batch.retry_at = now + RETRY_SECONDS
            self.client.publish(SAMPLE_TOPIC, self.batch.payload, qos=1)
