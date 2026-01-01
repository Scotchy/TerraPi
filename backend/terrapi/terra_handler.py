import board
import adafruit_dht
import RPi.GPIO as GPIO
import terrapi.sensor as sensor
from terrapi.terrarium import Terrarium
from terrapi.config_manager import ConfigManager
import time
import json
import os
from datetime import datetime

class TerraHandler():

    def __init__(self, terra, mqtt_client, conf, config_path: str = "conf/config.yaml"):
        self._terrarium = terra
        self._mqtt_client = mqtt_client
        self._conf = conf
        self._config_path = config_path

        # Initialize ConfigManager for runtime config updates
        self._config_manager = ConfigManager(config_path)

        self._follow_planning = conf.planning.active  # Whether to follow the planning or not
        self._current_mode = None
        self._default_mode = conf.planning.default_mode  # Default mode
        self._planning_periods = conf.planning.periods  # Planning periods

        self._loop_interval = 1  # Loop interval in seconds
        self._log_interval = conf.log_interval  # Log interval in seconds
        self._last_log = 0  # Last time the data was logged

        # Set message handler BEFORE connection (called from run.py after this)
        self._mqtt_client.on_message(self._handle_message)


    def _handle_message(self, client, userdata, message):
        # Topics possible: 
        #  - planning/active 
        #  - mode/set (works only if planning is not active)
        #  - config/get - request full configuration
        #  - config/update - update configuration section

        # Get the topic and the message
        topic = message.topic
        payload = message.payload.decode("utf-8")
        
        print(f"[MQTT] Received message on topic: {topic}")

        if topic == "planning/active":
            self._follow_planning = payload == "1"

        elif topic == "mode/set":
            if not self._follow_planning:
                self._current_mode = payload

        elif topic == "config/get":
            # Send full configuration to frontend
            print("Received config/get request, publishing full config...")
            self._publish_full_config()

        elif topic == "config/update":
            # Handle configuration update request
            try:
                update = json.loads(payload)
                success, message = self._config_manager.apply_config_update(
                    update, self._conf, self
                )
                # Publish status response
                status = {"success": success, "message": message, "section": update.get("section")}
                self._mqtt_client.publish("config/status", json.dumps(status))
                
                # If successful, also publish updated full config
                if success:
                    self._publish_full_config()
            except json.JSONDecodeError as e:
                status = {"success": False, "message": f"Invalid JSON: {str(e)}"}
                self._mqtt_client.publish("config/status", json.dumps(status))
            except Exception as e:
                status = {"success": False, "message": f"Error: {str(e)}"}
                self._mqtt_client.publish("config/status", json.dumps(status))
        else:
            print(f"Unknown topic {topic}")

    def _publish_full_config(self):
        """Publish the full configuration to the config/full topic."""
        try:
            full_config = self._config_manager.get_full_config(self._conf)
            # Add current runtime state
            full_config["planning"]["active"] = self._follow_planning
            full_config["current_mode"] = self._current_mode
            config_json = json.dumps(full_config)
            print(f"Publishing config/full: {config_json[:200]}...")
            self._mqtt_client.publish("config/full", config_json)
        except Exception as e:
            print(f"Error publishing full config: {e}")
            import traceback
            traceback.print_exc()

    def _on_mqtt_ready(self):
        """Called when MQTT connection is ready and subscriptions are confirmed."""
        print("[MQTT] Connection ready, publishing initial config...")
        self._publish_full_config()


    def run(self):

        # Queue topic subscriptions (will be subscribed when connection is ready)
        print("[MQTT] Queueing topic subscriptions...")
        self._mqtt_client.subscribe("planning/active")
        self._mqtt_client.subscribe("mode/set")
        self._mqtt_client.subscribe("config/get")
        self._mqtt_client.subscribe("config/update")
        
        # Set callback to publish initial config when connection is ready
        self._mqtt_client.on_ready(self._on_mqtt_ready)

        print("[MQTT] Waiting for connection and entering main loop...")
        
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
                        print(f"sensor/{sensor_name}/{data_name}: {str(data_value)}")

                # Send current mode
                self._mqtt_client.publish("mode", self._current_mode)
                print(f"mode: {self._current_mode}")

            # Get the mode
            self._current_mode = self.get_mode()

            mode_params = self._conf.modes[self._current_mode]
            target_controls_states = {control_name: mode_params[control_name] for control_name in mode_params.keys()}

            for control_name, control in self._terrarium.controls.items():
                # Set the control state
                control.switch(target_controls_states.get(control_name, False))
            
            # Sleep for 1 second
            time.sleep(1)


    def get_mode(self):
        # Set mode according to the planning if needed
        if self._follow_planning:
            current_time = datetime.now()
            for period in self._planning_periods.values():
                # Str to hour and minute
                start_hour, start_minute = period.start.split(":")
                end_hour, end_minute = period.end.split(":")
                start_hour, start_minute = int(start_hour), int(start_minute)
                end_hour, end_minute = int(end_hour), int(end_minute)

                # Check if the current time is in the period
                if start_hour <= current_time.hour <= end_hour and start_minute <= current_time.minute <= end_minute:
                    return period.mode

                
            # If no period is active, return the default mode
            return self._default_mode
            
        else:
            # Remain unchanged
            return self._current_mode