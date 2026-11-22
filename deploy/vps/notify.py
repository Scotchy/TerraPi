"""Perform authenticated broker checks or wait for the selected Pi deployment."""
import json
import ssl
import sys
import threading

import paho.mqtt.client as mqtt

TOPIC = "terrapi/deploy/controller"


def run(config, transport, port, sequence=None):
    done = threading.Event()
    outcome = []
    client = mqtt.Client(transport=transport)
    client.tls_set_context(ssl.create_default_context())
    client.username_pw_set(config["username"], config["password"])

    def on_connect(client, _, flags, rc):
        if rc:
            outcome.append("failed")
            done.set()
        elif sequence is None:
            outcome.append("healthy")
            done.set()
        else:
            client.subscribe(TOPIC + "/status", qos=1)

    def on_subscribe(client, _, mid, qos):
        if 128 in qos:
            outcome.append("failed")
            done.set()
        else:
            client.publish(TOPIC + "/wake", "check", qos=1)

    def on_message(client, _, msg):
        try:
            status = json.loads(msg.payload)
            if status["sequence"] == sequence and status["result"] in ("healthy", "failed"):
                outcome.append(status["result"])
                done.set()
        except (ValueError, KeyError, TypeError):
            pass

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_message = on_message
    client.connect(config["host"], int(port), keepalive=30)
    client.loop_start()
    try:
        done.wait(300 if sequence is not None else 10)
        return outcome[0] if outcome else "pending"
    finally:
        client.disconnect()
        client.loop_stop()


if __name__ == "__main__":
    config = json.load(sys.stdin)
    if sys.argv[1] == "check":
        ok = run(config, "tcp", config["native_port"]) == "healthy" and run(config, "websockets", config["ws_port"]) == "healthy"
        sys.exit(0 if ok else 1)
    else:
        result = run(config, "tcp", config["native_port"], config["sequence"])
        sys.exit({"healthy": 0, "pending": 75, "failed": 1}[result])
