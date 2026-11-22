"""Reconcile signed releases over HTTPS. MQTT wake messages contain no deployment inputs."""
import base64
import grp
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import pwd
import re
import shutil
import ssl
import subprocess
import tarfile
import tempfile
import threading
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

import paho.mqtt.client as mqtt

ROOT = Path("/var/lib/terrapi")
KEYS = Path("/etc/terrapi")
SERVICE = "terrapi-controller.service"
TOPIC = "terrapi/deploy/controller"
LIMIT = 4 * 1024 * 1024
MAX_PREPARATIONS = 3
MIN_FREE_BYTES = 64 * 1024 * 1024


def sync_directory(path):
    fd = os.open(path, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path, data):
    tmp = tempfile.NamedTemporaryFile(dir=path.parent, delete=False)
    try:
        with tmp:
            tmp.write(data)
            tmp.flush()
            os.fsync(tmp.fileno())
        os.replace(tmp.name, path)
        sync_directory(path.parent)
    finally:
        Path(tmp.name).unlink(missing_ok=True)


def run(*args, data=None, timeout=60):
    return subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          check=True, timeout=timeout).stdout


def fetch(base, name, limit):
    if urlsplit(base).scheme != "https":
        raise ValueError("HTTPS required")
    with urlopen(base.rstrip("/") + "/" + name, timeout=15) as response:
        if urlsplit(response.geturl()).netloc != urlsplit(base).netloc or urlsplit(response.geturl()).scheme != "https":
            raise ValueError("Invalid release origin")
        data = response.read(limit + 1)
    if len(data) > limit:
        raise ValueError("Oversize response")
    return data


def verify(envelope, public_key):
    body = base64.b64decode(envelope["body"], validate=True)
    with tempfile.NamedTemporaryFile() as sig:
        sig.write(base64.b64decode(envelope["signature"], validate=True))
        sig.flush()
        run("openssl", "dgst", "-sha256", "-verify", public_key, "-signature", sig.name, data=body)
    manifest = json.loads(body)
    if manifest["device"] != "controller" or manifest["platform"] != "linux-" + platform.machine():
        raise ValueError("Wrong target")
    if type(manifest["sequence"]) is not int or manifest["sequence"] <= 0:
        raise ValueError("Invalid generation")
    for key in ("bundle", "settings"):
        if not re.fullmatch("[0-9a-f]{64}", manifest[key]):
            raise ValueError("Invalid digest")
    return manifest


def artifact(origin, digest):
    raw = fetch(origin, digest, LIMIT)
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("Artifact verification failed")
    return raw


def unpack(raw, target):
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
        size = 0
        for member in archive:
            if member.isdir() and member.name.rstrip("/") == "terrapi":
                continue
            if not member.isfile() or not re.fullmatch(r"(run\.py|requirements-pi\.txt|terrapi/[A-Za-z_0-9]+\.py)", member.name):
                raise ValueError("Unexpected controller bundle member")
            size += member.size
            if size > LIMIT:
                raise ValueError("Oversize controller release")
            path = target / member.name
            path.parent.mkdir(exist_ok=True)
            with path.open("xb") as dest:
                shutil.copyfileobj(archive.extractfile(member), dest)


def prepare(origin, manifest, release):
    raw = artifact(origin, manifest["bundle"])
    encrypted = artifact(origin, manifest["settings"])
    try:
        clear = run("openssl", "cms", "-decrypt", "-binary", "-inform", "DER",
                    "-recip", KEYS / "recipient.pem", "-inkey", KEYS / "recipient.key", data=encrypted)
    except subprocess.CalledProcessError as error:
        raise ValueError("Invalid encrypted settings") from error
    settings = json.loads(clear)
    if not isinstance(settings, dict):
        raise ValueError("Invalid controller settings")
    if shutil.disk_usage(release.parent).free < MIN_FREE_BYTES:
        raise OSError("Insufficient staging space")
    release.mkdir()
    unpack(raw, release)
    prepare_environment(release)
    (release / "settings.json").write_text(json.dumps(settings))
    gid = grp.getgrnam("terrapi").gr_gid
    # Keep application source, credentials and interpreter root-owned and group-readable.
    for path in [release, *release.rglob("*")]:
        if path.is_symlink():
            continue
        os.chown(path, 0, gid)
        path.chmod(0o750 if path.is_dir() or path.stat().st_mode & 0o100 else 0o640)
    check_candidate(release)
    # Flush the staged tree and its directory entry before journaling activation.
    run("sync", "-f", release)


def check_candidate(release):
    helper = Path(__file__).with_name("check_candidate.py")
    try:
        run("/usr/sbin/runuser", "-u", "terrapi", "--", release / "venv/bin/python3", "-I",
            helper, release, ROOT / "config/config.yaml", timeout=30)
    except subprocess.CalledProcessError as error:
        if error.returncode == 75:
            raise OSError("Broker temporarily unavailable") from error
        raise ValueError("Candidate configuration or credentials failed preflight") from error


