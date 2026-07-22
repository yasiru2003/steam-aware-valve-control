"""
schedule_reader.py

Schedule Reader Module for Parsing CSV Production Schedules.
Pinned & Hand-Verified Version:
- Batch 1 runs continuously from start_s to gap_start_s.
- Planned Idle Gap runs from gap_start_s to gap_end_s (gap_start_s + gap_dur_s).
- Batch 2 runs from gap_end_s to gap_end_s + cure_dur_s.
- Curing stops completely after Batch 2 completion.
"""

import os
import pandas as pd
import numpy as np


def load_schedule(filepath):
    """
    Parses a production schedule CSV and returns a list of schedule entry dicts.
    Handles relative filepaths and searches in the schedules/ directory automatically.
    """
    if not os.path.exists(filepath):
        script_dir = os.path.dirname(__file__)
        candidates = [
            os.path.join(script_dir, "schedules", os.path.basename(filepath)),
            os.path.join(script_dir, filepath),
            os.path.join(script_dir, os.path.basename(filepath)),
        ]
        for cand in candidates:
            if os.path.exists(cand):
                filepath = cand
                break

    df = pd.read_csv(filepath)
    entries = []
    for idx, row in df.iterrows():
        press_id_str = str(row["press_id"]).strip()
        start_s = float(row["start_hour"]) * 3600.0
        cure_dur_s = float(row["cure_duration_hours"]) * 3600.0
        gap_start_s = float(row["idle_gap_start_hour"]) * 3600.0 if "idle_gap_start_hour" in row else 999999.0
        gap_dur_s = float(row["idle_gap_duration_hours"]) * 3600.0 if "idle_gap_duration_hours" in row else 0.0

        entries.append({
            "press_id": press_id_str,
            "start_s": start_s,
            "cure_dur_s": cure_dur_s,
            "gap_start_s": gap_start_s,
            "gap_dur_s": gap_dur_s,
        })
    return entries


def is_curing(press_id, current_time_s: float, schedule_entries: list) -> bool:
    """
    Hand-Verified Curing Schedule Logic:
    1. Batch 1: start_s <= t < gap_start_s
    2. Idle Gap: gap_start_s <= t < gap_end_s -> False
    3. Batch 2: gap_end_s <= t < gap_end_s + cure_dur_s
    4. Post-Batch 2: t >= gap_end_s + cure_dur_s -> False
    """
    p_id_str = str(press_id).strip()
    target_ids = {p_id_str, f"Press_{p_id_str}", p_id_str.replace("Press_", "")}

    for entry in schedule_entries:
        if entry["press_id"] in target_ids:
            start_s = entry["start_s"]
            cure_dur_s = entry.get("cure_dur_s", 23400.0)
            gap_start_s = entry["gap_start_s"]
            gap_dur_s = entry["gap_dur_s"]
            gap_end_s = gap_start_s + gap_dur_s

            # 1. Before schedule start -> Not Curing
            if current_time_s < start_s:
                return False

            # 2. Batch 1 Window: start_s <= current_time_s < gap_start_s
            if start_s <= current_time_s < gap_start_s:
                return True

            # 3. Idle Gap Window: gap_start_s <= current_time_s < gap_end_s -> Not Curing (Idle)
            if gap_start_s <= current_time_s < gap_end_s:
                return False

            # 4. Batch 2 Window (if post-gap exists): gap_end_s <= current_time_s < gap_end_s + cure_dur_s
            if gap_dur_s > 0:
                batch2_end_s = gap_end_s + cure_dur_s
                if gap_end_s <= current_time_s < batch2_end_s:
                    return True
                else:
                    return False
            else:
                batch1_end_s = start_s + cure_dur_s
                if start_s <= current_time_s < batch1_end_s:
                    return True
                else:
                    return False

    return False


def load_schedule_from_csv(filepath_or_buffer, hours: float = 12.0, dt: float = 5.0):
    """
    Legacy helper: parses production schedule and returns time vector, schedule boolean dict, and DataFrame.
    """
    df = pd.read_csv(filepath_or_buffer)
    n_steps = int(hours * 3600 / dt)
    times = np.arange(n_steps) * dt
    entries = load_schedule(filepath_or_buffer)

    schedules = {}
    for entry in entries:
        pid = entry["press_id"]
        mask = np.zeros(n_steps, dtype=bool)
        for i, t in enumerate(times):
            mask[i] = is_curing(pid, t, entries)
        schedules[pid] = mask

    return times, schedules, df
