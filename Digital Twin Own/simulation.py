"""
simulation.py

Runs the full multi-press curing simulation, tracking each press's
REAL physical completion time (when its hold timer actually satisfies
the required cure duration at 130°C), not just when the schedule's
clock runs out.

Compares Human Operator Control (Ordinary Unmanaged Baseline) vs
Smart Supervisory Control.

Brief Specification for Idle & Peak Behavior:
- Human Operator Control: PID control during curing; valve left 15%
  cracked open (u = 0.15) during idle breaks.
- Smart Supervisory Control: ControllerNode budget capping (1.8 press
  eq) + valve auto-closed to 0% (u = 0.00) during idle breaks.
"""

import os
from press_model import CuringPress, TARGET_TEMP
from pid_controller import PIDController
from schedule_reader import load_schedule, is_curing
from controller import ControllerNode, STEAM_BUDGET

# Simulation settings
DT_SECONDS = 10                    # size of one time step
HUMAN_IDLE_VALVE_OPENING = 0.15    # 15% cracked open valve leak in human operator control
SAFETY_MARGIN_S = 2 * 3600         # extra 2 hours of safety margin beyond schedule end

KP = 0.01
KI = 0.001
KD = 0.005

SCHEDULES_DIR = os.path.join(os.path.dirname(__file__), "schedules")
DEFAULT_SCHEDULE_FILE = os.path.join(SCHEDULES_DIR, "schedule_1_peak_overlap.csv")


def run_simulation(schedule_filepath=None, mode="smart"):
    """
    mode : "human" (or "naive") vs "smart"

    Runs until every press has REALLY finished its physical cure hold
    (hold_elapsed >= cure_time_s), using the schedule's own end time
    only as a safety upper bound, not as the actual completion metric.
    """
    if schedule_filepath is None:
        schedule_filepath = DEFAULT_SCHEDULE_FILE

    schedule_entries = load_schedule(schedule_filepath)

    # Dynamically extract press_ids from CSV entries
    press_ids = []
    for e in schedule_entries:
        p_str = str(e["press_id"]).replace("Press_", "").strip()
        try:
            pid = int(p_str)
            if pid not in press_ids:
                press_ids.append(pid)
        except ValueError:
            pass
    if not press_ids:
        press_ids = [1, 2, 3]
    press_ids.sort()

    presses = {pid: CuringPress(pid) for pid in press_ids}
    pids = {pid: PIDController(KP, KI, KD) for pid in press_ids}
    controller_node = ControllerNode(press_ids, steam_budget=STEAM_BUDGET)

    # --- Safety upper bound only, NOT the completion metric ---
    max_schedule_end_s = 0.0
    for e in schedule_entries:
        start_s = e["start_s"]
        cure_dur_s = e.get("cure_dur_s", 23400.0)
        gap_start_s = e.get("gap_start_s", 999999.0)
        gap_dur_s = e.get("gap_dur_s", 0.0)

        if gap_dur_s > 0 and gap_start_s < 999999.0:
            end_s = gap_start_s + gap_dur_s + cure_dur_s   # multi-batch
        else:
            end_s = start_s + cure_dur_s                   # single-batch

        if end_s > max_schedule_end_s:
            max_schedule_end_s = end_s

    safety_cutoff_s = max_schedule_end_s + SAFETY_MARGIN_S

    # --- Real physical completion tracking, per press ---
    completion_time_s = {pid: None for pid in press_ids}

    log = []
    current_time = 0.0

    while current_time <= safety_cutoff_s:
        curing_status = {
            pid: is_curing(pid, current_time, schedule_entries)
            for pid in press_ids
        }

        raw_demands = {
            pid: pids[pid].compute(TARGET_TEMP, presses[pid].temperature, DT_SECONDS)
            for pid in press_ids
        }

        press_temps = {pid: presses[pid].temperature for pid in press_ids}

        if mode == "smart":
            final_valves = controller_node.resolve(raw_demands, curing_status, DT_SECONDS, press_temps)
        else:
            final_valves = {
                pid: (raw_demands[pid] if curing_status[pid] else HUMAN_IDLE_VALVE_OPENING)
                for pid in press_ids
            }

        step_entry = {"time_seconds": current_time, "time_hours": current_time / 3600.0, "press_ids": press_ids}
        total_flow = 0.0

        for pid in press_ids:
            presses[pid].update(final_valves[pid], curing_status[pid], DT_SECONDS)
            state = presses[pid].get_state()
            total_flow += state["steam_flow_kg_s"]

            for key, value in state.items():
                step_entry[f"press{pid}_{key}"] = value

            # Record the REAL moment this press finishes its physical cure hold
            if completion_time_s[pid] is None and presses[pid].hold_elapsed >= presses[pid].params["cure_time_s"]:
                completion_time_s[pid] = current_time

        step_entry["total_steam_flow_kg_s"] = total_flow
        log.append(step_entry)

        # Stop early once every press has genuinely finished, no need to keep simulating
        if all(t is not None for t in completion_time_s.values()):
            break

        current_time += DT_SECONDS

    # If a press never finished within the safety window, mark it with the cutoff time
    # (so the number is visibly capped rather than silently missing)
    for pid in press_ids:
        if completion_time_s[pid] is None:
            completion_time_s[pid] = safety_cutoff_s

    real_completion_s = max(completion_time_s.values())

    return log, real_completion_s


