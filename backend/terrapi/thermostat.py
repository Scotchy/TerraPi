"""
Thermostat controller for TerraPi.
Computes relay state based on temperature readings and configurable parameters.
"""


class Thermostat:
    """
    Thermostat controller that determines relay state based on temperature.
    
    Supports both cooling and heating modes with hysteresis to prevent
    rapid relay cycling (which can damage equipment and cause wear).
    
    Attributes:
        target_temp: Desired temperature setpoint
        hysteresis: Dead-band range (±) to prevent rapid cycling
        action: 'cooling' or 'heating' mode
    """
    
    def __init__(self, target_temp: float, hysteresis: float = 1.0, 
                 action: str = "cooling"):
        """
        Initialize thermostat controller.
        
        Args:
            target_temp: Target temperature in degrees Celsius
            hysteresis: Temperature tolerance band (default ±1.0°C)
            action: 'cooling' (turn on when hot) or 'heating' (turn on when cold)
        """
        self.target_temp = target_temp
        self.hysteresis = hysteresis
        self.action = action
        self._relay_state = False
    
    def compute_state(self, current_temp: float) -> bool:
        """
        Compute whether the relay should be ON or OFF.
        
        Uses hysteresis to prevent rapid cycling:
        - For cooling: ON when temp >= target + hysteresis, OFF when temp <= target - hysteresis
        - For heating: ON when temp <= target - hysteresis, OFF when temp >= target + hysteresis
        - Within the hysteresis band, the current state is maintained
        
        Args:
            current_temp: Current temperature reading from sensor
            
        Returns:
            True if relay should be ON, False if OFF
        """
        if self.action == "cooling":
            # Cooling: turn ON when temp exceeds (target + hysteresis)
            #          turn OFF when temp drops below (target - hysteresis)
            if current_temp >= self.target_temp + self.hysteresis:
                self._relay_state = True
            elif current_temp <= self.target_temp - self.hysteresis:
                self._relay_state = False
            # Otherwise, maintain current state (inside hysteresis band)
        
        elif self.action == "heating":
            # Heating: turn ON when temp drops below (target - hysteresis)
            #          turn OFF when temp exceeds (target + hysteresis)
            if current_temp <= self.target_temp - self.hysteresis:
                self._relay_state = True
            elif current_temp >= self.target_temp + self.hysteresis:
                self._relay_state = False
            # Otherwise, maintain current state (inside hysteresis band)
        
        return self._relay_state
    
    def set_state(self, state: bool):
        """
        Manually set the relay state.
        
        Useful for initializing state or forcing a specific state.
        
        Args:
            state: Desired relay state (True = ON, False = OFF)
        """
        self._relay_state = state
    
    @property
    def relay_state(self) -> bool:
        """Get the current relay state."""
        return self._relay_state
    
    def __repr__(self) -> str:
        return (f"Thermostat(target={self.target_temp}°C, hysteresis=±{self.hysteresis}°C, "
                f"action={self.action}, state={'ON' if self._relay_state else 'OFF'})")
