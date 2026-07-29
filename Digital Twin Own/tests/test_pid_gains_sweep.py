"""
tests/test_pid_gains_sweep.py

Batch test: sweeps Kp, Ki, Kd individually across a range of values
while holding the other two at their default values.

Runs real simulation for all 5 schedules at each gain combination.
Outputs raw results to stdout.

Defaults (from simulation.py):  KP=0.01, KI=0.001, KD=0.005

Usage (from project root):
    python3 "Digital Twin Own/tests/test_pid_gains_sweep.py"
"""

import sys, os

# Ensure parent package (Digital Twin Own/) is importable
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import simulation
from simulation import run_simulation, total_steam_used

# Defaults
DEFAULT_KP = 0.01
DEFAULT_KI = 0.001
DEFAULT_KD = 0.005

schedules = [
    ('schedule_1_peak_overlap.csv',    'Sched-1'),
    ('schedule_2_staggered_15m.csv',   'Sched-2'),
    ('schedule_3_staggered_30m.csv',   'Sched-3'),
    ('schedule_4_idle_waste_test.csv', 'Sched-4'),
    ('schedule_5_full_shift_heavy.csv','Sched-5'),
]

SCHEDULES_DIR = os.path.join(BASE_DIR, 'schedules')

SEP = '=' * 135


def run_batch(label, sweep_param, sweep_values, fixed_kp, fixed_ki, fixed_kd):
    print(f'\n{SEP}')
    print(f'  SWEEP: {label}   (other gains fixed)')
    print(f'  Fixed: KP={fixed_kp}, KI={fixed_ki}, KD={fixed_kd}')
    print(SEP)
    print(
        f"  {'Value':>12} | "
        f"{'Sched-1 Comp':>14} {'Steam':>8} {'Peak':>12} | "
        f"{'Sched-2 Comp':>14} {'Steam':>8} {'Peak':>12} | "
        f"{'Sched-3 Comp':>14} {'Steam':>8} {'Peak':>12} | "
        f"{'Sched-4 Comp':>14} {'Steam':>8} {'Peak':>12} | "
        f"{'Sched-5 Comp':>14} {'Steam':>8} {'Peak':>12}"
    )
    print('-' * 135)

    for val in sweep_values:
        # Inject gain values into simulation module
        simulation.KP = fixed_kp
        simulation.KI = fixed_ki
        simulation.KD = fixed_kd
        if sweep_param == 'KP':
            simulation.KP = val
        elif sweep_param == 'KI':
            simulation.KI = val
        elif sweep_param == 'KD':
            simulation.KD = val

        default_marker = '*' if round(val, 6) == round(
            {'KP': DEFAULT_KP, 'KI': DEFAULT_KI, 'KD': DEFAULT_KD}[sweep_param], 6
        ) else ' '

        row = f"  {default_marker}{val:.5f}     |"
        for filename, label_s in schedules:
            filepath = os.path.join(SCHEDULES_DIR, filename)
            log, comp_s = run_simulation(filepath, mode='smart')
            p_ids = log[-1].get('press_ids', [1, 2, 3])
            steam = total_steam_used(log, p_ids)
            peak  = max(r['total_steam_flow_kg_s'] for r in log)
            hrs   = comp_s / 3600.0
            mins  = comp_s / 60.0
            row  += f" {hrs:.3f}h({mins:.0f}m) {steam:.2f}kg {peak:.5f}  |"
        print(row)

    # Restore defaults
    simulation.KP = DEFAULT_KP
    simulation.KI = DEFAULT_KI
    simulation.KD = DEFAULT_KD
    print(f'  * = Default value')


# ── Kp sweep: 0.001 to 0.040 in steps of 0.001 ─────────────────────────────
kp_values = [round(i * 0.001, 4) for i in range(1, 41)]

# ── Ki sweep: 0.0001 to 0.0040 in steps of 0.0001 ───────────────────────────
ki_values = [round(i * 0.0001, 5) for i in range(1, 41)]

# ── Kd sweep: 0.001 to 0.040 in steps of 0.001 ──────────────────────────────
kd_values = [round(i * 0.001, 4) for i in range(1, 41)]


if __name__ == '__main__':
    run_batch(
        label='Kp  (0.001 to 0.040, step 0.001)',
        sweep_param='KP',
        sweep_values=kp_values,
        fixed_kp=DEFAULT_KP,
        fixed_ki=DEFAULT_KI,
        fixed_kd=DEFAULT_KD,
    )

    run_batch(
        label='Ki  (0.0001 to 0.0040, step 0.0001)',
        sweep_param='KI',
        sweep_values=ki_values,
        fixed_kp=DEFAULT_KP,
        fixed_ki=DEFAULT_KI,
        fixed_kd=DEFAULT_KD,
    )

    run_batch(
        label='Kd  (0.001 to 0.040, step 0.001)',
        sweep_param='KD',
        sweep_values=kd_values,
        fixed_kp=DEFAULT_KP,
        fixed_ki=DEFAULT_KI,
        fixed_kd=DEFAULT_KD,
    )

    print(f'\n{SEP}')
    print('  Done.')
    print(SEP)
