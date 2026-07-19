"""
Physical parameters and material properties for the Solid Tyre Curing Press.
"""

DEFAULT_PARAMS = {
    "Cp_steel": 490.0,      # J/kg·K (Mould specific heat)
    "Cp_rubber": 2000.0,    # J/kg·K (Rubber specific heat)
    "k_rubber": 0.20,       # W/m·K (Rubber thermal conductivity)
    "T_target": 130.0,      # °C (Target cure temperature)
    "T_ambient": 30.0,      # °C (Ambient room temperature)
    "h_loss": 10.0,         # W/m²·K (Heat loss coefficient)
    "T_sat": 152.0,         # °C (Steam saturation temperature at ~5 bar)
    "UA_steam": 500.0,      # W/K (Steam heat conductance)
    "h_fg": 2114e3,         # J/kg (Latent heat of steam vaporization)
    "cure_time_s": 6.5 * 3600  # seconds (Default cure hold duration)
}
