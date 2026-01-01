"""
Configuration Manager for TerraPi.
Handles reading, writing, and validating the unified YAML configuration file.
"""

import os
import yaml
from typing import Any, Dict, Tuple

from terrapi.config_loader import Config


class ConfigManager:
    """Manages runtime configuration updates and YAML persistence."""

    def __init__(self, config_path: str):
        """
        Initialize ConfigManager with the config file path.
        
        Args:
            config_path: Path to the config.yaml file.
        """
        self._config_path = config_path

    def get_full_config(self, conf: Config) -> Dict[str, Any]:
        """
        Get the full configuration as a JSON-serializable dict.
        
        Args:
            conf: The Config object.
            
        Returns:
            Dict with all configuration sections.
        """
        # Build modes dict (direct attribute access)
        modes = {}
        for mode_name in conf.modes.keys():
            mode_data = conf.modes[mode_name]
            mode_dict = {}
            
            # Iterate through controls in this mode
            if hasattr(mode_data, 'keys'):
                for control_name in mode_data.keys():
                    control_config = mode_data[control_name] if hasattr(mode_data, '__getitem__') else getattr(mode_data, control_name)
                    
                    # Check if it's a thermostat config
                    if hasattr(control_config, 'type') and control_config.type == 'thermostat':
                        # Serialize thermostat config
                        mode_dict[control_name] = {
                            'type': 'thermostat',
                            'enabled': getattr(control_config, 'enabled', False),
                            'target_temperature': float(getattr(control_config, 'target_temperature', 25.0)),
                            'hysteresis': float(getattr(control_config, 'hysteresis', 1.0)),
                            'sensor': getattr(control_config, 'sensor', 'dht22'),
                            'action': getattr(control_config, 'action', 'cooling')
                        }
                    elif isinstance(control_config, dict) and control_config.get('type') == 'thermostat':
                        # Already a dict thermostat config
                        mode_dict[control_name] = control_config
                    else:
                        # Simple boolean control
                        mode_dict[control_name] = bool(control_config)
            elif hasattr(mode_data, 'to_dict'):
                mode_dict = mode_data.to_dict()
            elif hasattr(mode_data, '_data'):
                mode_dict = mode_data._data
            
            modes[mode_name] = mode_dict
        
        # Build planning dict
        planning_conf = conf.planning
        planning = {
            "active": planning_conf.active,
            "default_mode": planning_conf.default_mode,
            "periods": {}
        }
        for period_name in planning_conf.periods.keys():
            period = planning_conf.periods[period_name]
            planning["periods"][period_name] = {
                "start": period.start,
                "end": period.end,
                "mode": period.mode
            }
        
        # Build sensors dict (read-only info)
        sensors = {}
        for sensor_name in conf.sensors.keys():
            sensor_conf = conf.sensors[sensor_name]
            sensors[sensor_name] = {
                "type": sensor_conf.type if hasattr(sensor_conf, 'type') else str(sensor_conf),
            }
        
        # Build controls dict (read-only info)
        controls = {}
        for control_name in conf.controls.keys():
            control_conf = conf.controls[control_name]
            controls[control_name] = {
                "type": control_conf.type if hasattr(control_conf, 'type') else str(control_conf),
            }
        
        return {
            "modes": modes,
            "planning": planning,
            "sensors": sensors,
            "controls": controls,
            "log_interval": conf.log_interval
        }

    def validate_modes(self, modes: Dict[str, Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Validate modes configuration.
        
        Args:
            modes: Dict of mode_name -> {control_name: bool | thermostat_config}
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not modes:
            return False, "At least one mode is required"
        
        for mode_name, controls in modes.items():
            if not isinstance(mode_name, str) or not mode_name.strip():
                return False, f"Invalid mode name: {mode_name}"
            if not isinstance(controls, dict):
                return False, f"Mode '{mode_name}' must have control states"
            for control_name, control_config in controls.items():
                # Check if it's a thermostat config
                if isinstance(control_config, dict) and control_config.get('type') == 'thermostat':
                    # Validate thermostat config
                    is_valid, error = self._validate_thermostat_config(control_config, mode_name, control_name)
                    if not is_valid:
                        return False, error
                elif not isinstance(control_config, bool):
                    return False, f"Control '{control_name}' in mode '{mode_name}' must be true/false or a thermostat config"
        
        return True, ""

    def _validate_thermostat_config(self, config: Dict[str, Any], mode_name: str, control_name: str) -> Tuple[bool, str]:
        """
        Validate a thermostat configuration.
        
        Args:
            config: Thermostat configuration dict
            mode_name: Name of the mode (for error messages)
            control_name: Name of the control (for error messages)
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ['enabled', 'target_temperature', 'hysteresis', 'sensor', 'action']
        
        for field in required_fields:
            if field not in config:
                return False, f"Thermostat '{control_name}' in mode '{mode_name}' missing required field: {field}"
        
        if not isinstance(config['enabled'], bool):
            return False, f"Thermostat '{control_name}' in mode '{mode_name}': 'enabled' must be true/false"
        
        try:
            temp = float(config['target_temperature'])
            if temp < -50 or temp > 100:
                return False, f"Thermostat '{control_name}' in mode '{mode_name}': target_temperature out of range (-50 to 100)"
        except (ValueError, TypeError):
            return False, f"Thermostat '{control_name}' in mode '{mode_name}': target_temperature must be a number"
        
        try:
            hyst = float(config['hysteresis'])
            if hyst < 0 or hyst > 10:
                return False, f"Thermostat '{control_name}' in mode '{mode_name}': hysteresis out of range (0 to 10)"
        except (ValueError, TypeError):
            return False, f"Thermostat '{control_name}' in mode '{mode_name}': hysteresis must be a number"
        
        if not isinstance(config['sensor'], str) or not config['sensor'].strip():
            return False, f"Thermostat '{control_name}' in mode '{mode_name}': sensor must be a non-empty string"
        
        if config['action'] not in ['cooling', 'heating']:
            return False, f"Thermostat '{control_name}' in mode '{mode_name}': action must be 'cooling' or 'heating'"
        
        return True, ""

    def validate_planning(self, planning: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validate planning configuration.
        
        Args:
            planning: Planning configuration dict
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if "active" not in planning:
            return False, "Planning must have 'active' field"
        
        if "default_mode" not in planning:
            return False, "Planning must have 'default_mode' field"
        
        if "periods" in planning:
            for period_name, period in planning["periods"].items():
                if "start" not in period or "end" not in period or "mode" not in period:
                    return False, f"Period '{period_name}' must have start, end, and mode"
                
                # Validate time format (HH:MM)
                for time_field in ["start", "end"]:
                    time_val = str(period[time_field])
                    try:
                        parts = time_val.split(":")
                        if len(parts) != 2:
                            raise ValueError()
                        hour, minute = int(parts[0]), int(parts[1])
                        if not (0 <= hour <= 23 and 0 <= minute <= 59):
                            raise ValueError()
                    except (ValueError, AttributeError):
                        return False, f"Invalid time format in period '{period_name}': {time_val}"
        
        return True, ""

    def _load_full_yaml(self) -> Dict[str, Any]:
        """Load the full YAML config file."""
        with open(self._config_path, 'r') as f:
            return yaml.safe_load(f)

    def _save_full_yaml(self, data: Dict[str, Any]) -> None:
        """Save the full YAML config file."""
        with open(self._config_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def update_modes(self, modes: Dict[str, Dict[str, bool]]) -> Tuple[bool, str]:
        """
        Update modes section in the unified config file.
        
        Args:
            modes: New modes configuration
            
        Returns:
            Tuple of (success, message)
        """
        is_valid, error = self.validate_modes(modes)
        if not is_valid:
            return False, error
        
        try:
            config = self._load_full_yaml()
            config['modes'] = modes
            self._save_full_yaml(config)
            return True, "Modes updated successfully"
        except Exception as e:
            return False, f"Failed to update modes: {str(e)}"

    def update_planning(self, planning: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Update planning section in the unified config file.
        
        Args:
            planning: New planning configuration
            
        Returns:
            Tuple of (success, message)
        """
        is_valid, error = self.validate_planning(planning)
        if not is_valid:
            return False, error
        
        try:
            config = self._load_full_yaml()
            config['planning'] = planning
            self._save_full_yaml(config)
            return True, "Planning updated successfully"
        except Exception as e:
            return False, f"Failed to update planning: {str(e)}"

    def apply_config_update(self, update: Dict[str, Any], conf: Config, terra_handler) -> Tuple[bool, str]:
        """
        Apply a configuration update from the frontend.
        
        Args:
            update: Dict with section name and new values
            conf: The Config object
            terra_handler: The TerraHandler instance for runtime updates
            
        Returns:
            Tuple of (success, message)
        """
        section = update.get("section")
        data = update.get("data")
        
        if not section or data is None:
            return False, "Update must include 'section' and 'data'"
        
        if section == "modes":
            success, message = self.update_modes(data)
            if success:
                # Hot-reload modes in memory by updating the config's internal data
                conf._data['modes'] = data
            return success, message
        
        elif section == "planning":
            success, message = self.update_planning(data)
            if success:
                # Hot-reload planning in terra_handler
                if "active" in data:
                    terra_handler._follow_planning = data["active"]
                # Update config's internal data (default_mode and periods are read from here)
                conf._data['planning'] = data
            return success, message
        
        else:
            return False, f"Unknown config section: {section}"
