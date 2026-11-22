import argparse
from contextlib import ExitStack
import logging
import signal
import time

import RPi.GPIO as GPIO

from terrapi.client import MosquittoClient
from terrapi.config_loader import connection_settings, load_config
from terrapi.terra_handler import TerraHandler
from terrapi.terrarium import Terrarium


def run_once(path):
    config = load_config(path)
    with ExitStack() as resources:
        GPIO.setmode(GPIO.BCM)
        resources.callback(GPIO.cleanup)
        terra = Terrarium(config, resources)
        client = MosquittoClient(connection_settings(config))
        handler = TerraHandler(terra, client, config, path)
        resources.callback(client.disconnect)
        client.start(handler.on_message, handler.publish_config)
        handler.run()


def run():
    parser = argparse.ArgumentParser(description="Run the TerraPi controller")
    parser.add_argument("--conf", default="conf/config.yaml", help="Path to live configuration")
    args = parser.parse_args()

    def stop(signum, frame):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    while True:
        try:
            run_once(args.conf)
        except Exception:
            logging.exception("Controller stopped. Retrying in 10 seconds.")
            time.sleep(10)


if __name__ == "__main__":
    run()
