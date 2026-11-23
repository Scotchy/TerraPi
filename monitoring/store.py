"""Minute-resolution terrarium history, with exact hourly aggregates for broad queries."""
import contextlib
import math
import re
import sqlite3
import time

MINUTE = 60
MINUTES_PER_HOUR = 60
RETENTION_MINUTES = 5 * 365 * 24 * 60
MAX_POINTS = 1200
MAX_BATCH = 120

# One byte stores the three nullable states (00 unknown, 01 off, 10 on)
# and the offline-recovery flag. Sensor values are stored as integer hundredths.
DEVICES = ("power", "led", "cooling")
METRICS = ("temperature", "humidity")
COLUMNS = ["observed", "recovered"]
RAW_AGGREGATES = ["count(*)", "sum((flags >> 6) & 1)"]
for metric in METRICS:
    for operation in ("min", "max", "sum", "count"):
        COLUMNS.append(f"{metric}_{operation}")
        RAW_AGGREGATES.append(f"{operation}({metric})")
for shift, device in enumerate(DEVICES):
    for name, value in (("on", 2), ("off", 1)):
        COLUMNS.append(f"{device}_{name}")
        RAW_AGGREGATES.append(f"sum(((flags >> {shift * 2}) & 3) = {value})")

RAW_SQL = ", ".join(RAW_AGGREGATES)
HOUR_SQL = ", ".join(
    f"min({col})" if col.endswith("_min") else
    f"max({col})" if col.endswith("_max") else f"sum({col})" for col in COLUMNS
)


