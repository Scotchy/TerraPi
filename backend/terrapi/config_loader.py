"""Resolve private connection settings without expanding editable fields."""
import os

from .config_schema import private_value, read_config


def connection_settings(config):
    settings = dict(config["mqtt"])
    for field in ("host", "user", "password", "ca_certs"):
        if field in settings:
            settings[field] = private_value(settings[field], os.environ)
    if os.environ.get("TERRAPI_MANAGED_TLS") == "1":
        settings.update(host=os.environ["MQTT_HOST"], port=int(os.environ["MQTT_PORT"]),
                        user=os.environ["MQTT_USER"], password=os.environ["MQTT_PASSWORD"], use_ssl=True)
    return settings


def load_config(path):
    return read_config(path)
