"""
benchmark.py

Benchmark suite for evaluating the MILP peak-flattening scheduler.
Tests across realistic plant scales (8 to 20 presses) for both
Homogeneous and Heterogeneous press configurations.

Outputs results as CSV files:
  1. benchmark_results.csv: Summary metrics for all test runs
  2. schedule_solution_<type>_<N>.csv: Discrete schedule assignments (compatible with Digital Twin format)
  3. steam_profiles_timeseries.csv: Baseline vs scheduled aggregated steam draw time series
"""

import argparse
import os
import time
from typing import List, Dict
import pandas as pd
import numpy as np

from profiles import (
    generate_homogeneous_instances,
    generate_heterogeneous_instances,
    TYRE_TYPES
)
from milp_scheduler import solve_steam_schedule, ScheduleResult


def run_benchmark(
    press_counts: List[int] = None,
    time_limit_sec: int = 30,
    dt_min: int = 5,
    output_dir: str = "./results"
) -> pd.DataFrame:
    if press_counts is None:
        press_counts = [8, 10, 12, 14, 16, 18, 20]

    os.makedirs(output_dir, exist_ok=True)
    benchmark_records = []
    timeseries_frames = []

    print(f"{'='*80}")
    print(f"ILP STEAM SCHEDULER BENCHMARK SUITE")
    print(f"Scale: {press_counts} presses | Time Limit: {time_limit_sec}s | Step: {dt_min} min")
    print(f"{'='*80}\n")

    for n in press_counts:
        for inst_type in ["Homogeneous", "Heterogeneous"]:
            print(f"--> Running {inst_type} Instance with N={n} presses...", end="", flush=True)

            if inst_type == "Homogeneous":
                presses = generate_homogeneous_instances(
                    num_presses=n,
                    tyre_type="Medium_Solid",
                    max_stagger_window_min=90,
                    dt_min=dt_min
                )
            else:
                presses = generate_heterogeneous_instances(
                    num_presses=n,
                    max_stagger_window_min=90,
                    dt_min=dt_min,
                    seed=42 + n
                )

            t0 = time.time()
            res: ScheduleResult = solve_steam_schedule(
                presses=presses,
                dt_min=dt_min,
                time_limit_sec=time_limit_sec,
                verbose=False
            )
            elapsed = time.time() - t0

            print(f" Done in {res.solve_time_sec:.2f}s | Peak: {res.baseline_peak_kgh:.1f} -> {res.scheduled_peak_kgh:.1f} kg/h ({res.peak_reduction_pct:.1f}% reduction) [{res.status}]")

            # Record benchmark summary row
            record = {
                "instance_type": inst_type,
                "num_presses": n,
                "solver_status": res.status,
                "solve_time_sec": res.solve_time_sec,
                "baseline_peak_kgh": res.baseline_peak_kgh,
                "scheduled_peak_kgh": res.scheduled_peak_kgh,
                "peak_reduction_kgh": round(res.baseline_peak_kgh - res.scheduled_peak_kgh, 2),
                "peak_reduction_pct": res.peak_reduction_pct,
                "time_limit_sec": time_limit_sec,
                "time_step_min": dt_min,
            }
            benchmark_records.append(record)

            # Export individual schedule CSV compatible with Digital Twin format
            # Format: press_id,start_hour,cure_duration_hours,idle_gap_start_hour,idle_gap_duration_hours
            schedule_rows = []
            for p in presses:
                start_h = res.assigned_starts_hour[p.press_id]
                cure_h = round(p.cycle_duration_min / 60.0, 2)
                schedule_rows.append({
                    "press_id": p.press_id,
                    "tyre_type": p.tyre_type,
                    "start_hour": start_h,
                    "cure_duration_hours": cure_h,
                    "idle_gap_start_hour": 999999.0,
                    "idle_gap_duration_hours": 0.0
                })

            sched_df = pd.DataFrame(schedule_rows)
            sched_csv_path = os.path.join(output_dir, f"schedule_{inst_type.lower()}_n{n}.csv")
            sched_df.to_csv(sched_csv_path, index=False)

            # Record time series for comparison
            ts_df = pd.DataFrame({
                "instance_type": inst_type,
                "num_presses": n,
                "time_min": res.time_axis_min,
                "time_hour": np.round(res.time_axis_min / 60.0, 2),
                "baseline_steam_kgh": np.round(res.baseline_steam_curve, 2),
                "scheduled_steam_kgh": np.round(res.scheduled_steam_curve, 2)
            })
            timeseries_frames.append(ts_df)

    # 1. Save main benchmark results CSV
    results_df = pd.DataFrame(benchmark_records)
    summary_csv_path = os.path.join(output_dir, "benchmark_results.csv")
    results_df.to_csv(summary_csv_path, index=False)
    print(f"\n[+] Saved benchmark summary to: {summary_csv_path}")

    # 2. Save aggregated time-series profiles CSV
    all_ts_df = pd.concat(timeseries_frames, ignore_index=True)
    timeseries_csv_path = os.path.join(output_dir, "steam_profiles_timeseries.csv")
    all_ts_df.to_csv(timeseries_csv_path, index=False)
    print(f"[+] Saved time-series comparison to: {timeseries_csv_path}")

    # Also save in root directory for easy access
    root_summary_path = "benchmark_results.csv"
    results_df.to_csv(root_summary_path, index=False)
    print(f"[+] Copied root CSV to: {root_summary_path}\n")

    return results_df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run MILP Steam Scheduler Benchmark")
    parser.add_argument("--limit", type=int, default=20, help="CBC time limit in seconds per instance")
    parser.add_argument("--step", type=int, default=5, help="Time discretization step in minutes")
    parser.add_argument("--output", type=str, default="./results", help="Directory for CSV outputs")
    args = parser.parse_args()

    run_benchmark(
        press_counts=[8, 10, 12, 14, 16, 18, 20],
        time_limit_sec=args.limit,
        dt_min=args.step,
        output_dir=args.output
    )
