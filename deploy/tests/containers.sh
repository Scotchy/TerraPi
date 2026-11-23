#!/usr/bin/env bash
# Local synthetic credentials only. Nothing binds a host port or contacts production.
set -euo pipefail
scratch=$(mktemp -d)
network="terrapi-test-$(basename "$scratch" | tr '[:upper:].' '[:lower:]-')"
export FRONTEND_IMAGE=terrapi-ci/frontend:test WEB_PORT=0
export MONITORING_IMAGE=terrapi-ci/monitoring:test MONITORING_SETTINGS_FILE="$scratch/monitoring.json"
export BROKER_IMAGE DATA_VOLUME="$network-data" LOG_VOLUME="$network-logs" BROKER_CONFIG_DIR="$scratch"
BROKER_IMAGE=$(cat deploy/vps/broker-image)
export NATIVE_PORT=127.0.0.1:0 WS_PORT=127.0.0.1:0
compose=(docker compose -p "$network" --project-directory "$scratch"
    -f "$PWD/deploy/vps/frontend.yaml" -f "$PWD/deploy/vps/broker.yaml"
    -f "$PWD/deploy/vps/monitoring.yaml" -f "$scratch/network.yaml")
clean() {
    "${compose[@]}" down --volumes >/dev/null 2>&1 || true
    docker volume rm "$DATA_VOLUME" "$LOG_VOLUME" >/dev/null 2>&1 || true
    docker network rm "$network" >/dev/null 2>&1 || true
    rm -rf "$scratch"
}
trap clean EXIT
printf 'networks:\n  app:\n    name: %s\n' "$network" > "$scratch/network.yaml"
mkdir "$scratch/public" "$scratch/previous"
cp deploy/vps/mosquitto.conf "$scratch"
docker network create "$network" >/dev/null
docker volume create "$DATA_VOLUME" >/dev/null
docker volume create "$LOG_VOLUME" >/dev/null
openssl req -x509 -newkey rsa:2048 -nodes -days 1 -subj /CN=broker \
    -addext 'subjectAltName=DNS:broker' -keyout "$scratch/key.pem" -out "$scratch/chain.pem" 2>/dev/null
cp deploy/vps/acl.example "$scratch/acl"
printf '\nuser fixture\ntopic readwrite ci/#\ntopic readwrite terrapi/deploy/controller/#\n' >> "$scratch/acl"
# Run as the current user so the synthetic files can be removed after the test.
docker run --rm --user "$(id -u):$(id -g)" -v "$scratch:/test" --entrypoint mosquitto_passwd \
    "$BROKER_IMAGE" -b -c /test/passwords fixture fixture-test-only
for role in monitoring dashboard; do
    docker run --rm --user "$(id -u):$(id -g)" -v "$scratch:/test" --entrypoint mosquitto_passwd \
        "$BROKER_IMAGE" -H sha512-pbkdf2 -b /test/passwords "$role" "$role-test-only"
done
PYTHONPATH=deploy/ci python3 - "$scratch" <<'PY'
import json, sys
from pathlib import Path
from dispatch import monitoring_settings
root = Path(sys.argv[1])
settings = monitoring_settings({"mqtt_user": "monitoring", "mqtt_password": "monitoring-test-only",
                                "dashboard_user": "dashboard"}, (root / "passwords").read_text())
(root / "monitoring.json").write_text(json.dumps(settings))
PY
chmod 755 "$scratch"
chmod 644 "$scratch"/{chain.pem,key.pem,passwords,acl,mosquitto.conf,monitoring.json}
"${compose[@]}" up -d
docker run --rm -i --network "$network" -v "$scratch/chain.pem:/test-ca:ro" -e SSL_CERT_FILE=/test-ca \
    -e NO_PROXY=frontend,broker,monitoring -e no_proxy=frontend,broker,monitoring \
    --entrypoint python terrapi-ci/notifier:test - <<'PY'
import base64, json, re, ssl, sys, time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import paho.mqtt.client as mqtt
from threading import Event
for attempt in range(25):
    try:
        html = urlopen("http://frontend:8080/terra/", timeout=2).read().decode()
        break
    except OSError:
        if attempt == 24: raise
        time.sleep(.5)
paths = re.findall(r'(?:src|href)="(/terra/static/[^"]+)"', html)
assert paths and any(x.endswith(".js") for x in paths) and any(x.endswith(".css") for x in paths)
for path in paths:
    assert urlopen("http://frontend:8080" + path).headers.get_content_type() != "text/html"
for attempt in range(25):
    try:
        with urlopen("http://monitoring:8081/health", timeout=2):
            break
    except OSError:
        if attempt == 24: raise
        time.sleep(.5)
end = int(time.time())
history = f"http://frontend:8080/terra/api/monitoring/history?start={end-3600}&end={end}&points=120"
def request(user, password):
    basic = base64.b64encode(f"{user}:{password}".encode()).decode()
    return Request(history, headers={"Authorization": "Basic " + basic})
for denied in (history, request("monitoring", "monitoring-test-only"), request("dashboard", "wrong")):
    try:
        urlopen(denied, timeout=2)
    except HTTPError as err:
        assert err.code in (401, 403), err.code
    else:
        raise AssertionError("Private history accessible with incorrect credentials")
with urlopen(request("dashboard", "dashboard-test-only"), timeout=4) as response:
    assert response.headers.get_content_type() == "application/json"
    assert json.load(response)["summary"]["online"] == 0
for transport, host, port, path, tls in [
    ("tcp", "broker", 1883, "", True),
    ("websockets", "broker", 9001, "/mqtt", True),
    ("websockets", "frontend", 8080, "/terra/mqtt", False),
]:
    done = Event()
    client = mqtt.Client(transport=transport)
    client.username_pw_set("fixture", "fixture-test-only")
    if tls: client.tls_set_context(ssl.create_default_context(cafile="/test-ca"))
    if path: client.ws_set_options(path)
    def on_connect(c, _, flags, rc):
        if rc == 0: c.subscribe("ci/probe", qos=1)
    client.on_connect = on_connect
    client.on_subscribe = lambda c, _, mid, qos: c.publish("ci/probe", "test", qos=1)
    client.on_message = lambda c, _, msg: done.set() if msg.payload == b"test" else None
    client.connect(host, port)
    client.loop_start()
    assert done.wait(8), (transport, port)
    client.disconnect()
    client.loop_stop()
sys.path.insert(0, "/app")
from notify import TOPIC, run
fixture = {"host": "broker", "username": "fixture", "password": "fixture-test-only"}
assert run(fixture, "tcp", 1883) == "healthy"
assert run(fixture, "websockets", 9001) == "healthy"
ready = Event()
device = mqtt.Client()
device.tls_set_context(ssl.create_default_context())
device.username_pw_set(fixture["username"], fixture["password"])
device.on_connect = lambda c, _, flags, rc: c.subscribe(TOPIC + "/wake", qos=1)
device.on_subscribe = lambda *args: ready.set()
device.on_message = lambda c, _, msg: c.publish(TOPIC + "/status", json.dumps({"sequence": 42, "result": "healthy"}), qos=1)
device.connect("broker", 1883)
device.loop_start()
assert ready.wait(5)
assert run(fixture, "tcp", 1883, 42) == "healthy"
device.disconnect()
device.loop_stop()
print("Dashboard, authenticated history, both TLS listeners, proxied MQTT and release acknowledgment passed")
PY
