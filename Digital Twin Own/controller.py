"""
Control algorithms for steam valve control (PID Controller & Budget-Based Priority Throttling).
"""

import numpy as np


class PID:
    """Discrete PID controller with anti-windup clamping [0.0, 1.0]."""
    def __init__(self, kp=0.02, ki=0.00015, kd=0.01, u_min=0.0, u_max=1.0):
        # --- WHY THESE GAIN VALUES WERE CHOSEN ---
        # 1. kp = 0.02 (Proportional Gain):
        #    - At cold start (30°C), temperature error is 100°C (130 - 30).
        #    - Output u = 0.02 * 100 = 2.0 (clamped to 1.0 = 100% open valve for fast heating).
        #    - Near target (128°C), error is 2°C -> u = 0.02 * 2 = 0.04 (4% open valve).
        #
        # 2. ki = 0.00015 (Integral Gain):
        #    - Accumulates error over long time (curing runs for 23,400+ seconds).
        #    - Must be tiny (0.00015) so stored memory doesn't explode and overheat the press.
        #
        # 3. kd = 0.01 (Derivative Gain):
        #    - Measures rate of temperature rise (°C/sec).
        #    - Acts as a brake as press approaches 130°C to prevent overshoot.
        # ----------------------------------------
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.u_min = u_min  # 0.0 = 0% valve open (fully closed)
        self.u_max = u_max  # 1.0 = 100% valve open (fully open)
        self.integral = 0.0
        self.prev_error = None

    def step(self, error: float, dt: float) -> float:
        """Calculates control signal u given error and timestep dt."""
        self.integral += error * dt
        
        if self.prev_error is None:
            derivative = 0.0
        else:
            derivative = (error - self.prev_error) / dt
            
        self.prev_error = error
        
        u_raw = self.kp * error + self.ki * self.integral + self.kd * derivative
        return float(np.clip(u_raw, self.u_min, self.u_max))

    def reset(self):
        """Reset internal memory states."""
        self.integral = 0.0
        self.prev_error = None


class PeakSmoothingController:
    """
    Budget-Based Priority Throttling Controller with Escalation Timer.
    
    Algorithm:
    1. Total system steam budget = total_steam_budget (e.g. 1.5 full-press equivalents).
    2. Rank heating presses by estimated time remaining to setpoint (closest first).
    3. Top ranked press gets 100% steam (1.0).
    4. Leftover budget (total_budget - 1.0 = 0.5) is split equally among remaining heating presses,
       respecting a minimum floor (e.g. 0.25 = 25%).
    5. Floor Breach: If splitting drops below 0.25, lowest priority press is delayed (0.0).
    6. Escalation Timer: If a press has been capped/delayed > 15 mins (900s), force-promote to 100%
       to prevent starvation.
    """
    def __init__(
        self, 
        max_allowed_flow_kg_s: float = 0.06, 
        total_steam_budget: float = 1.5,
        floor_pct: float = 0.25,
        escalation_time_s: float = 15.0 * 60.0
    ):
        self.max_allowed_flow_kg_s = max_allowed_flow_kg_s
        self.total_steam_budget = total_steam_budget
        self.floor_pct = floor_pct
        self.escalation_time_s = escalation_time_s
        
        # Track time spent below full steam per press
        self.time_below_full = {}

    def apply_smoothing(self, valve_signals: dict, press_objects: dict, dt: float = 5.0, enable_smoothing: bool = True) -> dict:
        if not enable_smoothing:
            return valve_signals  # Unmanaged baseline

        # 1. Update escalation timers
        for p_id, u_req in valve_signals.items():
            if p_id not in self.time_below_full:
                self.time_below_full[p_id] = 0.0

            press = press_objects[p_id]
            if press.stage == "heating" and u_req > 0.5:
                # Press wants significant steam but may be throttled
                self.time_below_full[p_id] += dt
            else:
                self.time_below_full[p_id] = 0.0

        # Identify all presses currently in 'heating' stage
        heating_pids = [
            p_id for p_id, press in press_objects.items()
            if press.stage == "heating" and valve_signals[p_id] > 0.1
        ]

        # If 1 or 0 presses heating, no budget conflict
        if len(heating_pids) <= 1:
            return valve_signals

        # Check for escalation force-promotions
        escalated_pids = [
            pid for pid in heating_pids
            if self.time_below_full[pid] >= self.escalation_time_s
        ]

        # 2. Rank heating presses by temperature (closest to setpoint = highest priority)
        heating_pids.sort(key=lambda pid: press_objects[pid].T_press, reverse=True)

        # Move escalated presses to top priority
        for pid in escalated_pids:
            heating_pids.remove(pid)
            heating_pids.insert(0, pid)

        # 3. Budget allocation
        smoothed_signals = valve_signals.copy()
        
        # Top ranked press gets 100% steam (1.0)
        top_pid = heating_pids[0]
        smoothed_signals[top_pid] = min(valve_signals[top_pid], 1.0)

        remaining_budget = max(0.0, self.total_steam_budget - 1.0)
        other_heating = heating_pids[1:]

        if other_heating:
            share = remaining_budget / len(other_heating)

            for rank, pid in enumerate(other_heating):
                if share >= self.floor_pct:
                    # Allocate share respecting floor
                    smoothed_signals[pid] = min(valve_signals[pid], share)
                else:
                    # Floor Breach: If budget share drops below floor (0.25),
                    # allow top remaining to take floor, and delay lower priority presses (0.0)
                    available_slots = int(remaining_budget / self.floor_pct)
                    if rank < available_slots:
                        smoothed_signals[pid] = min(valve_signals[pid], self.floor_pct)
                    else:
                        # Stagger start: delay ramp up until budget frees
                        smoothed_signals[pid] = 0.0

        return smoothed_signals
