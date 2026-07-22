"""
parameters.py

Physical constants and default parameters for solid tyre curing press simulation.
Tuned for realistic 25-minute steam ramp-up times.
"""

DEFAULT_PARAMS = {
    "T_ambient": 30.0,        # Ambient room temperature (°C)
    "T_sat": 143.7,           # Steam saturation temperature at ~3 bar (°C)
    "T_target": 130.0,        # Curing target temperature (°C)
    "cure_time_s": 23400.0,   # Target curing hold time (~6.5 hours in seconds)
    "UA_steam": 250.0,        # Heat transfer coefficient for steam inlet (W/°C) - 25-min ramp
    "h_loss": 3.5,            # Ambient heat loss coefficient (W/°C)
    "Cp_steel": 460.0,        # Specific heat capacity of steel mold (J/kg·°C)
    "h_fg": 2133000.0,        # Latent heat of vaporization of steam (J/kg)
}

TARGET_TEMP = DEFAULT_PARAMS["T_target"]
