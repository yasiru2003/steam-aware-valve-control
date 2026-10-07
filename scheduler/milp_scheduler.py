"""
milp_scheduler.py

Mixed Integer Linear Programming (MILP) Steam Demand Peak-Flattening Scheduler.
Formulated with PuLP and solved with Coin-or CBC.
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import time
import numpy as np
import pulp

from profiles import PressSpec


@dataclass
class ScheduleResult:
    status: str
    solve_time_sec: float
    baseline_peak_kgh: float
    scheduled_peak_kgh: float
    peak_reduction_pct: float
    mip_gap: Optional[float]
    assigned_starts_min: Dict[str, int]
    assigned_starts_hour: Dict[str, float]
    time_axis_min: np.ndarray
    baseline_steam_curve: np.ndarray
    scheduled_steam_curve: np.ndarray


def calculate_steam_curve(
    presses: List[PressSpec],
    start_times_min: Dict[str, int],
    dt_min: int,
    total_horizon_steps: int
) -> np.ndarray:
    """Calculates aggregated steam consumption (kg/h) across all presses given start times."""
    curve = np.zeros(total_horizon_steps, dtype=float)
    for p in presses:
        start_step = start_times_min[p.press_id] // dt_min
        profile = p.demand_profile
        end_step = min(total_horizon_steps, start_step + len(profile))
        dur_steps = end_step - start_step
        if dur_steps > 0:
            curve[start_step:end_step] += profile[:dur_steps]
    return curve


def solve_steam_schedule(
    presses: List[PressSpec],
    dt_min: int = 5,
    time_limit_sec: int = 60,
    gap_rel: float = 0.01,
    verbose: bool = False
) -> ScheduleResult:
    """
    Formulates and solves the MILP peak-flattening scheduling problem.

    Epigraph formulation:
        Minimise P_peak + epsilon * sum(start_time_offsets)
        Subject to:
            sum_{s in W_i} x_{i, s} = 1                       forall i in Presses
            P_peak >= sum_{i} sum_{s} d_i(t - s) * x_{i, s}    forall t in TimeHorizon
            x_{i, s} in {0, 1}
    """
    # 1. Determine discrete time horizon
    max_horizon_min = max(p.latest_start_min + p.cycle_duration_min for p in presses)
    total_steps = (max_horizon_min // dt_min) + 1
    time_axis_min = np.arange(total_steps) * dt_min

    # 2. Compute Unstaggered Baseline (All presses starting at earliest_start_min)
    baseline_starts = {p.press_id: p.earliest_start_min for p in presses}
    baseline_curve = calculate_steam_curve(presses, baseline_starts, dt_min, total_steps)
    baseline_peak = float(np.max(baseline_curve))

    # 3. Create PuLP MILP Problem
    prob = pulp.LpProblem("Tyre_Press_Steam_Peak_Scheduler", pulp.LpMinimize)

    # Epigraph variable: Peak steam draw across time
    P_peak = pulp.LpVariable("P_peak", lowBound=0.0, cat=pulp.LpContinuous)

    # Binary assignment variables x[i, s]
    x_vars: Dict[Tuple[str, int], pulp.LpVariable] = {}
    slots_per_press: Dict[str, List[int]] = {}

    for p in presses:
        allowed_slots = list(range(p.earliest_start_min, p.latest_start_min + 1, dt_min))
        slots_per_press[p.press_id] = allowed_slots
        for s in allowed_slots:
            var_name = f"x_{p.press_id}_s{s}"
            x_vars[(p.press_id, s)] = pulp.LpVariable(var_name, cat=pulp.LpBinary)

    # Constraint 1: Exactly one start time slot per press
    for p in presses:
        prob += (
            pulp.lpSum([x_vars[(p.press_id, s)] for s in slots_per_press[p.press_id]]) == 1,
            f"AssignOneSlot_{p.press_id}"
        )

    # Demand contributions: pre-index by global time step t to build constraints efficiently
    # total_demand(t) = sum_{i, s: s_step <= t < s_step + len(d_i)} d_i[t - s_step] * x[i, s]
    step_demands: List[List[pulp.LpAffineExpression]] = [[] for _ in range(total_steps)]

    for p in presses:
        profile = p.demand_profile
        prof_len = len(profile)
        for s in slots_per_press[p.press_id]:
            s_step = s // dt_min
            var = x_vars[(p.press_id, s)]
            for tau_step in range(prof_len):
                t = s_step + tau_step
                if t < total_steps:
                    flow = profile[tau_step]
                    if flow > 0.001:
                        step_demands[t].append(flow * var)

    # Constraint 2: Epigraph peak bounds P_peak >= D_total(t)
    for t in range(total_steps):
        if step_demands[t]:
            prob += (
                P_peak >= pulp.lpSum(step_demands[t]),
                f"PeakSteamBound_t{t}"
            )

    # Objective: Minimise peak steam draw (with small tie-breaker for earlier start times)
    epsilon = 1e-4  # Secondary priority: prefer earlier starts if peak is unaffected
    start_delay_penalty = pulp.lpSum([
        (s / max_horizon_min) * x_vars[(p.press_id, s)]
        for p in presses
        for s in slots_per_press[p.press_id]
    ])
    prob += P_peak + (epsilon * start_delay_penalty), "Minimise_Peak_Steam_Draw"

    # 4. Solve with CBC
    cbc_solver = pulp.PULP_CBC_CMD(
        timeLimit=time_limit_sec,
        gapRel=gap_rel,
        msg=1 if verbose else 0
    )

    start_timer = time.perf_counter()
    solver_status_code = prob.solve(cbc_solver)
    elapsed_time = time.perf_counter() - start_timer

    status_str = pulp.LpStatus[solver_status_code]

    # Extract chosen start times
    assigned_starts_min = {}
    assigned_starts_hour = {}

    for p in presses:
        chosen_s = p.earliest_start_min
        for s in slots_per_press[p.press_id]:
            val = pulp.value(x_vars[(p.press_id, s)])
            if val is not None and val > 0.5:
                chosen_s = s
                break
        assigned_starts_min[p.press_id] = chosen_s
        assigned_starts_hour[p.press_id] = round(chosen_s / 60.0, 3)

    # Calculate final scheduled curve
    scheduled_curve = calculate_steam_curve(presses, assigned_starts_min, dt_min, total_steps)
    scheduled_peak = float(np.max(scheduled_curve))
    reduction_pct = (
        ((baseline_peak - scheduled_peak) / baseline_peak * 100.0)
        if baseline_peak > 0 else 0.0
    )

    return ScheduleResult(
        status=status_str,
        solve_time_sec=round(elapsed_time, 3),
        baseline_peak_kgh=round(baseline_peak, 2),
        scheduled_peak_kgh=round(scheduled_peak, 2),
        peak_reduction_pct=round(reduction_pct, 2),
        mip_gap=None,
        assigned_starts_min=assigned_starts_min,
        assigned_starts_hour=assigned_starts_hour,
        time_axis_min=time_axis_min,
        baseline_steam_curve=baseline_curve,
        scheduled_steam_curve=scheduled_curve
    )
