"""
profiles.py

Steam demand profiles and synthetic instance generator for tyre curing presses.
Supports both homogeneous and heterogeneous press configurations.
"""

from dataclasses import dataclass
from typing import List, Dict
import numpy as np


@dataclass
class PressSpec:
    press_id: str
    tyre_type: str
    cycle_duration_min: int   # Total duration in minutes
    earliest_start_min: int   # Earliest allowed start time (min)
    latest_start_min: int     # Latest allowed start time (min)
    demand_profile: np.ndarray  # Steam demand array at dt_min intervals (kg/h)


# Predefined industrial solid tyre categories
TYRE_TYPES = {
    "Small_Solid": {
        "cycle_duration_min": 240,   # 4.0 hours
        "heatup_duration_min": 30,
        "peak_steam_kgh": 32.0,      # kg/h during initial heatup
        "hold_steam_kgh": 4.5,       # kg/h during holding
    },
    "Medium_Solid": {
        "cycle_duration_min": 390,   # 6.5 hours (standard 300kg press)
        "heatup_duration_min": 45,
        "peak_steam_kgh": 48.0,      # kg/h during initial heatup
        "hold_steam_kgh": 6.0,       # kg/h during holding
    },
    "Large_Industrial": {
        "cycle_duration_min": 480,   # 8.0 hours
        "heatup_duration_min": 60,
        "peak_steam_kgh": 65.0,      # kg/h during initial heatup
        "hold_steam_kgh": 8.5,       # kg/h during holding
    },
    "Heavy_OTR": {
        "cycle_duration_min": 600,   # 10.0 hours
        "heatup_duration_min": 75,
        "peak_steam_kgh": 82.0,      # kg/h during initial heatup
        "hold_steam_kgh": 11.0,      # kg/h during holding
    },
}


def generate_demand_curve(tyre_type: str, dt_min: int = 5) -> np.ndarray:
    """
    Generates a realistic steam demand profile (kg/h) sampled at dt_min steps.
    Consists of:
      1. Rapid heat-up phase (high steam condensation rate)
      2. Tapering transition
      3. Steady holding phase (balancing ambient thermal losses)
      4. Depressurization / cooling phase (zero steam consumption)
    """
    spec = TYRE_TYPES[tyre_type]
    total_steps = spec["cycle_duration_min"] // dt_min
    heatup_steps = spec["heatup_duration_min"] // dt_min
    hold_steps = int(total_steps * 0.85) - heatup_steps
    cooling_steps = total_steps - heatup_steps - hold_steps

    profile = []
    # Heat-up phase: High draw, tapering slightly as temperature rises
    for step in range(heatup_steps):
        frac = step / max(1, heatup_steps - 1)
        # Condensing steam flow starts at maximum and tapers as T_press approaches T_sat
        flow = spec["peak_steam_kgh"] * (1.0 - 0.25 * (frac ** 0.8))
        profile.append(flow)

    # Holding phase: Steady consumption to offset convection & radiation losses
    for step in range(hold_steps):
        profile.append(spec["hold_steam_kgh"])

    # Depressurization / cooling phase: steam valve closed
    for step in range(cooling_steps):
        profile.append(0.0)

    return np.array(profile, dtype=float)


def generate_homogeneous_instances(
    num_presses: int,
    tyre_type: str = "Medium_Solid",
    max_stagger_window_min: int = 90,
    dt_min: int = 5
) -> List[PressSpec]:
    """
    Creates an instance where all presses have identical tyre type and demand profile.
    High symmetry.
    """
    demand = generate_demand_curve(tyre_type, dt_min=dt_min)
    cycle_dur = TYRE_TYPES[tyre_type]["cycle_duration_min"]

    presses = []
    for i in range(1, num_presses + 1):
        presses.append(
            PressSpec(
                press_id=f"Press_{i:02d}",
                tyre_type=tyre_type,
                cycle_duration_min=cycle_dur,
                earliest_start_min=0,
                latest_start_min=max_stagger_window_min,
                demand_profile=demand.copy()
            )
        )
    return presses


def generate_heterogeneous_instances(
    num_presses: int,
    max_stagger_window_min: int = 90,
    dt_min: int = 5,
    seed: int = 42
) -> List[PressSpec]:
    """
    Creates an instance where presses have varying tyre sizes, differing cure durations,
    and distinct steam demand profiles. Broken symmetry.
    """
    rng = np.random.RandomState(seed)
    tyre_choices = list(TYRE_TYPES.keys())

    # Pre-cache demand curves
    curves = {t: generate_demand_curve(t, dt_min=dt_min) for t in tyre_choices}

    presses = []
    for i in range(1, num_presses + 1):
        chosen_type = rng.choice(tyre_choices)
        cycle_dur = TYRE_TYPES[chosen_type]["cycle_duration_min"]

        presses.append(
            PressSpec(
                press_id=f"Press_{i:02d}",
                tyre_type=chosen_type,
                cycle_duration_min=cycle_dur,
                earliest_start_min=0,
                latest_start_min=max_stagger_window_min,
                demand_profile=curves[chosen_type].copy()
            )
        )
    return presses
