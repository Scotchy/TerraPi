from xpipe.config import to_dict
import time

class Terrarium():

    def __init__(self, conf):
        self._conf = conf
        print("Initializing sensors...")
        self.sensors = { sensor_name: sensor() for sensor_name, sensor in conf.sensors.items() }
        time.sleep(2)
        print("Initializing controls...")
        self.controls = { control_name: control() for control_name, control in conf.controls.items() }