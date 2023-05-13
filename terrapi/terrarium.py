from xpipe.config import to_dict

class Terrarium():

    def __init__(self, conf):
        self._conf = conf

        self.sensors = to_dict(conf.sensors)
        self.controls = to_dict(conf.controls)