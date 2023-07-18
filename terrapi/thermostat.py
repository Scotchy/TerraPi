
import enum


class Controller():

    def __init__(self, sensors_names):
        """
        Controller class

        Args:
            sensors_names (list): List of sensor names
        """
        self.sensors_names = sensors_names

    def should_switch(self, *sensor_values):
        """
        Returns True if the controller should switch on, False otherwise
        """
        raise NotImplementedError()


class ThermostatMode(enum.Enum):
    HEAT = "heat"
    COOL = "cool"


class Thermostat(Controller):
    def __init__(self, sensors_names, thresh_temp, release_delta, mode):
        """
        Thermostat class

        Args:
            thresh_temp (float): Temperature threshold to switch the thermostat
            release_delta (float): Don't switch on the heating (resp. switch off cooling) if the temperature is above (resp. below) the threshold by this value
            mode (str): Thermostat mode (possible values: "heat", "cool")
        """
        self.thresh_temp = thresh_temp
        self.release_delta = release_delta
        self.mode = ThermostatMode(mode)
        self._last_state = None
        super().__init__(sensors_names)
        

    def should_switch(self, *sensor_values):
        """
        Returns True if the thermostat should switch on, False otherwise

        Args:
            temp (float): Current temperature
        """
        temp = sensor_values[0]["temperature"]
        if self.mode == ThermostatMode.HEAT:
            if temp < self.thresh_temp - self.release_delta:
                self._last_state = True
                return True
            elif temp > self.thresh_temp:
                self._last_state = False
                return False
            else:
                return self._last_state
        elif self.mode == ThermostatMode.COOL:
            if temp > self.thresh_temp + self.release_delta:
                self._last_state = True
                return True
            elif temp < self.thresh_temp:
                self._last_state = False
                return False
            else:
                return self._last_state
        else:
            raise ValueError("Invalid thermostat mode")
