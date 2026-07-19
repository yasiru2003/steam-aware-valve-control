"""
Multi-Press Digital Twin Simulation Engine.
Runs concurrent presses on a shared boiler line, evaluating Peak Demand Smoothing and Idle Shutoff.
"""

import numpy as np
import pandas as pd
from press_model import CuringPress
from controller import PeakSmoothingController
from schedule_reader import load_schedule_from_csv


def run_multi_press_simulation(
    schedule_filepath="Digital Twin Own/sample_schedule.csv",
    mass=300.0,
    params=None,
    hours=12.0,
    dt=5.0,
    kp=0.02,
    ki=0.00015,
    kd=0.01,
    smart_idle_shutoff=True,
    enable_peak_smoothing=True,
    max_boiler_flow_kg_s=0.06
):
    """
    Executes a multi-press simulation across all presses defined in the production schedule.
    """
    times, schedules_dict, df_schedule = load_schedule_from_csv(schedule_filepath, hours=hours, dt=dt)
    n_steps = len(times)

    presses = {
        p_id: CuringPress(press_id=p_id, mass=mass, params=params, kp=kp, ki=ki, kd=kd)
        for p_id in schedules_dict.keys()
    }

    peak_controller = PeakSmoothingController(max_allowed_flow_kg_s=max_boiler_flow_kg_s)

    # Data structures to store time-series histories per press
    history = {
        p_id: {
            "T": [],
            "u": [],
            "steam_flow": [],
            "stage": [],
            "cum_steam": []
        }
        for p_id in presses.keys()
    }
    
    total_boiler_flow = []

    for i in range(n_steps):
        # Step 1: Gather raw requested valve signals from all presses
        raw_valve_signals = {
            p_id: press.get_requested_valve_signal(dt, schedules_dict[p_id][i], smart_idle_shutoff)
            for p_id, press in presses.items()
        }

        # Step 2: Apply peak demand smoothing across presses
        final_valve_signals = peak_controller.apply_smoothing(
            raw_valve_signals, 
            presses, 
            enable_smoothing=enable_peak_smoothing
        )

        step_boiler_flow = 0.0

        # Step 3: Apply physical step to all presses
        for p_id, press in presses.items():
            u_final = final_valve_signals[p_id]
            T_val, u_applied, flow_rate = press.apply_physics_step(u_final, dt)

            history[p_id]["T"].append(T_val)
            history[p_id]["u"].append(u_applied)
            history[p_id]["steam_flow"].append(flow_rate)
            history[p_id]["stage"].append(press.stage)
            history[p_id]["cum_steam"].append(press.steam_used_kg)

            step_boiler_flow += flow_rate

        total_boiler_flow.append(step_boiler_flow)

    total_steam_kg = sum(press.steam_used_kg for press in presses.values())
    peak_boiler_flow_kg_s = max(total_boiler_flow)

    return (
        times,
        history,
        np.array(total_boiler_flow),
        total_steam_kg,
        peak_boiler_flow_kg_s,
        df_schedule
    )


if __name__ == "__main__":
    print("--- Running Multi-Press Digital Twin Simulation Test ---")
    
    # 1. Run Conventional Unmanaged Simulation (No peak smoothing, 15% idle crack)
    t_conv, hist_conv, flow_conv, total_conv, peak_conv, _ = run_multi_press_simulation(
        smart_idle_shutoff=False,
        enable_peak_smoothing=False
    )

    # 2. Run Smart Managed Simulation (Peak smoothing + 0% idle shutoff)
    t_smart, hist_smart, flow_smart, total_smart, peak_smart, _ = run_multi_press_simulation(
        smart_idle_shutoff=True,
        enable_peak_smoothing=True
    )

    steam_saved = total_conv - total_smart
    pct_saved = (steam_saved / total_conv) * 100.0
    peak_flattened_pct = ((peak_conv - peak_smart) / peak_conv) * 100.0

    print(f"Conventional Total Steam : {total_conv:.2f} kg | Peak Flow: {peak_conv:.4f} kg/s")
    print(f"Smart Managed Total Steam: {total_smart:.2f} kg | Peak Flow: {peak_smart:.4f} kg/s")
    print(f"Total Steam Saved       : {steam_saved:.2f} kg ({pct_saved:.1f}%)")
    print(f"Boiler Peak Flattened    : {peak_flattened_pct:.1f}% Reduction in Peak Demand Spike")
