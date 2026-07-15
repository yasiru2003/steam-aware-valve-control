"""
Digital twin for a single solid tyre curing press.
Models temperature, valve position, and steam use through the
heating -> holding -> cooling -> idle stages, controlled by a PID
loop that tracks a temperature setpoint.
"""

import numpy as np

class PressParams:
    def __init__(
        self,
        UA_steam=450.0,     # W/K, steam-to-mould heat transfer conductance
        UA_amb=25.0,         # W/K, mould-to-ambient heat loss conductance
        m_cp=180_000.0,      # J/K, thermal mass of mould + rubber charge
        T_sat=152.0,         # deg C, saturation temp at supply steam pressure
        T_amb=30.0,          # deg C, ambient/room temperature
        h_fg=2114e3          # J/kg, latent heat of steam at supply pressure
    ):
        self.UA_steam = UA_steam
        self.UA_amb = UA_amb
        self.m_cp = m_cp
        self.T_sat = T_sat
        self.T_amb = T_amb
        self.h_fg = h_fg


class PID:
    def __init__(self, kp, ki, kd, u_min=0.0, u_max=1.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.u_min = u_min
        self.u_max = u_max
        self.integral = 0.0
        self.prev_error = None

    def step(self, error, dt):
        self.integral += error * dt
        derivative = 0.0 if self.prev_error is None else (error - self.prev_error) / dt
        self.prev_error = error
        u = self.kp * error + self.ki * self.integral + self.kd * derivative
        return float(np.clip(u, self.u_min, self.u_max))


class CuringPress:
    """One press, tracked through cure stages."""

    def __init__(self, params: PressParams, cure_temp=130.0, cure_time_s=6.5 * 3600, kp=0.02, ki=0.00015, kd=0.01):
        self.p = params
        self.cure_temp = cure_temp
        self.cure_time_s = cure_time_s
        self.T = params.T_amb
        self.stage = "idle"       # idle, heating, holding, cooling
        self.hold_elapsed = 0.0
        self.steam_used_kg = 0.0
        self.pid = PID(kp=kp, ki=ki, kd=kd)

    def set_stage_from_schedule(self, production_active: bool):
        if not production_active:
            self.stage = "idle"
            self.pid.integral = 0.0
            return
        if self.stage == "idle":
            self.stage = "heating"
        elif self.stage == "heating" and self.T >= self.cure_temp - 0.5:
            self.stage = "holding"
        elif self.stage == "holding" and self.hold_elapsed >= self.cure_time_s:
            self.stage = "cooling"

    def step(self, dt, production_active: bool, smart_idle_shutoff=True):
        self.set_stage_from_schedule(production_active)

        if self.stage in ("heating", "holding"):
            error = self.cure_temp - self.T
            u = self.pid.step(error, dt)
            if self.stage == "holding":
                self.hold_elapsed += dt
        elif self.stage == "cooling":
            u = 0.0
        else:  # idle
            # naive control leaves the valve cracked open; smart control shuts it
            u = 0.0 if smart_idle_shutoff else 0.15

        Q_in = u * self.p.UA_steam * max(self.p.T_sat - self.T, 0.0)
        Q_loss = self.p.UA_amb * (self.T - self.p.T_amb)
        dT = (Q_in - Q_loss) / self.p.m_cp * dt
        self.T += dT

        steam_flow = Q_in / self.p.h_fg   # kg/s
        self.steam_used_kg += steam_flow * dt

        return self.T, u, steam_flow


def run_simulation(
    params: PressParams,
    cure_temp=130.0,
    cure_time_s=6.5 * 3600,
    hours=10.0,
    dt=5.0,
    gap_start_s=7.0 * 3600,
    gap_duration_s=1.5 * 3600,
    kp=0.02,
    ki=0.00015,
    kd=0.01,
    smart_idle_shutoff=True
):
    press = CuringPress(params, cure_temp=cure_temp, cure_time_s=cure_time_s, kp=kp, ki=ki, kd=kd)
    n_steps = int(hours * 3600 / dt)

    times = np.arange(n_steps) * dt
    schedule = np.ones(n_steps, dtype=bool)
    
    # Calculate step indices for the idle gap
    gap_start_idx = int(gap_start_s / dt)
    gap_end_idx = int((gap_start_s + gap_duration_s) / dt)
    
    # Clip indices to prevent index out of bounds
    gap_start_idx = max(0, min(gap_start_idx, n_steps))
    gap_end_idx = max(0, min(gap_end_idx, n_steps))
    
    schedule[gap_start_idx:gap_end_idx] = False

    T_hist, u_hist, steam_hist, stage_hist = [], [], [], []
    for i in range(n_steps):
        T, u, steam_flow = press.step(dt, schedule[i], smart_idle_shutoff)
        T_hist.append(T)
        u_hist.append(u)
        steam_hist.append(steam_flow)
        stage_hist.append(press.stage)

    return times, np.array(T_hist), np.array(u_hist), np.array(steam_hist), stage_hist, press.steam_used_kg
