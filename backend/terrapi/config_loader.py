"""
TerraPi Configuration Loader
Custom YAML configuration with environment variable substitution and dynamic object instantiation.
Replaces xpipe dependency.
"""

import os
import re
import yaml
from typing import Any, Dict

import terrapi.sensor as sensor_module
import terrapi.control as control_module


class Config:
    """Configuration object with attribute access to nested values."""
    
    def __init__(self, data: Dict[str, Any]):
        self._data = data
    
    def __getattr__(self, name: str) -> Any:
        if name.startswith('_'):
            return super().__getattribute__(name)
        
        value = self._data.get(name)
        if value is None:
            raise AttributeError(f"Config has no attribute '{name}'")
        
        if isinstance(value, dict):
            return Config(value)
        return value
    
    def __getitem__(self, key: str) -> Any:
        value = self._data[key]
        if isinstance(value, dict):
            return Config(value)
        return value
    
    def get(self, key: str, default: Any = None) -> Any:
        value = self._data.get(key, default)
        if isinstance(value, dict):
            return Config(value)
        return value
    
    def keys(self):
        return self._data.keys()
    
    def items(self):
        for key, value in self._data.items():
            if isinstance(value, dict):
                yield key, Config(value)
            else:
                yield key, value
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert back to plain dict."""
        return self._data


def substitute_env_vars(value: str) -> str:
    """Replace ${VAR_NAME} with environment variable values."""
    if not isinstance(value, str):
        return value
    
    pattern = r'\$\{([^}]+)\}'
    
    def replacer(match):
        var_name = match.group(1)
        env_value = os.environ.get(var_name, '')
        if not env_value:
            print(f"Warning: Environment variable {var_name} not set")
        return env_value
    
    return re.sub(pattern, replacer, value)


def process_config(data: Any) -> Any:
    """Recursively process config values, substituting env vars."""
    if isinstance(data, dict):
        return {k: process_config(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [process_config(item) for item in data]
    elif isinstance(data, str):
        return substitute_env_vars(data)
    return data


def instantiate_sensors(sensors_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Create sensor instances from config.
    
    Config format:
        sensor_name:
            type: ClassName
            pin: 17
    """
    sensors = {}
    for name, config in sensors_config.items():
        sensor_type = config.get('type')
        if not sensor_type:
            raise ValueError(f"Sensor '{name}' missing 'type' field")
        
        sensor_class = getattr(sensor_module, sensor_type, None)
        if sensor_class is None:
            raise ValueError(f"Unknown sensor type: {sensor_type}")
        
        # Get constructor args (everything except 'type')
        kwargs = {k: v for k, v in config.items() if k != 'type'}
        sensors[name] = sensor_class(**kwargs)
    
    return sensors


def instantiate_controls(controls_config: Dict[str, Any]) -> Dict[str, control_module.Control]:
    """
    Create control instances from config.
    
    Config format:
        control_name:
            type: ClassName
            pin: 7
    """
    controls = {}
    for name, config in controls_config.items():
        control_type = config.get('type')
        if not control_type:
            raise ValueError(f"Control '{name}' missing 'type' field")
        
        control_class = getattr(control_module, control_type, None)
        if control_class is None:
            raise ValueError(f"Unknown control type: {control_type}")
        
        # Get constructor args (everything except 'type')
        kwargs = {k: v for k, v in config.items() if k != 'type'}
        controls[name] = control_class(**kwargs)
    
    return controls


def load_config(config_path: str) -> Config:
    """
    Load configuration from YAML file.
    
    - Substitutes ${ENV_VAR} patterns with environment variables
    - Returns a Config object with attribute access
    
    Note: Sensors and controls are NOT instantiated here.
    Use Terrarium class to instantiate them.
    """
    with open(config_path, 'r') as f:
        raw_config = yaml.safe_load(f)
    
    # Process environment variables
    processed = process_config(raw_config)
    
    return Config(processed)


def save_config(config_path: str, config: Dict[str, Any]) -> None:
    """Save configuration to YAML file."""
    with open(config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
