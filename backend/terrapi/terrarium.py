from terrapi.config_loader import instantiate_sensors, instantiate_controls
import time

class Terrarium():

    def __init__(self, conf):
        self._conf = conf
        print("Initializing sensors...")
        self.sensors = instantiate_sensors(conf.sensors.to_dict())
        time.sleep(2)
        print("Initializing controls...")
        self.controls = instantiate_controls(conf.controls.to_dict())