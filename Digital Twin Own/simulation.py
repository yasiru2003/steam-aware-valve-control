"""
Simulation Runner Engine for Digital Twin.
"""

import numpy as np
from press_model import CuringPress


def run_simulation(
    mass=300.0,
    params=None,
    hours=10.0,
    dt=5.0,
    gap_start_s=7.0 * 3600,
    gap_duration_s=1.5 * 3600,
    kp=0.02,
    ki=0.00015,
    kd=0.01,
    smart_idle_shutoff=True
):
    """Executes a full simulation run over specified hours."""
    press = CuringPress(mass=mass, params=params, kp=kp, ki=ki, kd=kd)
    n_steps = int(hours * 3600 / dt)

    times = np.arange(n_steps) * dt
    schedule = np.ones(n_steps, dtype=bool)

    # Define scheduled idle gap
    gap_start_idx = max(0, min(int(gap_start_s / dt), n_steps))
    gap_end_idx = max(0, min(int((gap_start_s + gap_duration_s) / dt), n_steps))
    schedule[gap_start_idx:gap_end_idx] = False

    T_hist, u_hist, steam_hist, stage_hist = [], [], [], []

    for i in range(n_steps):
        T_val, u_val, steam_flow = press.step(dt, schedule[i], smart_idle_shutoff)
        T_hist.append(T_val)
        u_hist.append(u_val)
        steam_hist.append(steam_flow)
        stage_hist.append(press.stage)

    return (
        times,
        np.array(T_hist),
        np.array(u_hist),
        np.array(steam_hist),
        stage_hist,
        press.steam_used_kg
    )


if __name__ == "__main__":
    print("--- Running Modular Digital Twin Simulation Test ---")
    
    # Run Smart Control
    t_s, T_s, u_s, flow_s, stages_s, total_s = run_simulation(smart_idle_shutoff=True)
    
    # Run Naive Control
    t_n, T_n, u_n, flow_n, stages_n, total_n = run_simulation(smart_idle_shutoff=False)

    saved_kg = total_n - total_s
    pct_saved = (saved_kg / total_n) * 100.0

    print(f"Naive Steam Consumption  : {total_n:.2f} kg")
    print(f"Smart Steam Consumption  : {total_s:.2f} kg")
    print(f"Steam Savings            : {saved_kg:.2f} kg ({pct_saved:.1f}%)")
