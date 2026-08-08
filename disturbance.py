import math
import random


class ThermalDisturbance:
    """
    Models real-world thermal disturbances for an industrial curing press:
    1. Cold Tyre Insertion (Thermal Shock): Front-loaded exponential heat absorption when cold rubber touches hot mold.
    2. Press Door/Mold Opening: Accelerated heat loss during mold opening and tyre extraction.
    3. Ambient Temperature Noise: Small room air fluctuations.
    """

    def __init__(self, enable_tyre_shock=True, enable_door_opening=True, enable_noise=False):
        self.enable_tyre_shock = enable_tyre_shock
        self.enable_door_opening = enable_door_opening
        self.enable_noise = enable_noise

        # Internal state tracking (prevents caller state dependency bugs)
        self.previous_mode = None

        # Tyre shock state (exponential decay profile)
        self.active_shock_mins_remaining = 0.0
        self.shock_elapsed_mins = 0.0
        self.shock_duration_mins = 3.0
        self.shock_total_drop = 8.0

        # Door opening state
        self.door_opening_mins_remaining = 0.0
        self.door_loss_rate = 1.5  # °C/min additional heat loss when mold opens

    def trigger_tyre_shock(self, total_drop=8.0, duration_mins=3.0):
        """
        Triggers a cold tyre insertion shock causing total_drop °C heat loss
        tapering exponentially over duration_mins.
        """
        if self.enable_tyre_shock:
            self.active_shock_mins_remaining = duration_mins
            self.shock_duration_mins = duration_mins
            self.shock_total_drop = total_drop
            self.shock_elapsed_mins = 0.0

    def trigger_door_opening(self, duration_mins=2.0, loss_rate=1.5):
        """
        Triggers press door opening heat loss when mold opens to extract cured tyre.
        """
        if self.enable_door_opening:
            self.door_opening_mins_remaining = duration_mins
            self.door_loss_rate = loss_rate

    def get_disturbance(self, mode, previous_mode=None, dt=1.0):
        """
        Returns temperature adjustment (°C per dt step) to apply to plant physics.
        Negative values represent heat loss/cooling drop.
        """
        # Handle caller passing dt positionally as 2nd argument
        if isinstance(previous_mode, (float, int)):
            dt = float(previous_mode)
            previous_mode = None

        if dt is None or not isinstance(dt, (float, int)):
            dt = 1.0
        net_disturbance_per_min = 0.0

        # Internal state transition detection (robust against caller state bugs)
        if mode == "CURING" and self.previous_mode != "CURING":
            # Cold tyre loaded into hot mold
            self.trigger_tyre_shock(total_drop=8.0, duration_mins=3.0)

        elif mode in ("STANDBY", "CHANGE_OVER") and self.previous_mode == "CURING":
            # Mold opened to extract finished tyre
            self.trigger_door_opening(duration_mins=2.0, loss_rate=1.5)

        self.previous_mode = mode

        # 1. Apply active tyre insertion thermal shock (exponential decay profile)
        if self.active_shock_mins_remaining > 0:
            tau = self.shock_duration_mins / 2.5
            # Exponentially decaying heat absorption rate
            decay_factor = math.exp(-self.shock_elapsed_mins / tau)
            
            # Normalize so integral equals total_drop
            initial_peak_rate = (self.shock_total_drop / tau) / (1.0 - math.exp(-self.shock_duration_mins / tau))
            current_shock_rate = initial_peak_rate * decay_factor

            net_disturbance_per_min -= current_shock_rate

            self.shock_elapsed_mins += dt
            self.active_shock_mins_remaining -= dt

        # 2. Apply active press door opening heat loss
        if self.door_opening_mins_remaining > 0:
            net_disturbance_per_min -= self.door_loss_rate
            self.door_opening_mins_remaining -= dt

        # 3. Apply optional ambient noise
        if self.enable_noise:
            net_disturbance_per_min += random.uniform(-0.05, 0.05)

        # Return net temperature delta for this dt step
        return net_disturbance_per_min * dt
