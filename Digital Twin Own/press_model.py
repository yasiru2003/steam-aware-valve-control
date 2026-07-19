"""
CuringPress Physical Model & Cure Stage State Machine.
"""

from parameters import DEFAULT_PARAMS
from controller import PID


class CuringPress:
    """Simulates a solid tyre curing press physical model (V1: Single Lumped Temperature)."""

    def __init__(self, mass: float = 300.0, params: dict = None, kp=0.02, ki=0.00015, kd=0.01):
        self.mass = mass
        self.params = DEFAULT_PARAMS.copy()
        if params:
            self.params.update(params)

        self.T_press = self.params["T_ambient"]
        self.stage = "idle"       # Allowed stages: 'idle', 'heating', 'holding', 'cooling'
        self.hold_elapsed = 0.0
        self.steam_used_kg = 0.0
        self.pid = PID(kp=kp, ki=ki, kd=kd)

    def set_stage_from_schedule(self, production_active: bool):
        """Updates internal cure stage based on schedule and temperature."""
        if not production_active:
            self.stage = "idle"
            self.pid.reset()
            return
            
        cure_target = self.params["T_target"]
        cure_time = self.params["cure_time_s"]

        if self.stage == "idle":
            self.stage = "heating"
        elif self.stage == "heating" and self.T_press >= cure_target - 0.5:
            self.stage = "holding"
        elif self.stage == "holding" and self.hold_elapsed >= cure_time:
            self.stage = "cooling"

    def step(self, dt: float, production_active: bool, smart_idle_shutoff=True):
        """Advances physics equations and control loop by one timestep dt."""
        self.set_stage_from_schedule(production_active)

        # 1. Determine valve opening ratio u
        if self.stage in ("heating", "holding"):
            error = self.params["T_target"] - self.T_press
            u = self.pid.step(error, dt)
            if self.stage == "holding":
                self.hold_elapsed += dt
        elif self.stage == "cooling":
            u = 0.0
        else:  # idle
            # Naive control leaves valve cracked open at 15%; Smart control closes it completely
            u = 0.0 if smart_idle_shutoff else 0.15

        # 2. Thermal heat transfer calculation
        UA_steam = self.params["UA_steam"]
        T_sat = self.params["T_sat"]
        T_amb = self.params["T_ambient"]
        h_loss = self.params["h_loss"]
        Cp_steel = self.params["Cp_steel"]
        h_fg = self.params["h_fg"]

        Q_in = u * UA_steam * max(T_sat - self.T_press, 0.0)
        Q_loss = h_loss * (self.T_press - T_amb)
        Q_net = Q_in - Q_loss

        # 3. Temperature rate of change (°C/s) and update
        rate_dT = Q_net / (self.mass * Cp_steel)
        self.T_press += rate_dT * dt

        # 4. Steam flow (kg/s) and cumulative steam (kg)
        steam_flow = Q_in / h_fg
        self.steam_used_kg += steam_flow * dt

        return self.T_press, u, steam_flow
