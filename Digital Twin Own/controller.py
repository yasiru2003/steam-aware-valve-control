"""
Control algorithms for steam valve control (PID Controller).
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
