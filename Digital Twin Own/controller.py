"""
controller.py

Supervisory Controller for Multiple Curing Presses.
Implements Priority-Based Sequential Staggering with Escalation Safeguard:
- Ranks presses currently in HEATING stage (< 129.5°C) by temperature.
- Escalation Safeguard: If a secondary press is throttled at floor for >= 15 mins (ESCALATION_SECONDS),
  it is force-promoted to top priority (u=1.0) to prevent starvation.
- Escalated Secondary Priority: Escalated secondary presses get FIRST claim on leftover secondary budget
  before splitting any remaining budget among non-escalated secondary presses.
- Holds presses already at target setpoint (>= 129.5°C) at minimal holding demand/floor.
"""

STEAM_BUDGET = 1.8           # optimal shared steam budget in press equivalents
FLOOR_PERCENT = 0.25         # minimum floor share when pre-heating
ESCALATION_SECONDS = 15 * 60  # 15 minutes escalation safeguard


class ControllerNode:
    def __init__(self, press_ids, steam_budget: float = 1.8):
        self.press_ids = press_ids
        self.steam_budget = float(steam_budget)
        self.time_at_floor = {press_id: 0.0 for press_id in press_ids}
        self.escalated = {press_id: False for press_id in press_ids}
        self.sim_time = 0.0

    def resolve(self, pid_demands, curing_status, dt_seconds, press_temperatures=None):
        """
        pid_demands        : dict {press_id: raw_valve_demand}
        curing_status      : dict {press_id: True/False}
        dt_seconds         : time step size in seconds
        press_temperatures : dict {press_id: temp_C}
        """
        demands = {}
        for press_id, demand in pid_demands.items():
            if curing_status.get(press_id, False):
                demands[press_id] = demand
            else:
                demands[press_id] = 0.0
                self.time_at_floor[press_id] = 0.0
                self.escalated[press_id] = False

        active_ids = [pid for pid in demands if demands[pid] > 0.0]
        total_demand = sum(demands[pid] for pid in active_ids)
        budget = self.steam_budget

        # If total demand fits within budget, grant requested signals directly
        if total_demand <= budget or not active_ids:
            for press_id in active_ids:
                self.time_at_floor[press_id] = 0.0
                self.escalated[press_id] = False
            return dict(demands)

        # Separate presses into 'heating' (< 129.5°C) and 'holding' (>= 129.5°C)
        temps = press_temperatures if press_temperatures else {}
        heating_ids = [pid for pid in active_ids if temps.get(pid, 0.0) < 129.5]
        holding_ids = [pid for pid in active_ids if temps.get(pid, 0.0) >= 129.5]

        final = {}
        # Holding presses take their minimal holding demand / floor allocation
        holding_budget_used = 0.0
        for pid in holding_ids:
            allocated = min(demands[pid], FLOOR_PERCENT)
            final[pid] = allocated
            holding_budget_used += allocated
            self.time_at_floor[pid] = 0.0
            self.escalated[pid] = False

        remaining_budget = max(0.0, budget - holding_budget_used)

        if heating_ids:
            # Separate escalated and non-escalated heating presses
            escalated_heating = [pid for pid in heating_ids if self.escalated[pid]]
            non_escalated_heating = [pid for pid in heating_ids if not self.escalated[pid]]

            # Rank BOTH queues by temperature descending so closest to setpoint finishes first
            escalated_heating.sort(key=lambda pid: temps.get(pid, 0.0), reverse=True)
            non_escalated_heating.sort(key=lambda pid: temps.get(pid, 0.0), reverse=True)

            # Promoted order: Escalated queue first, then non-escalated queue
            ordered_heating_ids = escalated_heating + non_escalated_heating

            top_heating_pid = ordered_heating_ids[0]
            final[top_heating_pid] = min(demands[top_heating_pid], remaining_budget, 1.0)
            self.time_at_floor[top_heating_pid] = 0.0

            rem_for_secondaries = max(0.0, remaining_budget - final[top_heating_pid])
            secondary_heating_ids = ordered_heating_ids[1:]

            if secondary_heating_ids:
                esc_secondaries = [pid for pid in secondary_heating_ids if self.escalated[pid]]
                non_esc_secondaries = [pid for pid in secondary_heating_ids if not self.escalated[pid]]

                # Step 1: Escalated secondary presses get FIRST CLAIM on leftover secondary budget
                if esc_secondaries:
                    esc_share = rem_for_secondaries / len(esc_secondaries)
                    for pid in esc_secondaries:
                        allocated = max(FLOOR_PERCENT * demands[pid], min(demands[pid], esc_share))
                        final[pid] = allocated
                        self.time_at_floor[pid] += dt_seconds

                    used_by_esc = sum(final[pid] for pid in esc_secondaries)
                    rem_for_secondaries = max(0.0, rem_for_secondaries - used_by_esc)

                # Step 2: Non-escalated secondary presses split whatever budget is left (or floor allocation)
                if non_esc_secondaries:
                    non_esc_share = rem_for_secondaries / len(non_esc_secondaries) if rem_for_secondaries > 0 else 0.0
                    for pid in non_esc_secondaries:
                        allocated = max(FLOOR_PERCENT * demands[pid], min(demands[pid], non_esc_share))
                        final[pid] = allocated

                        if allocated < demands[pid]:
                            self.time_at_floor[pid] += dt_seconds
                            if self.time_at_floor[pid] >= ESCALATION_SECONDS:
                                self.escalated[pid] = True
                        else:
                            self.time_at_floor[pid] = 0.0
                            self.escalated[pid] = False

        self.sim_time += dt_seconds

        # Fill 0.0 for inactive presses
        for pid in pid_demands:
            if pid not in final:
                final[pid] = 0.0

        return final