def total_steam_used(log, press_ids=None):
    """Calculates total steam used from final log entry."""
    if not log:
        return 0.0
    last_entry = log[-1]
    if press_ids is None:
        press_ids = last_entry.get("press_ids", [1, 2, 3])
    return sum(
        last_entry.get(f"press{pid}_total_steam_used_kg", 0.0)
        for pid in press_ids
    )


if __name__ == "__main__":
    schedule_files = [
        ("schedule_1_peak_overlap.csv", "🔥 Schedule 1: Heavy Overlap Peak Test (0m, 0m, 0m)"),
        ("schedule_2_staggered_15m.csv", "⏱️ Schedule 2: 15-Min Staggered Schedule (0m, 15m, 30m)"),
        ("schedule_3_staggered_30m.csv", "📅 Schedule 3: 30-Min Staggered Schedule (0m, 30m, 60m)"),
        ("schedule_4_idle_waste_test.csv", "💤 Schedule 4: Long Idle Break Test (3.0h Idle Gap)"),
        ("schedule_5_full_shift_heavy.csv", "🏭 Schedule 5: 4-Press Heavy Double Shift (4 Presses)"),
    ]

    print("========================================================================")
    print("  HUMAN OPERATOR VS SMART SUPERVISORY CONTROL COMPARISON RESULTS       ")
    print("  (Physical Completion = real hold-timer completion, not schedule clock) ")
    print("========================================================================")

    for filename, title in schedule_files:
        filepath = os.path.join(SCHEDULES_DIR, filename)
        human_log, human_completion_s = run_simulation(filepath, mode="human")
        smart_log, smart_completion_s = run_simulation(filepath, mode="smart")

        p_ids = human_log[-1].get("press_ids", [1, 2, 3])
        human_steam = total_steam_used(human_log, p_ids)
        smart_steam = total_steam_used(smart_log, p_ids)

        human_time = human_completion_s / 3600.0
        smart_time = smart_completion_s / 3600.0
        delay_mins = (smart_time - human_time) * 60.0

        human_peak = max(row["total_steam_flow_kg_s"] for row in human_log)
        smart_peak = max(row["total_steam_flow_kg_s"] for row in smart_log)
        peak_red_pct = ((human_peak - smart_peak) / human_peak) * 100.0 if human_peak > 0 else 0.0
        steam_saved_kg = human_steam - smart_steam
        steam_saved_pct = (steam_saved_kg / human_steam) * 100.0 if human_steam > 0 else 0.0

        print(f"\n{title} ({filename}) [Presses: {len(p_ids)}]")
        print(f"   Human Operator Control : Physical Completion = {human_time:.3f} hrs ({human_time*60:.1f}m) | Steam = {human_steam:.3f} kg | Peak Flow = {human_peak:.5f} kg/s")
        print(f"   Smart Supervisory Control: Physical Completion = {smart_time:.3f} hrs ({smart_time*60:.1f}m) | Steam = {smart_steam:.3f} kg | Peak Flow = {smart_peak:.5f} kg/s")
        print(f"   Empirical Difference     : Steam Saved = {steam_saved_kg:+.3f} kg ({steam_saved_pct:+.1f}%) | Time Delay = {delay_mins:+.1f} mins | Peak Red = {peak_red_pct:+.1f}%")