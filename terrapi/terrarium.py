from xpipe.config import to_dict

class Terrarium():

    def __init__(self, conf):
        self._conf = conf

        self.sensors = { sensor_name: sensor() for sensor_name, sensor in conf.sensors.items() }
        self.controls = { control_name: control() for control_name, control in conf.controls.items() }