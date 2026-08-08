import math
import pandas as pd
from datetime import datetime, timedelta

from pid_controller import PIDController
from disturbance import ThermalDisturbance
from schedule_fetcher import get_all_press_schedules


class PlantSimulation:
    def __init__(self, initial_temp, ambient_temp, heat_coeff, cool_coeff):
        self.temperature = initial_temp
        self.ambient_temperature = ambient_temp
        self.heat_coeff = heat_coeff
        self.cool_coeff = cool_coeff

    def update(self, valve_position, disturbance_delta=0.0, dt=1.0):
        heating_rate = valve_position * self.heat_coeff
        cooling_rate = (self.temperature - self.ambient_temperature) * self.cool_coeff
        self.temperature += (heating_rate - cooling_rate + disturbance_delta) * dt
        return self.temperature


def calculate_preheat_minutes(start_temp, target_temp, ambient_temp, heat_coeff, cool_coeff):
    temp = start_temp
    minutes = 0
    dt = 1.0
    while temp < target_temp - 0.5 and minutes < 300:
        h_rate = 100.0 * heat_coeff
        c_rate = (temp - ambient_temp) * cool_coeff
        temp += (h_rate - c_rate) * dt
        minutes += 1
    return minutes


def calculate_hold_threshold(target_temp, ambient_temp, heating_coeff, cooling_coeff):
    q_loss = (target_temp - ambient_temp) * cooling_coeff / heating_coeff
    tau = 1.0 / cooling_coeff
    
    for g in range(1, 1440):
        hold_cost = q_loss * g
        T_g = ambient_temp + (target_temp - ambient_temp) * math.exp(-g / tau)
        
        needed_reheat = calculate_preheat_minutes(T_g, target_temp, ambient_temp, heating_coeff, cooling_coeff)
        shut_cost = 100.0 * needed_reheat
        
        if hold_cost > shut_cost:
            return float(g)
            
    return 1440.0


