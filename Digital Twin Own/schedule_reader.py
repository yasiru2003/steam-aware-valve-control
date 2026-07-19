"""
Schedule Reader Module for Parsing CSV/JSON Production Schedules.
"""

import pandas as pd
import numpy as np


def load_schedule_from_csv(filepath_or_buffer, hours: float = 12.0, dt: float = 5.0):
    """
    Parses a production schedule CSV and generates time-step active arrays per press.
    
    CSV Columns expected:
    - press_id: Name/ID of press (e.g. Press_1, Press_2)
    - start_hour: Hour when job starts heating
    - cure_duration_hours: Curing hold duration
    - idle_gap_start_hour: Hour when planned idle gap starts
    - idle_gap_duration_hours: Duration of idle gap
    """
    df = pd.read_csv(filepath_or_buffer)
    n_steps = int(hours * 3600 / dt)
    times = np.arange(n_steps) * dt
    
    schedules = {}
    
    for idx, row in df.iterrows():
        press_id = str(row["press_id"]).strip()
        start_s = float(row["start_hour"]) * 3600.0
        gap_start_s = float(row["idle_gap_start_hour"]) * 3600.0
        gap_dur_s = float(row["idle_gap_duration_hours"]) * 3600.0
        
        active_mask = np.zeros(n_steps, dtype=bool)
        
        # Active from start_s until gap_start_s, and resumed after gap_start_s + gap_dur_s
        start_idx = max(0, min(int(start_s / dt), n_steps))
        gap_start_idx = max(0, min(int(gap_start_s / dt), n_steps))
        gap_end_idx = max(0, min(int((gap_start_s + gap_dur_s) / dt), n_steps))
        
        active_mask[start_idx:gap_start_idx] = True
        active_mask[gap_end_idx:] = True
        
        schedules[press_id] = active_mask
        
    return times, schedules, df
