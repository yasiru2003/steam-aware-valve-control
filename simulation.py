import time
from datetime import datetime, timedelta

from controller import ControllerNode
from schedule_fetcher import get_all_press_schedules


class TemperatureSimulation:

    def __init__(self):
        self.temperature = 25.0
        self.ambient_temperature = 25.0


    def get_temperature(self):
        return self.temperature


    def set_valve(self, valve_position, dt):

        # Heating from valve
        heating_rate = valve_position * 0.02

        # Natural cooling
        cooling = (
            self.temperature -
            self.ambient_temperature
        ) * 0.005

        self.temperature += (
            heating_rate - cooling
        ) * dt



class SimulationClock:

    def __init__(self):

        # Simulation starts early at 06:00 to observe dynamic pre-heating
        self.current_time = datetime.strptime(
            "06:00",
            "%H:%M"
        )


    def update(self):

        # 1 step = 1 simulation minute
        self.current_time += timedelta(minutes=1)


    def get_time(self):

        return self.current_time


TARGET_CURING_TEMP = 130.0
STANDBY_TEMP = 100.0
AMBIENT_TEMP = 25.0
MAX_STANDBY_MINUTES = 60


def calculate_preheat_duration(start_temp, target_temp=TARGET_CURING_TEMP, ambient_temp=AMBIENT_TEMP):
    """
    Calculates exact required preheat duration in minutes
    based on current room/sensor temperature and thermal model.
    """
    temp = start_temp
    minutes = 0
    dt = 1.0
    while temp < target_temp - 0.5:
        heating_rate = 100.0 * 0.02
        cooling = (temp - ambient_temp) * 0.005
        temp += (heating_rate - cooling) * dt
        minutes += 1
        if minutes > 300:
            break
    return minutes


def calculate_hold_threshold(target_temp, ambient_temp, heating_coeff=0.02, cooling_coeff=0.005):
    """
    Calculates the dynamic break-even idle gap duration (in minutes).
    Replaces the fixed 60-minute cutoff with a cost-based decision:
    - hold_cost: Steam spent keeping the press near cure temperature for the whole gap.
    - shut_cost: Extra reheat energy needed because the press cooled down during the gap.
    
    If gap < threshold, holding warm (STANDBY) is cheaper.
    If gap >= threshold, shutting off completely (COOLING) is cheaper.
    """
    import math
    q_loss = (target_temp - ambient_temp) * cooling_coeff / heating_coeff
    tau = 1.0 / cooling_coeff
    C_thermal = 1.0 / heating_coeff
    
    for g in range(1, 1440):
        hold_cost = q_loss * g
        T_g = ambient_temp + (target_temp - ambient_temp) * math.exp(-g / tau)
        
        # We use a realistic shut cost that incorporates the heat loss during reheating
        # to ensure a physically sensible crossover point.
        needed_reheat = calculate_preheat_duration(T_g, target_temp, ambient_temp)
        shut_cost = 100.0 * needed_reheat
        
        if hold_cost > shut_cost:
            return float(g)
            
    return 1440.0


controller_node = ControllerNode()
temperature_sim = TemperatureSimulation()
clock = SimulationClock()

dt = 1.0

# Fetch multi-tyre schedules for P001 from schedule.csv
cycles = get_all_press_schedules("schedules/schedule.csv", "P001")
if not cycles:
    cycles = [{
        "tyre_id": "P001_T1",
        "start_in": datetime.strptime("08:00", "%H:%M").time(),
        "start_out": datetime.strptime("15:00", "%H:%M").time()
    }]

print(f"--- Multi-Tyre Curing Schedule for P001 ---")
for c in cycles:
    print(f" - Tyre: {c['tyre_id']} | Start In: {c['start_in'].strftime('%H:%M')} | Start Out: {c['start_out'].strftime('%H:%M')} (7 Hours)")

# Calculate initial cold preheat start time for first tyre cycle
first_start_in = cycles[0]["start_in"]
initial_room_temp = temperature_sim.get_temperature()
needed_preheat_minutes = calculate_preheat_duration(
    initial_room_temp,
    target_temp=TARGET_CURING_TEMP,
    ambient_temp=temperature_sim.ambient_temperature
)

today_date = datetime.today()
start_in_dt = datetime.combine(today_date, first_start_in)
preheat_start_dt = start_in_dt - timedelta(minutes=needed_preheat_minutes)
preheat_start_time = preheat_start_dt.time()

print(f"\nInitial Room Temp: {initial_room_temp:.1f} °C -> Cold Preheat Time: {needed_preheat_minutes} mins")
print(f"Smart Cold Preheat Start Time: {preheat_start_time.strftime('%H:%M')}\n")

