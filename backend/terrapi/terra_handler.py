import board
import adafruit_dht
import RPi.GPIO as GPIO
import terrapi.sensor as sensor
from terrapi.terrarium import Terrarium
from terrapi.config_manager import ConfigManager
from terrapi.thermostat import Thermostat
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
        # Note: default_mode and planning_periods are read directly from self._conf for hot-reload support

        self._loop_interval = 1  # Loop interval in seconds
        self._log_interval = conf.log_interval  # Log interval in seconds
        self._last_log = 0  # Last time the data was logged

        # Thermostat instances (keyed by control_name) to maintain state between loops
        self._thermostats = {}

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
                print(f"[CONFIG] Received update for section '{update.get('section')}': {update.get('data')}")
                success, message = self._config_manager.apply_config_update(
                    update, self._conf, self
                )
                print(f"[CONFIG] Update result: success={success}, message={message}")
                # Publish status response
                status = {"success": success, "message": message, "section": update.get("section")}
                self._mqtt_client.publish("config/status", json.dumps(status))
                
                # If successful, also publish updated full config
                if success:
                    self._publish_full_config()
                    # Log current config state for debugging
                    print(f"[CONFIG] Updated modes in memory: {self._conf._data.get('modes')}")
                    print(f"[CONFIG] Updated planning in memory: {self._conf._data.get('planning')}")
            except json.JSONDecodeError as e:
                status = {"success": False, "message": f"Invalid JSON: {str(e)}"}
                self._mqtt_client.publish("config/status", json.dumps(status))
            except Exception as e:
                status = {"success": False, "message": f"Error: {str(e)}"}
                self._mqtt_client.publish("config/status", json.dumps(status))
                import traceback
                traceback.print_exc()
        else:
            print(f"Unknown topic {topic}")

    def _publish_full_config(self):
        """Publish the full configuration to the config/full topic."""
        try:
            full_config = self._config_manager.get_full_config(self._conf)
            # Add current runtime state
            full_config["planning"]["active"] = self._follow_planning
            # Use current mode or calculate it if not yet set
            current_mode = self._current_mode if self._current_mode else self.get_mode()
            full_config["current_mode"] = current_mode
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
                print(f"[SENSOR] Reading data from sensor '{sensor_name}'...")
                data[sensor_name] = sensor.get_data()
                print(f"[SENSOR] Collected sensor data: {data}")
            
            # Get the mode FIRST (before publishing)
            self._current_mode = self.get_mode()
            print(f"[MODE] Current mode determined: {self._current_mode}")

            # Send the data to mqtt
            if time.time() - self._last_log >= self._log_interval:
                self._last_log = time.time()
                for sensor_name, sensor_data in data.items():
                    if sensor_data is None:
                        print(f"[SENSOR] No data from sensor '{sensor_name}', skipping MQTT publish.")
                        continue
                    for data_name, data_value in sensor_data.items():
                        self._mqtt_client.publish(f"sensor/{sensor_name}/{data_name}", str(data_value))
                        print(f"[SENSOR] sensor/{sensor_name}/{data_name}: {str(data_value)}")

                # Send current mode
                self._mqtt_client.publish("mode", self._current_mode if self._current_mode else "None")
                print(f"[MODE] mode: {self._current_mode}")
            
            # Handle 'None' mode - skip control application
            if self._current_mode is None or self._current_mode == "None":
                print(f"[CONTROL] Mode is None, swipping all controls OFF")
                for control_name, control in self._terrarium.controls.items():
                    control.switch(False)
                    print(f"[CONTROL] Control '{control_name}' set to state: False")
            
            else:
                # Apply mode to controls
                mode_params = self._conf.modes.get(self._current_mode) if hasattr(self._conf.modes, 'get') else getattr(self._conf.modes, self._current_mode, None)
                
                if mode_params is None:
                    print(f"[CONTROL] Unknown mode '{self._current_mode}', skipping control application")
                    time.sleep(1)
                    continue
                
                # Debug: log mode being applied
                print(f"[CONTROL] Applying mode '{self._current_mode}'")

                for control_name, control in self._terrarium.controls.items():
                    mode_config = mode_params.get(control_name) if hasattr(mode_params, 'get') else getattr(mode_params, control_name, None)
                    
                    # Check if this is a thermostat config (has 'type' attribute set to 'thermostat')
                    is_thermostat = False
                    if mode_config is not None:
                        if hasattr(mode_config, 'type'):
                            is_thermostat = mode_config.type == 'thermostat'
                        elif isinstance(mode_config, dict):
                            is_thermostat = mode_config.get('type') == 'thermostat'
                    
                    if is_thermostat:
                        # Handle thermostat control
                        relay_state = self._apply_thermostat(control_name, mode_config, data)
                        control.switch(relay_state)
                    else:
                        # Simple boolean control (backwards compatible)
                        state = bool(mode_config) if mode_config is not None else False
                        control.switch(state)
                        print(f"[CONTROL] Control '{control_name}' set to state: {state}")
                

            # Publish control states
            for control_name, control in self._terrarium.controls.items():
                state = control.get_state()
                self._mqtt_client.publish(f"control/{control_name}/state", str(state))
                print(f"[CONTROL] control/{control_name}/state: {str(state)}")
            
            # Sleep for 1 second
            time.sleep(1)


    def get_mode(self):
        # Set mode according to the planning if needed
        if self._follow_planning:
            current_time = datetime.now()
            current_minutes = current_time.hour * 60 + current_time.minute  # Convert to minutes since midnight
            print(f"[MODE] Following planning, current time: {current_time.strftime('%H:%M')} ({current_minutes} min)")
            
            # Read periods directly from config to get latest values
            planning_periods = self._conf.planning.periods
            for period_name in planning_periods.keys():
                period = planning_periods[period_name]
                # Str to hour and minute
                start_parts = str(period.start).split(":")
                end_parts = str(period.end).split(":")
                start_hour, start_minute = int(start_parts[0]), int(start_parts[1])
                end_hour, end_minute = int(end_parts[0]), int(end_parts[1])
                
                start_minutes = start_hour * 60 + start_minute
                end_minutes = end_hour * 60 + end_minute
                
                # Get the mode for this period
                period_mode = period.mode
                print(f"[MODE] Checking period '{period_name}': {start_hour:02d}:{start_minute:02d} - {end_hour:02d}:{end_minute:02d} -> mode '{period_mode}'")

                # Check if the current time is in the period
                # Handle overnight periods (e.g., 22:00 - 07:00)
                if start_minutes <= end_minutes:
                    # Normal period (same day): e.g., 07:00 - 17:00
                    if start_minutes <= current_minutes < end_minutes:
                        print(f"[MODE] Matched period '{period_name}', using mode '{period_mode}'")
                        return period_mode
                else:
                    # Overnight period: e.g., 22:00 - 07:00
                    # Current time is in period if it's >= start OR < end
                    if current_minutes >= start_minutes or current_minutes < end_minutes:
                        print(f"[MODE] Matched overnight period '{period_name}', using mode '{period_mode}'")
                        return period_mode
                
            # If no period is active, return the default mode from config (for hot-reload support)
            default_mode = self._conf.planning.default_mode
            print(f"[MODE] No period matched, using default mode '{default_mode}'")
            return default_mode
            
        else:
            # Remain unchanged
            print(f"[MODE] Planning inactive, keeping current mode '{self._current_mode}'")
            return self._current_mode

    def _apply_thermostat(self, control_name: str, config, sensor_data: dict) -> bool:
        """
        Apply thermostat logic to determine relay state.
        
        Args:
            control_name: Name of the control (e.g., 'cooling_system')
            config: Thermostat configuration (Config object or dict)
            sensor_data: Dict of sensor readings {sensor_name: {data_name: value}}
            
        Returns:
            True if relay should be ON, False if OFF
        """
        # Extract config values (handle both Config object and dict)
        def get_val(key, default=None):
            if hasattr(config, key):
                return getattr(config, key)
            elif isinstance(config, dict):
                return config.get(key, default)
            return default
        
        enabled = get_val('enabled', False)
        if not enabled:
            print(f"[THERMOSTAT] {control_name}: disabled, relay OFF")
            return False
        
        target_temp = float(get_val('target_temperature', 25.0))
        hysteresis = float(get_val('hysteresis', 1.0))
        sensor_name = get_val('sensor', 'dht22')
        action = get_val('action', 'cooling')
        
        # Get temperature from referenced sensor
        sensor_readings = sensor_data.get(sensor_name, {})
        current_temp = sensor_readings.get('temperature') if sensor_readings else None
        
        if current_temp is None:
            print(f"[THERMOSTAT] {control_name}: No temperature from sensor '{sensor_name}', keeping current state")
            # Keep current state if we have a thermostat instance, otherwise OFF
            if control_name in self._thermostats:
                return self._thermostats[control_name].relay_state
            return False
        
        # Get or create thermostat instance for this control
        # Key includes mode to reset state when mode changes
        thermostat_key = f"{control_name}_{self._current_mode}"
        
        if thermostat_key not in self._thermostats:
            self._thermostats[thermostat_key] = Thermostat(
                target_temp=target_temp,
                hysteresis=hysteresis,
                action=action
            )
        else:
            # Update thermostat settings in case they changed
            thermostat = self._thermostats[thermostat_key]
            thermostat.target_temp = target_temp
            thermostat.hysteresis = hysteresis
            thermostat.action = action
        
        thermostat = self._thermostats[thermostat_key]
        relay_state = thermostat.compute_state(float(current_temp))
        
        print(f"[THERMOSTAT] {control_name}: temp={current_temp}°C, target={target_temp}°C (±{hysteresis}), "
              f"action={action}, relay={'ON' if relay_state else 'OFF'}")
        
        return relay_state