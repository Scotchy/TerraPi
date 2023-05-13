import board
import adafruit_dht
import RPi.GPIO as GPIO
import terrapi.sensor as sensor
from terrapi.terrarium import Terrarium
from xpipe.config import to_dict
import time

class TerraHandler():

    def __init__(self, terra, mqtt_client, conf):
        self._terra = terra
        self._mqtt_client = mqtt_client
        self._conf = conf

        self._follow_planning = conf.planning.active() # Whether to follow the planning or not
        self._current_mode = None
        self._default_mode = conf.planning.default_mode() # Default mode
        self._planning_periods = conf.planning.periods # Planning periods

        self._loop_interval = 1 # Loop interval in seconds
        self._log_interval = conf.log_interval() # Log interval in seconds
        self._last_log = 0 # Last time the data was logged

        self._terrarium = Terrarium(conf)


    def _handle_message(self, client, userdata, message):
        # Topics possible: 
        #  - planning/active 
        #  - mode/set (works only if planning is not active)

        # Get the topic and the message
        topic = message.topic
        message = message.payload.decode("utf-8")

        if topic == "planning/active":
            self._follow_planning = message == "1"

        elif topic == "mode/set":
            if not self._follow_planning:
                self._current_mode = message
        else:
            print(f"Unknown topic {topic}")


    def run(self):

        # Subscribe to topics
        self._mqtt_client.subscribe("planning/active")
        self._mqtt_client.subscribe("mode/set")
        
        self._mqtt_client.on_message(self._handle_message)

        # Start the loop
        while True:

            # Get the data from the sensors
            data = {}
            for sensor_name, sensor in self._terrarium.sensors.items():
                data[sensor_name] = sensor.get_data()
            
            # Send the data to mqtt
            if time.time() - self._last_log >= self._log_interval:
                self._last_log = time.time()
                for sensor_name, sensor_data in data.items():
                    for data_name, data_value in sensor_data.items():
                        self._mqtt_client.publish(f"sensor/{sensor_name}/{data_name}", str(data_value))

            # Get the mode
            self._current_mode = self.get_mode()

            mode_params = self._conf.modes[self._current_mode]
            target_controls_states = {control_name: mode_params[control_name] for control_name in mode_params.values()}

            for control_name, control in self._terrarium.controls.items():
                # Set the control state
                control.switch(target_controls_states.get(control_name, False))
            
            # Sleep for 1 second
            time.sleep(1)


    def get_mode(self):
        # Set mode according to the planning if needed
        if self._follow_planning:
            current_time = time.time()
            for period in self._planning_periods:
                if period.start() <= current_time <= period.end():
                    return period.mode()
            # If no period is active, return the default mode
            return self._default_mode
            
        else:
            # Remain unchanged
            return self._current_mode