from pid_controller import PIDController


TARGET_TEMPERATURE = 130.0
STANDBY_TEMPERATURE = 100.0


class ControllerNode:

    def __init__(self):

        self.pid = PIDController(
            kp=0.8,
            ki=0.01,
            kd=0.2,
            feedforward=26.25
        )
        self.previous_mode = None


    def update(self, current_temperature, dt, mode, setpoint=TARGET_TEMPERATURE):

        # Reset PID state when entering active control mode
        if (mode in ("CURING", "STANDBY", "CHANGE_OVER")) and (self.previous_mode not in ("CURING", "STANDBY", "CHANGE_OVER")):
            self.pid.reset()

        self.previous_mode = mode

        if mode == "PREHEAT":

            # Full 100% heating valve during preheat ramp-up
            valve = 100.0

        elif mode in ("CURING", "STANDBY", "CHANGE_OVER"):

            # -----------------------------------------------------------------
            # FEEDFORWARD DERIVATION (Why 26.25% at 130 °C?):
            # 1. Natural Heat Loss Rate = (setpoint - room_temp) * 0.005
            #    At 130 °C in 25 °C room = (130 - 25) * 0.005 = 0.525 °C/min
            # 2. Heating Rate = valve_position * 0.02 °C/min
            # 3. At Steady-State Equilibrium: Heating Rate = Heat Loss Rate
            #    valve_position * 0.02 = 0.525
            #    valve_position = 0.525 / 0.02 = 26.25%
            # -----------------------------------------------------------------
            self.pid.feedforward = (setpoint - 25.0) * 0.005 / 0.02

            valve = self.pid.compute(
                setpoint,
                current_temperature,
                dt
            )

            # -----------------------------------------------------------------
            # ALTERNATIVE STRATEGY A: Full Hot Standby (Always Hold 180 °C)
            # To force full hot standby (zero preheat delay for next tyre),
            # uncomment below:
            #
            # valve = self.pid.compute(TARGET_TEMPERATURE, current_temperature, dt)
            # -----------------------------------------------------------------

        elif mode == "COOLING":

            # -----------------------------------------------------------------
            # ALTERNATIVE STRATEGY B: Full Cooling Strategy (Valve 0.0%)
            # Heat source turned completely off; natural air cooling active.
            # -----------------------------------------------------------------
            valve = 0.0
            self.pid.reset()

        elif mode == "BREAK":

            valve = 0.0
            self.pid.reset()

        else:

            valve = 0.0
            self.pid.reset()


        # Valve limit
        valve = max(0.0, min(100.0, valve))


        return valve