class PressSimulationState:
    def __init__(self, press_id, cycles, config):
        self.press_id = press_id
        self.cycles = cycles
        self.config = config
        
        self.target_temperature = config['target_temperature']
        self.ambient_temperature = config['ambient_temperature']
        self.heating_coeff = config['heating_coeff']
        self.cooling_coeff = config['cooling_coeff']
        
        self.plant = PlantSimulation(
            initial_temp=self.ambient_temperature,
            ambient_temp=self.ambient_temperature,
            heat_coeff=self.heating_coeff,
            cool_coeff=self.cooling_coeff
        )
        
        self.pid = PIDController(
            kp=config['kp'],
            ki=config['ki'],
            kd=config['kd'],
            feedforward=(self.target_temperature - self.ambient_temperature) * self.cooling_coeff / self.heating_coeff
        )
        
        self.disturbance_model = ThermalDisturbance(enable_tyre_shock=config['enable_disturbance'])
        self.previous_mode = None
        self.mode = "IDLE"
        self.valve = 0.0
        self.history = []
        
        # Calculate preheat start time
        if self.cycles:
            self.first_start_in = self.cycles[0]["start_in"]
            self.last_cycle_end = self.cycles[-1]["start_out"]
            preheat_minutes = calculate_preheat_minutes(
                self.ambient_temperature, self.target_temperature, self.ambient_temperature, 
                self.heating_coeff, self.cooling_coeff
            )
            
            today_date = datetime.today()
            start_in_dt = datetime.combine(today_date, self.first_start_in)
            self.preheat_start_dt = start_in_dt - timedelta(minutes=preheat_minutes)
        else:
            self.first_start_in = None
            self.last_cycle_end = None
            self.preheat_start_dt = None

    def step(self, current_dt, elapsed_minutes, press_power_on, dt_step_minutes=5.0):
        # Process 'dt_step_minutes' in 1-minute physical increments for integration accuracy
        # but only append 1 history frame at the end of the tick.
        for _ in range(int(dt_step_minutes)):
            cur_time = current_dt.time()
            setpoint = self.target_temperature
            
            if not press_power_on or not self.cycles:
                self.mode = "SHUTDOWN (OFF)"
                setpoint = self.ambient_temperature
                self.valve = 0.0
                self.pid.reset()
            else:
                if cur_time < self.preheat_start_dt.time() and elapsed_minutes < 600:
                    self.mode = "IDLE"
                    setpoint = self.ambient_temperature
                elif self.preheat_start_dt.time() <= cur_time < self.first_start_in and elapsed_minutes < 600:
                    self.mode = "PREHEAT"
                    setpoint = self.target_temperature
                elif elapsed_minutes >= 990 or (cur_time >= self.last_cycle_end and elapsed_minutes > 500):
                    if self.plant.temperature > self.ambient_temperature + 1.0:
                        self.mode = "COOLING"
                    else:
                        self.mode = "IDLE"
                    setpoint = self.ambient_temperature
                else:
                    in_curing_cycle = False
                    for c in self.cycles:
                        if c["start_in"] <= cur_time < c["start_out"]:
                            self.mode = "CURING"
                            setpoint = self.target_temperature
                            in_curing_cycle = True
                            break
                    
                    if not in_curing_cycle:
                        # Inter-cycle gap handling
                        for i in range(len(self.cycles) - 1):
                            prev_out = self.cycles[i]["start_out"]
                            next_in = self.cycles[i + 1]["start_in"]
                            if prev_out <= cur_time < next_in:
                                dummy_date = datetime.today().date()
                                gap_mins = (
                                    datetime.combine(dummy_date, next_in) - 
                                    datetime.combine(dummy_date, prev_out)
                                ).total_seconds() / 60.0
                                
                                dynamic_hold_threshold = calculate_hold_threshold(
                                    self.target_temperature, self.ambient_temperature, 
                                    self.heating_coeff, self.cooling_coeff
                                )
                                
                                if gap_mins <= dynamic_hold_threshold:
                                    needed_reheat = calculate_preheat_minutes(
                                        self.plant.temperature, self.target_temperature, 
                                        self.ambient_temperature, self.heating_coeff, self.cooling_coeff
                                    )
                                    time_rem_mins = (datetime.combine(dummy_date, next_in) - datetime.combine(dummy_date, cur_time)).total_seconds() / 60.0
                                    
                                    if time_rem_mins > needed_reheat:
                                        self.mode = "STANDBY"
                                        setpoint = 100.0  # STANDBY_TEMP
                                    else:
                                        self.mode = "PREHEAT"
                                        setpoint = self.target_temperature
                                else:
                                    self.mode = "COOLING"
                                    setpoint = self.ambient_temperature
                                break

            # Disturbance
            dist_effect = self.disturbance_model.get_disturbance(self.mode, dt=1.0)
            
            # Reset PID on mode transition into CURING
            if self.mode == "CURING" and self.previous_mode != "CURING":
                self.pid.reset()
            self.previous_mode = self.mode
            
            # Determine Valve Output
            if self.mode == "IDLE":
                self.valve = 0.0
                self.pid.reset()
            elif self.mode == "PREHEAT":
                self.valve = 100.0
            elif self.mode in ("CURING", "STANDBY"):
                self.pid.feedforward = (setpoint - self.ambient_temperature) * self.cooling_coeff / self.heating_coeff
                self.valve = self.pid.compute(setpoint, self.plant.temperature, dt=1.0)
            elif self.mode == "COOLING":
                self.valve = 0.0
                self.pid.reset()
                
            self.valve = max(0.0, min(100.0, self.valve))
            
            # Update physics
            self.plant.update(self.valve, disturbance_delta=dist_effect if press_power_on else 0.0, dt=1.0)
            
            current_dt += timedelta(minutes=1)
            elapsed_minutes += 1

        self.history.append({
            "DateTime": current_dt,
            "Timestamp": current_dt.strftime("%H:%M"),
            "TimeMinutes": elapsed_minutes,
            "Temperature": self.plant.temperature,
            "Target": setpoint,
            "Valve": self.valve,
            "Mode": self.mode
        })
        return current_dt, elapsed_minutes