def prepare_environment(release):
    # Stage upgrades under an account without GPIO, deployment keys or write access to
    # the running controller. System-provided native packages can satisfy pinned versions.
    builder = pwd.getpwnam("terrapi-build")
    venv = release / "venv"
    venv.mkdir()
    os.chown(venv, builder.pw_uid, builder.pw_gid)
    release.chmod(0o711)
    requirements = release / "requirements-pi.txt"
    requirements.chmod(0o644)
    command = ["/usr/sbin/runuser", "-u", "terrapi-build", "--"]
    run(*command, "/usr/bin/python3", "-m", "venv", "--system-site-packages", venv)
    python = venv / "bin/python"
    validate = [*command, python, "-c", "from importlib.metadata import version; import sys; "
                "sys.exit(any(version(n) != v for n,v in (x.split('==') for x in sys.stdin.read().splitlines())))"]
    pins = requirements.read_bytes()
    try:
        run(*validate, data=pins)
    except subprocess.CalledProcessError:
        run(*command, python, "-m", "pip", "--disable-pip-version-check", "install",
            "--no-cache-dir", "--only-binary=:all:", "-r", requirements, timeout=300)
        run(*validate, data=pins)


def select(release):
    link = ROOT / "next"
    link.unlink(missing_ok=True)
    link.symlink_to(release)
    os.replace(link, ROOT / "current")
    sync_directory(ROOT)


def state():
    path = ROOT / "deployment.json"
    return json.loads(path.read_bytes()) if path.exists() else {"sequence": 0, "result": "healthy"}


def save(sequence, result, **fields):
    record = dict(sequence=sequence, result=result, **fields)
    atomic(ROOT / "deployment.json", json.dumps(record).encode())
    return record


def recover(record):
    if record["result"] == "activating":
        select(Path(record["previous"]))
        run("systemctl", "restart", SERVICE)
        return save(record["sequence"], "failed")
    return record


def reconcile(config, observe):
    record = recover(state())
    origin = config["origin"]
    manifest = verify(json.loads(fetch(origin, "desired.json", 16384)), KEYS / "signing.pub")
    sequence = manifest["sequence"]
    retrying = sequence == record["sequence"] and record["result"] == "retrying"
    if sequence <= record["sequence"] and not retrying:
        return record
    if time.time() >= manifest["expires"]:
        return save(sequence, "failed", reason="expired")
    release = ROOT / "releases" / str(sequence)
    # Only an interrupted preparation can leave this uncommitted directory.
    if release.exists():
        shutil.rmtree(release)
    previous = (ROOT / "current").resolve(strict=True)
    try:
        prepare(origin, manifest, release)
    except (ValueError, tarfile.TarError, EOFError) as error:
        shutil.rmtree(release, ignore_errors=True)
        return save(sequence, "failed", reason=type(error).__name__)
    except (OSError, subprocess.SubprocessError) as error:
        shutil.rmtree(release, ignore_errors=True)
        attempts = record["attempts"] + 1 if retrying else 1
        result = "failed" if attempts >= MAX_PREPARATIONS else "retrying"
        return save(sequence, result, attempts=attempts, reason=type(error).__name__)
    if time.time() >= manifest["expires"]:
        shutil.rmtree(release)
        return save(sequence, "failed", reason="expired")
    record = save(sequence, "activating", previous=str(previous))
    try:
        select(release)
        run("systemctl", "restart", SERVICE)
        if not observe(sequence):
            raise RuntimeError("Missing fresh control cycles")
    except Exception:
        return recover(record)
    return save(sequence, "healthy")


def main():
    os.umask(0o077)
    # Recover locally even if MQTT, DNS or the release server is unavailable at boot.
    recover(state())
    config = json.loads((KEYS / "updater.json").read_bytes())
    wake = threading.Event()
    received = threading.Condition()
    health = {}
    client = mqtt.Client()
    client.tls_set_context(ssl.create_default_context())
    client.username_pw_set(config["username"], config["password"])

    def connected(client, _, flags, rc):
        if rc == 0:
            client.subscribe([(TOPIC + "/wake", 1), (TOPIC + "/health", 0)])
            wake.set()

    def message(client, _, msg):
        if msg.topic == TOPIC + "/wake":
            wake.set()
        elif not msg.retain and msg.payload.isdigit():
            with received:
                seq = int(msg.payload)
                health[seq] = health.get(seq, 0) + 1
                received.notify_all()

    def observe(sequence):
        with received:
            return received.wait_for(lambda: health.get(sequence, 0) >= 2,
                                     timeout=config.get("health_timeout", 90))

    client.on_connect = connected
    client.on_message = message
    client.connect_async(config["host"], int(config["port"]))
    client.loop_start()
    wake.set()
    while True:
        wake.wait(60)
        wake.clear()
        try:
            record = reconcile(config, observe)
        except Exception as error:
            print("Reconciliation deferred:", type(error).__name__, flush=True)
            record = state()
        client.publish(TOPIC + "/status", json.dumps(record), qos=1, retain=True)


if __name__ == "__main__":
    main()
