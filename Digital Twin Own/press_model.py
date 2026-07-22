"""
press_model.py

CuringPress Physical Model & Cure Stage State Machine.
Standardized on the Convective Heat Exchanger Model (Q_in = u * UA_steam * (T_sat - T_press)).
Steam mass flow rate is derived from heat input divided by latent heat of vaporization (h_fg).
"""

from parameters import DEFAULT_PARAMS, TARGET_TEMP


class CuringPress:
    """
    Simulates a solid tyre curing press physical model (Single Lumped Temperature Model).
    Uses convective condensing heat transfer Q = u * UA_steam * (T_sat - T_press).
    """

    def __init__(self, press_id: str = "Press_1", mass: float = 300.0, params: dict = None):
        self.press_id = str(press_id)
        self.mass = mass
        self.params = DEFAULT_PARAMS.copy()
        if params:
            self.params.update(params)

        self.temperature = self.params["T_ambient"]
        self.stage = "idle"       # Explicit stages: 'idle', 'heating', 'holding', 'cooling'
        self.hold_elapsed = 0.0
        self.total_steam_used_kg = 0.0
        self.steam_flow_kg_s = 0.0
        self.u_applied = 0.0

    @property
    def T_press(self):
        """Alias for temperature property."""
        return self.temperature

    @T_press.setter
    def T_press(self, value):
        self.temperature = value

    @property
    def steam_used_kg(self):
        """Alias for cumulative steam used."""
        return self.total_steam_used_kg

    def set_stage_from_schedule(self, production_active: bool):
        """Updates internal cure stage based on schedule and temperature."""
        if not production_active:
            self.stage = "idle"
            self.hold_elapsed = 0.0
            return

        cure_target = self.params["T_target"]
        cure_time = self.params["cure_time_s"]

        if self.stage == "idle":
            self.stage = "heating"
        elif self.stage == "heating" and self.temperature >= cure_target - 0.5:
            self.stage = "holding"
        elif self.stage == "holding" and self.hold_elapsed >= cure_time:
            self.stage = "cooling"

    def update(self, u: float, production_active: bool, dt: float):
        """
        Advances physics step given applied valve opening percentage u [0.0, 1.0].
        Convective/Condensing Heat Exchanger Equation:
            Q_in = u * UA_steam * max(T_sat - T_press, 0.0)
        Derived Steam Mass Flow:
            steam_flow_kg_s = Q_in / h_fg
        """
        self.set_stage_from_schedule(production_active)

        # Clamp valve position between 0% and 100%
        u_clamped = max(0.0, min(1.0, float(u)))
        self.u_applied = u_clamped

        if self.stage == "holding":
            self.hold_elapsed += dt

        UA_steam = self.params["UA_steam"]
        T_sat = self.params["T_sat"]
        T_amb = self.params["T_ambient"]
        h_loss = self.params["h_loss"]
        Cp_steel = self.params["Cp_steel"]
        h_fg = self.params["h_fg"]

        # 1. Thermal heat transfer calculation (Convective Heat Exchanger Model Q = UA * ΔT)
        Q_in = u_clamped * UA_steam * max(T_sat - self.temperature, 0.0)
        Q_loss = h_loss * (self.temperature - T_amb)
        Q_net = Q_in - Q_loss

        # 2. Temperature rate of change (°C/s) and update (Euler Integration)
        rate_dT = Q_net / (self.mass * Cp_steel)
        self.temperature += rate_dT * dt

        # 3. Derived steam flow rate (kg/s) and cumulative steam mass (kg)
        self.steam_flow_kg_s = Q_in / h_fg
        self.total_steam_used_kg += self.steam_flow_kg_s * dt

        return self.temperature, self.u_applied, self.steam_flow_kg_s

    def apply_physics_step(self, u: float, dt: float):
        """Backward compatibility alias for update."""
        return self.update(u, production_active=True, dt=dt)

    def get_state(self):
        """Returns dictionary of state variables for logging."""
        return {
            "temperature": self.temperature,
            "stage": self.stage,
            "valve_opening": self.u_applied,
            "steam_flow_kg_s": self.steam_flow_kg_s,
            "total_steam_used_kg": self.total_steam_used_kg
        }