def parse_batch(payload, now):
    if not isinstance(payload, dict) or not isinstance(payload.get("id"), str):
        raise ValueError("Invalid batch")
    if not re.fullmatch("[0-9a-f]{32}", payload["id"]):
        raise ValueError("Invalid batch id")
    samples = payload.get("samples")
    if not isinstance(samples, list) or not 1 <= len(samples) <= MAX_BATCH:
        raise ValueError("Invalid batch size")
    rows = []
    for sample in samples:
        if not isinstance(sample, dict):
            raise ValueError("Invalid sample")
        ts = sample.get("ts")
        if type(ts) is not int or ts < 0 or ts % MINUTE or ts > now + MINUTE:
            raise ValueError("Invalid sample timestamp")
        if type(sample.get("recovered")) is not bool:
            raise ValueError("Missing connection status")
        flags = int(sample["recovered"]) << 6
        for i, key in enumerate(DEVICES):
            value = sample.get(key)
            if value is not None:
                if type(value) is not bool:
                    raise ValueError("Invalid equipment state")
                flags |= (1 + int(value)) << (2 * i)
        values = []
        for metric in METRICS:
            value = sample.get(metric)
            if value is not None:
                # Saturated, non-finite or corrupt readings convey no usable
                # climate value. Preserve equipment evidence from that minute.
                if type(value) not in (int, float):
                    raise ValueError("Invalid metric")
                low, high = (0, 100) if metric == "humidity" else (-273.15, 1000)
                value = round(value * 100) if low <= value <= high else None
            values.append(value)
        rows.append((ts // MINUTE, *values, flags))
    return payload["id"], rows


def retention_cutoff(now, retention_minutes):
    # Keep the entire oldest hour so its aggregate and raw source always agree.
    minute = int(now) // MINUTE - retention_minutes
    return minute // MINUTES_PER_HOUR * MINUTES_PER_HOUR


def combine(target, columns):
    """Combine sufficient statistics without averaging averages or losing extrema."""
    for name, value in zip(COLUMNS, columns):
        if value is None:
            continue
        if name.endswith("_min"):
            target[name] = min(target.get(name, value), value)
        elif name.endswith("_max"):
            target[name] = max(target.get(name, value), value)
        else:
            target[name] = target.get(name, 0) + value


def statistics(values, minutes):
    observed = values.get("observed", 0)
    recovered = values.get("recovered", 0)
    result = {"online": observed - recovered, "recovered": recovered, "unknown": minutes - observed}
    for metric in METRICS:
        count = values.get(metric + "_count", 0)
        result[metric] = {
            "min": values[metric + "_min"] / 100 if count else None,
            "max": values[metric + "_max"] / 100 if count else None,
            "avg": round(values[metric + "_sum"] / (100 * count), 3) if count else None,
            "count": count,
        }
    for device in DEVICES:
        on, off = values.get(device + "_on", 0), values.get(device + "_off", 0)
        result[device] = {"on": on, "off": off, "unknown": minutes - on - off}
    return result


class Store:
    def __init__(self, path, history_days=5 * 365):
        if type(history_days) is not int or not 1 <= history_days <= 5 * 365:
            raise ValueError("history_days must be between 1 and 1825")
        self.path = path
        self.retention_minutes = history_days * 24 * 60
        with self.connection() as db:
            db.execute("PRAGMA auto_vacuum=INCREMENTAL")
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("""CREATE TABLE IF NOT EXISTS samples (
                minute INTEGER PRIMARY KEY, temperature INTEGER, humidity INTEGER, flags INTEGER NOT NULL
            )""")
            db.execute(f"""CREATE TABLE IF NOT EXISTS hours (minute INTEGER PRIMARY KEY,
                {", ".join(col + " INTEGER" for col in COLUMNS)})""")
        self.prune()

    @contextlib.contextmanager
    def connection(self):
        with contextlib.closing(sqlite3.connect(self.path, timeout=10)) as db:
            db.execute("PRAGMA wal_autocheckpoint=256")
            db.execute("PRAGMA journal_size_limit=1048576")
            with db:
                yield db

    def prune(self, now=None):
        cutoff = retention_cutoff(time.time() if now is None else now, self.retention_minutes)
        with self.connection() as db:
            while True:
                oldest = db.execute("SELECT min(minute) FROM samples").fetchone()[0]
                if oldest is None or oldest >= cutoff:
                    break
                # Limit WAL growth if an operator shortens several years of history.
                stop = min(cutoff, oldest // 60 * 60 + 7 * 24 * 60)
                with db:
                    for table in ("samples", "hours"):
                        db.execute(f"DELETE FROM {table} WHERE minute < ?", (stop,))
                # Reuse a small number of free pages for new readings. Return
                # larger blocks to the filesystem when shortening retention.
                if db.execute("PRAGMA freelist_count").fetchone()[0] > 256:
                    db.execute("PRAGMA incremental_vacuum(256)").fetchall()

    def ingest(self, payload, now=None):
        now = time.time() if now is None else now
        batch_id, rows = parse_batch(payload, now)
        cutoff = retention_cutoff(now, self.retention_minutes)
        with self.connection() as db:
            touched = set()
            for row in rows:
                if row[0] < cutoff:
                    continue
                added = db.execute("INSERT OR IGNORE INTO samples VALUES (?,?,?,?)", row)
                if added.rowcount:
                    touched.add(row[0] // 60 * 60)
            # Each touched hour reads at most 60 rows, even for a late replay.
            for hour in touched:
                db.execute(f"""INSERT OR REPLACE INTO hours
                    SELECT ?, {RAW_SQL} FROM samples WHERE minute >= ? AND minute < ?""",
                           (hour, hour, hour + 60))
        return batch_id

    def history(self, start, end, points):
        if not (0 <= start < end <= 253402300800 and 1 <= points <= MAX_POINTS):
            raise ValueError("Invalid history range or point count")
        first = start // MINUTE
        stop = (end + MINUTE - 1) // MINUTE
        duration = stop - first
        if end - start > RETENTION_MINUTES * MINUTE:
            raise ValueError("The maximum range is five years")

        width = math.ceil(duration / points)
        if width >= 60:
            width = math.ceil(width / 60) * 60
        # Full interior hourly groups align with UTC; only edge fragments read raw samples.
        anchor = first if points == 1 else first // width * width
        if points > 1 and math.ceil((stop - anchor) / width) > points:
            width = math.ceil(duration / (points - 1))
            if width >= 60:
                width = math.ceil(width / 60) * 60
            anchor = first // width * width

        groups = {}
        with self.connection() as db:
            db.execute("BEGIN")  # All ranges, including the bounds, share one read snapshot.
            earliest = db.execute("SELECT min(minute) FROM samples").fetchone()[0]
            latest = db.execute("SELECT max(minute) FROM samples").fetchone()[0]

            def collect(table, aggregates, left, right):
                if left >= right:
                    return
                sql = f"""SELECT (minute - ?) / ? AS bucket, {aggregates}
                          FROM {table} WHERE minute >= ? AND minute < ? GROUP BY bucket"""
                for row in db.execute(sql, (anchor, width, left, right)):
                    combine(groups.setdefault(row[0], {}), row[1:])

            hour_start, hour_end = (first + 59) // 60 * 60, stop // 60 * 60
            if width < 60 or hour_start >= hour_end:
                collect("samples", RAW_SQL, first, stop)
            else:
                collect("samples", RAW_SQL, first, hour_start)
                collect("hours", HOUR_SQL, hour_start, hour_end)
                collect("samples", RAW_SQL, hour_end, stop)

        buckets, total = [], {}
        for idx, bucket_start in enumerate(range(anchor, stop, width)):
            left, right = max(bucket_start, first), min(bucket_start + width, stop)
            values = groups.get(idx, {})
            combine(total, [values.get(col) for col in COLUMNS])
            buckets.append({"start": left * MINUTE, "end": right * MINUTE,
                            **statistics(values, right - left)})
        return {"start": first * MINUTE, "end": stop * MINUTE, "step": width * MINUTE,
                "earliest": None if earliest is None else earliest * MINUTE,
                "latest": None if latest is None else latest * MINUTE,
                "buckets": buckets, "summary": statistics(total, duration)}
