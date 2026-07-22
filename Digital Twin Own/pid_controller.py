"""
pid_controller.py

PID controller for one curing press.
Input: temperature error (target - current).
Output: raw valve opening percentage (0.0 to 1.0), before
        schedule or steam budget adjust it.
Includes Anti-Windup Clamping on the integral accumulator.
"""


class PIDController:
    def __init__(self, kp, ki, kd):
        # Gains: how strongly each term reacts
        self.kp = kp
        self.ki = ki
        self.kd = kd

        # Memory needed between time steps
        self.integral = 0.0        # accumulated error over time
        self.previous_error = 0.0  # error from the last time step, for D term

    def compute(self, target_temp, current_temp, dt_seconds):
        """
        Called once per time step, per press.
        Returns a valve opening percentage between 0.0 and 1.0.
        """
        error = target_temp - current_temp

        # P term: react to how big the gap is right now
        p_term = self.kp * error

        # I term with Anti-Windup Clamping: prevent infinite integral accumulation during long ramps
        self.integral += error * dt_seconds
        
        # Clamp integral accumulator to prevent windup overshoot
        if self.ki > 0:
            max_integral = 1.0 / self.ki
            self.integral = max(-max_integral, min(max_integral, self.integral))

        i_term = self.ki * self.integral

        # D term: react to how fast the error is changing
        error_rate = (error - self.previous_error) / dt_seconds if dt_seconds > 0 else 0.0
        d_term = self.kd * error_rate

        # Save this error for next time step's D calculation
        self.previous_error = error

        # Combine all three
        raw_output = p_term + i_term + d_term

        # Clamp to a valid valve range [0.0, 1.0]
        valve_open_percent = max(0.0, min(1.0, raw_output))
        return valve_open_percent

    def freeze_integral(self):
        """Stops the integral term from building up while idle."""
        pass

    def reset_integral(self):
        """Resets integral accumulator for new cure cycles."""
        self.integral = 0.0
        self.previous_error = 0.0