# Simulation duration limits to prevent midnight rollover infinite loop
max_simulation_minutes = 24 * 60  # 24 Hours max (06:00 Day 1 to 06:00 Day 2)
elapsed_minutes = 0

while elapsed_minutes < max_simulation_minutes:

    # Current simulation time
    current_time = clock.get_time()
    cur_time_of_day = current_time.time()

    # Determine mode & active tyre for multi-tyre schedule
    active_mode = "IDLE"
    active_tyre = "N/A"
    setpoint_temp = TARGET_CURING_TEMP
    last_cycle_end = cycles[-1]["start_out"]

    if cur_time_of_day < preheat_start_time and elapsed_minutes < 600:
        active_mode = "IDLE"
        active_tyre = "N/A"
    elif preheat_start_time <= cur_time_of_day < first_start_in and elapsed_minutes < 600:
        active_mode = "PREHEAT"
        active_tyre = cycles[0]["tyre_id"]
        setpoint_temp = TARGET_CURING_TEMP
    elif elapsed_minutes >= 990 or (cur_time_of_day >= last_cycle_end and elapsed_minutes > 500):
        # After last cycle end (22:30): transition to COOLING until temp reaches room temp
        if temperature_sim.get_temperature() > temperature_sim.ambient_temperature + 1.0:
            active_mode = "COOLING"
        else:
            active_mode = "IDLE"
        active_tyre = "N/A"
    else:
        # Shift production window (between first start and last end)
        in_curing_cycle = False
        for c in cycles:
            if c["start_in"] <= cur_time_of_day < c["start_out"]:
                active_mode = "CURING"
                active_tyre = c["tyre_id"]
                setpoint_temp = TARGET_CURING_TEMP
                in_curing_cycle = True
                break
        if not in_curing_cycle:
            # Evaluate inter-cycle gap for Option 1 dynamic standby decision
            for i in range(len(cycles) - 1):
                prev_out = cycles[i]["start_out"]
                next_in = cycles[i + 1]["start_in"]
                next_tyre = cycles[i + 1]["tyre_id"]

                if prev_out <= cur_time_of_day < next_in:
                    dummy_date = datetime.today().date()
                    gap_mins = (
                        datetime.combine(dummy_date, next_in) -
                        datetime.combine(dummy_date, prev_out)
                    ).total_seconds() / 60.0

                    dynamic_hold_threshold = calculate_hold_threshold(
                        TARGET_CURING_TEMP, 
                        temperature_sim.ambient_temperature
                    )

                    if gap_mins <= dynamic_hold_threshold:
                        current_temp = temperature_sim.get_temperature()
                        needed_reheat_mins = calculate_preheat_duration(
                            current_temp,
                            target_temp=TARGET_CURING_TEMP,
                            ambient_temp=temperature_sim.ambient_temperature
                        )
                        dt_next_in = datetime.combine(dummy_date, next_in)
                        dt_cur_time = datetime.combine(dummy_date, cur_time_of_day)
                        time_remaining_mins = (dt_next_in - dt_cur_time).total_seconds() / 60.0

                        if time_remaining_mins > needed_reheat_mins:
                            # Dynamic Standby Phase: Maintain reduced standby temperature
                            active_mode = "STANDBY"
                            active_tyre = "CHANGE_OVER"
                            setpoint_temp = STANDBY_TEMP
                        else:
                            # Smart Preheat Phase: 100% valve dynamically triggered to hit target right on time
                            active_mode = "PREHEAT"
                            active_tyre = next_tyre
                            setpoint_temp = TARGET_CURING_TEMP
                    else:
                        # Long interval -> Cool down (valve 0.0%)
                        active_mode = "COOLING"
                        active_tyre = "INTER_CYCLE"
                    break


    # Controller calculates valve %
    valve = controller_node.update(
        temperature_sim.get_temperature(),
        dt,
        active_mode,
        setpoint=setpoint_temp
    )

    # Apply valve effect
    temperature_sim.set_valve(valve, dt)

    # Print log
    tyre_str = f"[{active_tyre}]" if active_tyre != "N/A" else "      "
    print(
        f"Time: {current_time.strftime('%H:%M')} | "
        f"Temp: {temperature_sim.get_temperature():.2f} °C | "
        f"Valve: {valve:6.2f}% | "
        f"Mode: {active_mode:7s} {tyre_str}"
    )

    # Move simulation clock
    clock.update()
    elapsed_minutes += 1

    # Pause between steps
    time.sleep(0.005)

    # Stop condition: after last cycle (22:30) when press has cooled down to room temp
    if elapsed_minutes > 990 and temperature_sim.get_temperature() <= temperature_sim.ambient_temperature + 1.0:
        print("\nMulti-Tyre Curing Simulation complete. Press has cooled to room temperature.")
        break