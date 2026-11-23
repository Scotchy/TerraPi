"""Validate live configuration without importing GPIO or opening any devices."""
import math
import re

import yaml


def mapping(value, name):
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def number(value, low, high, field):
    try:
        result = float(value)
    except (ValueError, TypeError, OverflowError):
        raise ValueError(f"Invalid {field}") from None
    if isinstance(value, bool) or not math.isfinite(result) or not low <= result <= high:
        raise ValueError(f"Invalid {field}")
    return result


def validate_devices(devices, section):
    for name, device in mapping(devices, section).items():
        if not isinstance(name, str) or not name or any(c in name for c in "/+#"):
            raise ValueError(f"Invalid name in {section}")
        kind = mapping(device, name).get("type")
        if not isinstance(kind, str) or not kind.isidentifier() or type(device.get("pin")) is not int:
            raise ValueError(f"Invalid {section} definition for {name}")


def validate_modes(modes, sensors, controls):
    if not mapping(modes, "Modes"):
        raise ValueError("At least one mode is required")
    for name, profile in modes.items():
        if not isinstance(name, str) or not name.strip() or name == "None":
            raise ValueError("Invalid mode name")
        for control, value in mapping(profile, "Mode controls").items():
            if control not in controls:
                raise ValueError(f"Unknown control in {name}")
            if isinstance(value, bool):
                continue
            if not isinstance(value, dict) or value.get("type") != "thermostat":
                raise ValueError(f"Invalid thermostat in {name}")
            if type(value.get("enabled")) is not bool or value.get("action") not in ("heating", "cooling"):
                raise ValueError(f"Invalid thermostat settings in {name}")
            if not isinstance(value.get("sensor"), str) or value["sensor"] not in sensors:
                raise ValueError(f"Unknown thermostat sensor in {name}")
            for field, low, high in (("target_temperature", -50, 100), ("hysteresis", 0, 10)):
                value[field] = number(value.get(field), low, high, field)


def validate_planning(plan, modes, legacy):
    def mode_name(value):
        if value in (None, "", "None"):
            return ""
        if isinstance(value, str) and value in modes:
            return value
        if legacy and isinstance(value, str):
            return ""  # Older editors could delete a mode still referenced by planning.
        raise ValueError("Schedule refers to an unknown mode")

    if type(plan.get("active")) is not bool or "default_mode" not in plan:
        raise ValueError("Planning needs a boolean active flag and a default mode")
    plan["default_mode"] = mode_name(plan["default_mode"])
    for name, period in mapping(plan.setdefault("periods", {}), "Periods").items():
        if not isinstance(name, str) or not name.strip() or not isinstance(period, dict) or "mode" not in period:
            raise ValueError("Invalid schedule period")
        period["mode"] = mode_name(period["mode"])
        for key in ("start", "end"):
            value = period.get(key)
            if not isinstance(value, str) or not re.fullmatch(r"(?:[01]?\d|2[0-3]):[0-5]\d", value):
                raise ValueError(f"Invalid {key} time in {name}")
            period[key] = value.zfill(5)


def validate_config(config, *, legacy=False):
    """Normalize legacy selections and check the complete candidate before use."""
    mapping(config, "Configuration")
    mapping(config.get("mqtt"), "MQTT settings")
    for section in ("sensors", "controls"):
        validate_devices(config.get(section), section)
    config["log_interval"] = number(config.get("log_interval"), 0.001, float("inf"), "log_interval")
    if "sensor_timeout" in config:
        config["sensor_timeout"] = number(config["sensor_timeout"], 0, float("inf"), "sensor_timeout")
    modes = config.get("modes")
    validate_modes(modes, config["sensors"], config["controls"])
    validate_planning(mapping(config.get("planning"), "Planning"), modes, legacy)
    if not isinstance(config.get("manual_mode"), str) or config["manual_mode"] not in modes:
        config["manual_mode"] = ""
    return config


def read_config(path):
    with open(path, encoding="utf-8") as source:
        return validate_config(yaml.safe_load(source), legacy=True)


def private_value(value, environment):
    if isinstance(value, str):
        return re.sub(r"\$\{(\w+)\}", lambda m: environment.get(m[1], ""), value)
    return value
