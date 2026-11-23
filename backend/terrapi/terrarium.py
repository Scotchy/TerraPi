from . import control, sensor


def create_device(module, base, definition):
    kind = getattr(module, definition["type"], None)
    if not isinstance(kind, type) or kind is base or not issubclass(kind, base):
        raise ValueError(f"Unsupported {base.__name__} type")
    return kind(**{key: value for key, value in definition.items() if key != "type"})


class Terrarium:
    def __init__(self, config, resources):
        self.controls = {}
        for name, definition in config["controls"].items():
            relay = create_device(control, control.Control, definition)
            resources.callback(relay.switch, False)
            self.controls[name] = relay
        self.sensors = {}
        for name, definition in config["sensors"].items():
            device = create_device(sensor, sensor.Sensor, definition)
            resources.callback(device.close)
            self.sensors[name] = device
