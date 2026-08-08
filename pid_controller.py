class PIDController:

    def __init__(self, kp, ki, kd, output_limits=(0.0, 100.0), feedforward=26.25):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.feedforward = feedforward
        self.min_output, self.max_output = output_limits

        self.integral = 0.0
        self.previous_error = None


    def reset(self):
        self.integral = 0.0
        self.previous_error = None


    def compute(self, setpoint, measurement, dt):
        error = setpoint - measurement

        # Handle first step derivative without initial spike
        if self.previous_error is None:
            derivative = 0.0
        else:
            derivative = (error - self.previous_error) / dt

        p_term = self.kp * error
        d_term = self.kd * derivative

        # Anti-windup (conditional integration)
        tentative_integral = self.integral + error * dt
        tentative_output = self.feedforward + p_term + self.ki * tentative_integral + d_term

        if self.min_output <= tentative_output <= self.max_output:
            self.integral = tentative_integral

        output = self.feedforward + p_term + self.ki * self.integral + d_term

        # Clamp output
        clamped_output = max(self.min_output, min(self.max_output, output))

        self.previous_error = error

        return clamped_output