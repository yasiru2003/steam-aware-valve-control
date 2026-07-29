"""
tests/test_floor_percent_sweep.py

Batch test: sweeps FLOOR_PERCENT from 1% to 40% in 1% steps.
Runs real simulation for all 5 schedules at each value.
Outputs raw results to stdout.

Usage (from project root):
    python3 "Digital Twin Own/tests/test_floor_percent_sweep.py"
"""

import sys, os

# Ensure parent package (Digital Twin Own/) is importable
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

from simulation import run_simulation, total_steam_used
import controller

schedules = [
    ('schedule_1_peak_overlap.csv',    'Sched-1 (Overlap)'),
    ('schedule_2_staggered_15m.csv',   'Sched-2 (15m Lag)'),
    ('schedule_3_staggered_30m.csv',   'Sched-3 (30m Lag)'),
    ('schedule_4_idle_waste_test.csv', 'Sched-4 (Idle Gap)'),
    ('schedule_5_full_shift_heavy.csv','Sched-5 (4-Press)'),
]

SCHEDULES_DIR = os.path.join(BASE_DIR, 'schedules')

# 1% to 40% in 1% steps
floor_range = [fp / 100.0 for fp in range(1, 41)]

orig_fp = controller.FLOOR_PERCENT

print('=' * 130)
print('  BATCH TEST: FLOOR_PERCENT 1% -> 40% (1% STEPS)  |  Real simulation.py runs  |  5 schedules each step')
print('=' * 130)
header = (
    f"{'FLOOR_%':>9} | "
    f"{'Sched-1 Comp':>14} {'Steam':>8} {'Peak':>11} | "
    f"{'Sched-2 Comp':>14} {'Steam':>8} {'Peak':>11} | "
    f"{'Sched-3 Comp':>14} {'Steam':>8} {'Peak':>11} | "
    f"{'Sched-4 Comp':>14} {'Steam':>8} {'Peak':>11} | "
    f"{'Sched-5 Comp':>14} {'Steam':>8} {'Peak':>11}"
)
print(header)
print('-' * 130)

try:
    for fp in floor_range:
        controller.FLOOR_PERCENT = fp
        row = f"  {fp*100:5.0f}%    |"
        for filename, label in schedules:
            filepath = os.path.join(SCHEDULES_DIR, filename)
            log, comp_s = run_simulation(filepath, mode='smart')
            p_ids = log[-1].get('press_ids', [1, 2, 3])
            steam = total_steam_used(log, p_ids)
            peak  = max(r['total_steam_flow_kg_s'] for r in log)
            hrs   = comp_s / 3600.0
            mins  = comp_s / 60.0
            mark  = '*' if fp == 0.25 else ' '
            row  += f" {mark}{hrs:.3f}h({mins:.0f}m) {steam:.2f}kg {peak:.5f}  |"
        print(row)
finally:
    controller.FLOOR_PERCENT = orig_fp

print('=' * 130)
print(f'  * = Baseline (FLOOR_PERCENT = 0.25)')
print('Done.')
