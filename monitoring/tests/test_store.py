import os
import random
import sqlite3
import tempfile
import time
import unittest

from monitoring.store import Store


def sample(ts, **changes):
    row = {"ts": ts, "temperature": 24.21, "humidity": 77, "power": True, "led": False,
           "cooling": None, "recovered": False}
    row.update(changes)
    return row


def batch(*rows):
    return {"id": "b" * 32, "samples": list(rows)}


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = os.path.join(self.temp.name, "history.sqlite3")
        self.store = Store(self.path)
        self.hour = (int(time.time()) // 3600 - 12) * 3600

    def test_replay_after_restart_only_fills_previously_missing_minutes(self):
        ts = self.hour
        self.store.ingest(batch(sample(ts), sample(ts + 180, temperature=None, humidity=None)))
        self.assertEqual(self.store.history(ts, ts + 240, 4)["summary"]["unknown"], 2)
        restarted = Store(self.path)
        delayed = batch(sample(ts, recovered=True), sample(ts + 120, temperature=22.73,
                        humidity=None, power=False, led=None, cooling=True, recovered=True))
        self.assertEqual(restarted.ingest(delayed), delayed["id"])
        self.assertEqual(restarted.ingest(delayed), delayed["id"])
        history = restarted.history(ts, ts + 240, 4)
        summary = history["summary"]
        self.assertEqual([summary[k] for k in ("online", "recovered", "unknown")], [2, 1, 1])
        self.assertEqual(summary["temperature"], {"min": 22.73, "avg": 23.47, "max": 24.21, "count": 2})
        self.assertEqual(summary["humidity"]["count"], 1)
        self.assertEqual(summary["power"], {"on": 2, "off": 1, "unknown": 1})
        self.assertEqual(summary["led"], {"on": 0, "off": 2, "unknown": 2})
        self.assertEqual(summary["cooling"], {"on": 1, "off": 0, "unknown": 3})
        self.assertIsNone(history["buckets"][1]["temperature"]["avg"])
        self.assertEqual(history["earliest"], ts)
        self.assertEqual(history["latest"], ts + 180)

    def test_hourly_and_raw_windows_agree_including_partial_boundaries(self):
        rng = random.Random(17)
        rows = [sample(self.hour + i * 60, temperature=rng.randrange(-3, 35) if i % 4 else None,
                       humidity=rng.randrange(100), power=i % 3 == 0, recovered=i % 11 == 0)
                for i in range(540) if i % 7]
        for offset in range(0, len(rows), 120):
            self.store.ingest(batch(*rows[offset:offset + 120]))
        for start_minute, end_minute in [(0, 385), (27, 427), (391, 477), (11, 24)]:
            start = self.hour + start_minute * 60 + 7
            end = self.hour + end_minute * 60 + 20
            raw = self.store.history(start, end, 1200)
            for points in (1, 2, 3, 5, 40, 480):
                wide = self.store.history(start, end, points)
                self.assertEqual(wide["summary"], raw["summary"])
                self.assertLessEqual(len(wide["buckets"]), points)
                self.assertEqual(wide["start"], start - 7)
                self.assertEqual(wide["end"], end + 40)
                previous = raw["start"]
                for bucket in wide["buckets"]:
                    self.assertEqual(previous, bucket["start"])
                    previous = bucket["end"]
                    data = self.store.history(bucket["start"], bucket["end"], 1200)["summary"]
                    self.assertEqual({k: bucket[k] for k in data}, data)
                self.assertEqual(previous, raw["end"])

    def test_prune_and_replay_cannot_resurrect_expired_samples(self):
        old = self.hour - 8 * 86400
        self.store.ingest(batch(sample(old), sample(self.hour)))
        shorter = Store(self.path, history_days=1)
        shorter.ingest(batch(sample(old, recovered=True)))
        result = shorter.history(old, self.hour + 60, 20)
        self.assertEqual(result["summary"]["temperature"]["count"], 1)
        self.assertEqual(result["earliest"], self.hour)
        with sqlite3.connect(self.path) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM hours").fetchone()[0], 1)

    def test_invalid_sample_rolls_back_complete_batch(self):
        for invalid in [sample(self.hour + 1), sample(self.hour, power="no"),
                        sample(self.hour, recovered=0)]:
            with self.assertRaises(ValueError):
                self.store.ingest(batch(sample(self.hour - 60), invalid))
        self.assertIsNone(self.store.history(self.hour - 60, self.hour, 1)["earliest"])

    def test_range_validation_and_sensor_failure(self):
        self.store.ingest(batch(sample(self.hour, temperature=float("nan"), humidity=110)))
        summary = self.store.history(self.hour, self.hour + 1, 1)["summary"]
        self.assertEqual(summary["online"], 1)
        self.assertIsNone(summary["humidity"]["avg"])
        self.assertIsNone(summary["temperature"]["avg"])
        for start, end, points in [(5, 0, 1), (0, 60, 0), (0, 60, 1201), (0, 1825 * 86400 + 1, 2)]:
            with self.assertRaises(ValueError):
                self.store.history(start, end, points)
