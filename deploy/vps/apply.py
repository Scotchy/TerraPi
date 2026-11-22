#!/usr/bin/python3
"""Installed VPS entry point for the restricted production SSH key."""
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urljoin, urlsplit
from urllib.request import urlopen

ROOT = Path("/var/lib/terrapi-deploy")
TOOLS = Path(__file__).resolve().parent


def atomic(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
        temp.write(data)
        temp.flush()
        os.fsync(temp.fileno())
    os.replace(temp.name, path)


def docker(*args, env=None, data=None, capture=False):
    result = subprocess.run(["docker", *map(str, args)], env=env, input=data, check=True,
                            stdout=subprocess.PIPE if capture else subprocess.DEVNULL)
    return result.stdout.strip().decode() if capture else None


def image(ref, name):
    namespace = (TOOLS / "image-namespace").read_text().strip()
    repo = "eclipse-mosquitto" if name == "broker" else namespace + "/" + name
    if not re.fullmatch(re.escape(repo) + r"@sha256:[0-9a-f]{64}", ref):
        raise ValueError("Unexpected registry image")
    return ref


def port(value):
    if type(value) is not int or not 1 <= value <= 65535:
        raise ValueError("Invalid port")
    return str(value)


def apply(service, config):
    docker("compose", "--project-directory", ROOT, "-f", TOOLS / (service + ".yaml"),
           "up", "-d", "--no-deps", service, env=dict(os.environ, **config))


def monitor(job, action):
    ref = image(job["release"]["notifier"], "notifier")
    docker("run", "--rm", "-i", "--network", "host", ref, action,
           data=json.dumps(dict(job["monitor"], sequence=job["sequence"])).encode())


def activate(service, env, check):
    state = ROOT / (service + ".json")
    pending = ROOT / (service + ".pending")
    old = json.loads(state.read_bytes()) if state.exists() else None
    if pending.exists() and old:
        apply(service, old)
        pending.unlink()
    atomic(pending, b"activating")
    try:
        apply(service, env)
        for attempt in range(8):
            try:
                check()
                break
            except Exception:
                if attempt == 7:
                    raise
                time.sleep(2)
        atomic(state, json.dumps(env).encode())
        pending.unlink()
    except Exception:
        if old:
            apply(service, old)
        else:
            docker("compose", "--project-directory", ROOT, "-f", TOOLS / (service + ".yaml"),
                   "stop", service, env=dict(os.environ, **env))
        pending.unlink()
        raise


def dashboard_assets(url):
    with urlopen(url, timeout=6) as response:
        html = response.read().decode()
    assets = re.findall(r'(?:src|href)="(/terra/static/[^"]+)"', html)
    if not any(s.endswith(".js") for s in assets) or not any(s.endswith(".css") for s in assets):
        raise ValueError("Missing dashboard assets")
    for asset in assets:
        with urlopen(urljoin(url, asset), timeout=6) as response:
            if response.headers.get_content_type() == "text/html":
                raise ValueError("Invalid dashboard asset")
    return set(assets)


def frontend(job):
    ref = image(job["release"]["frontend"], "frontend")
    docker("pull", ref)
    web = port(job["web_port"])
    if (ROOT / "frontend.json").exists():
        old = json.loads((ROOT / "frontend.json").read_text())
        cid = docker("compose", "--project-directory", ROOT, "-f", TOOLS / "frontend.yaml",
                     "ps", "-q", "frontend", env=dict(os.environ, **old), capture=True)
        if cid:
            target = ROOT / "previous/terra/static"
            target.mkdir(parents=True, exist_ok=True)
            target.parent.chmod(0o755)
            target.chmod(0o755)
            docker("cp", cid + ":/usr/share/nginx/html/terra/static/.", target)

    def check():
        assets = dashboard_assets("http://127.0.0.1:" + web + "/terra/")
        public = job.get("dashboard_url")
        if public and (urlsplit(public).scheme != "https" or dashboard_assets(public) != assets):
            raise ValueError("Public route did not serve the selected release")
    activate("frontend", {"FRONTEND_IMAGE": ref, "WEB_PORT": web}, check)


def broker(job):
    ref = image(job["release"]["broker"], "broker")
    docker("pull", ref)
    settings = Path(tempfile.mkdtemp(prefix="broker-", dir=ROOT))
    # Eclipse Mosquitto runs as UID/GID 1883 after dropping privileges.
    os.chown(settings, 0, 1883)
    settings.chmod(0o750)
    for name in ("chain.pem", "key.pem", "passwords", "acl"):
        file = settings / name
        file.write_text(job["files"][name].rstrip() + "\n")
        os.chown(file, 0, 1883)
        file.chmod(0o440)
    shutil.copyfile(TOOLS / "mosquitto.conf", settings / "mosquitto.conf")
    (settings / "mosquitto.conf").chmod(0o444)
    data, logs = (job["volumes"][key] for key in ("data", "logs"))
    if job["volumes"] != json.loads((TOOLS / "allowed-volumes.json").read_bytes()):
        raise ValueError("Volumes do not belong to this project")
    for volume in (data, logs):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", volume):
            raise ValueError("Invalid volume")
    cfg = {"BROKER_IMAGE": ref, "BROKER_CONFIG_DIR": str(settings), "DATA_VOLUME": data,
           "LOG_VOLUME": logs, "NATIVE_PORT": port(job["monitor"]["native_port"]),
           "WS_PORT": port(job["monitor"]["ws_port"])}
    activate("broker", cfg, lambda: monitor(job, "check"))


def controller(job):
    public = ROOT / "public"
    envelope = job["envelope"]
    body = json.loads(base64.b64decode(envelope["body"], validate=True))
    generation = job["sequence"]
    if type(generation) is not int or generation <= 0 or body["sequence"] != generation:
        raise ValueError("Invalid deployment generation")
    desired = public / "desired.json"
    if desired.exists():
        previous = json.loads(base64.b64decode(json.loads(desired.read_bytes())["body"]))
        if previous["sequence"] > generation:
            raise ValueError("Superseded deployment")
        if previous["sequence"] == generation:
            # Retrying a delayed acknowledgment uses the exact original signed request.
            monitor(job, "notify")
            return
    for key in ("bundle", "settings"):
        raw = base64.b64decode(job[key], validate=True)
        digest = hashlib.sha256(raw).hexdigest()
        if digest != body[key]:
            raise ValueError("Artifact digest mismatch")
        atomic(public / digest, raw)
        (public / digest).chmod(0o644)
    atomic(desired, json.dumps(envelope).encode())
    desired.chmod(0o644)
    monitor(job, "notify")


def main():
    os.umask(0o077)
    job = json.loads(sys.stdin.buffer.read(16 * 1024 * 1024))
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (ROOT / "deploy.lock").open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for name in ("public", "previous"):
            directory = ROOT / name
            directory.mkdir(exist_ok=True)
            directory.chmod(0o755)
        # Read-only release mounts and a project-specific Docker network.
        check = subprocess.run(["docker", "network", "inspect", "terrapi-app"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if check.returncode:
            docker("network", "create", "terrapi-app")
        with tempfile.TemporaryDirectory() as registry:
            os.environ["DOCKER_CONFIG"] = registry
            docker("login", "ghcr.io", "-u", job["registry"]["username"], "--password-stdin",
                   data=job["registry"]["token"].encode())
            if job["component"] in ("controller", "broker"):
                docker("pull", image(job["release"]["notifier"], "notifier"))
            {"controller": controller, "broker": broker, "frontend": frontend}[job["component"]](job)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        subprocess.run(["logger", "-t", "terrapi-deploy", "Deployment failed: " + type(error).__name__])
        if isinstance(error, subprocess.CalledProcessError) and error.returncode == 75:
            sys.exit(75)
        sys.exit(1)
