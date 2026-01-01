"""
Configuration Manager for TerraPi.
Handles reading, writing, and validating YAML configuration files.
"""

import os
import yaml
import json
from typing import Any, Dict, Optional, Tuple


class ConfigManager:
    """Manages runtime configuration updates and YAML persistence."""

    def __init__(self, conf_dir: str):
        """
        Initialize ConfigManager with the configuration directory.
        
        Args:
            conf_dir: Path to the conf/ directory containing YAML files.
        """
        self._conf_dir = conf_dir
        self._modes_file = os.path.join(conf_dir, "modes.yaml")
        self._planning_file = os.path.join(conf_dir, "planning.yaml")
        self._main_file = os.path.join(conf_dir, "main.yaml")

    def get_full_config(self, conf) -> Dict[str, Any]:
        """
        Get the full configuration as a JSON-serializable dict.
        
        Args:
            conf: The xpipe config object.
            
        Returns:
            Dict with all configuration sections.
        """
        # Build modes dict
        modes = {}
        for mode_name in conf.modes.keys():
            mode_params = conf.modes[mode_name]
            modes[mode_name] = {
                control: mode_params[control] 
                for control in mode_params.keys()
            }
        
        # Build planning dict
        planning = {
            "active": conf.planning.active(),
            "default_mode": conf.planning.default_mode(),
            "periods": {}
        }
        for period_name, period in conf.planning.periods.items():
            planning["periods"][period_name] = {
                "start": period.start(),
                "end": period.end(),
                "mode": period.mode()
            }
        
        # Build sensors dict (read-only info)
        sensors = {}
        for sensor_name, sensor_class in conf.sensors.items():
            sensors[sensor_name] = {
                "type": type(sensor_class).__name__ if hasattr(sensor_class, '__name__') else str(sensor_class),
            }
        
        # Build controls dict (read-only info)
        controls = {}
        for control_name, control_class in conf.controls.items():
            controls[control_name] = {
                "type": type(control_class).__name__ if hasattr(control_class, '__name__') else str(control_class),
            }
        
        return {
            "modes": modes,
            "planning": planning,
            "sensors": sensors,
            "controls": controls,
            "log_interval": conf.log_interval()
        }

    def validate_modes(self, modes: Dict[str, Dict[str, bool]]) -> Tuple[bool, str]:
        """
        Validate modes configuration.
        
        Args:
            modes: Dict of mode_name -> {control_name: bool}
            
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
            for control_name, state in controls.items():
                if not isinstance(state, bool):
                    return False, f"Control '{control_name}' in mode '{mode_name}' must be true/false"
        
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

    def update_modes(self, modes: Dict[str, Dict[str, bool]]) -> Tuple[bool, str]:
        """
        Update modes configuration and persist to YAML.
        
        Args:
            modes: New modes configuration
            
        Returns:
            Tuple of (success, message)
        """
        is_valid, error = self.validate_modes(modes)
        if not is_valid:
            return False, error
        
        try:
            with open(self._modes_file, 'w') as f:
                yaml.dump(modes, f, default_flow_style=False, sort_keys=False)
            return True, "Modes updated successfully"
        except Exception as e:
            return False, f"Failed to write modes file: {str(e)}"

    def update_planning(self, planning: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Update planning configuration and persist to YAML.
        
        Args:
            planning: New planning configuration
            
        Returns:
            Tuple of (success, message)
        """
        is_valid, error = self.validate_planning(planning)
        if not is_valid:
            return False, error
        
        try:
            with open(self._planning_file, 'w') as f:
                yaml.dump(planning, f, default_flow_style=False, sort_keys=False)
            return True, "Planning updated successfully"
        except Exception as e:
            return False, f"Failed to write planning file: {str(e)}"

    def apply_config_update(self, update: Dict[str, Any], conf, terra_handler) -> Tuple[bool, str]:
        """
        Apply a configuration update from the frontend.
        
        Args:
            update: Dict with section name and new values
            conf: The xpipe config object
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
                # Hot-reload modes in memory
                for mode_name, controls in data.items():
                    conf.modes[mode_name] = type('Mode', (), controls)()
            return success, message
        
        elif section == "planning":
            success, message = self.update_planning(data)
            if success:
                # Hot-reload planning in terra_handler
                if "active" in data:
                    terra_handler._follow_planning = data["active"]
                if "default_mode" in data:
                    terra_handler._default_mode = data["default_mode"]
            return success, message
        
        else:
            return False, f"Unknown config section: {section}"
