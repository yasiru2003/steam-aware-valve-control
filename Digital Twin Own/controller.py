"""
Control algorithms for steam valve control (PID Controller & Peak Demand Smoothing).
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
    Multi-Press Peak Demand Controller.
    Staggers and limits simultaneous valve ramp-ups across presses so total boiler steam flow rate
    does not spike above max_allowed_flow_kg_s.
    """
    def __init__(self, max_allowed_flow_kg_s: float = 0.06):
        self.max_allowed_flow_kg_s = max_allowed_flow_kg_s

    def apply_smoothing(self, valve_signals: dict, press_objects: dict, enable_smoothing: bool = True) -> dict:
        """
        Adjusts requested valve opening ratios across all presses if simultaneous demand spikes.
        """
        if not enable_smoothing:
            return valve_signals  # Return raw unmanaged valve signals

        # Calculate estimated total steam flow rate if raw valve signals are used
        total_estimated_flow = 0.0
        heating_press_ids = []

        for p_id, press in press_objects.items():
            u = valve_signals[p_id]
            Q_est = u * press.params["UA_steam"] * max(press.params["T_sat"] - press.T_press, 0.0)
            flow_est = Q_est / press.params["h_fg"]
            total_estimated_flow += flow_est

            if press.stage == "heating" and u > 0.3:
                heating_press_ids.append(p_id)

        # If estimated flow exceeds boiler limit and multiple presses are heating simultaneously
        if total_estimated_flow > self.max_allowed_flow_kg_s and len(heating_press_ids) > 1:
            # Stagger heating presses: prioritize the press furthest along in heating
            heating_press_ids.sort(key=lambda pid: press_objects[pid].T_press, reverse=True)
            
            # Allow highest temp press full ramp, soften valve opening for secondary heating presses
            smoothed_signals = valve_signals.copy()
            for rank, pid in enumerate(heating_press_ids):
                if rank > 0:
                    # Scale down valve signal for lower priority heating presses to smooth peak
                    smoothed_signals[pid] = min(smoothed_signals[pid], 0.4 / (rank + 1))
            return smoothed_signals

        return valve_signals
