# Press Temperature Control & Digital Twin Guide

## 1. System Overview

This project simulates a thermal control system for an industrial press. The system reads production schedules from CSV files, dynamically calculates predictive pre-heating times based on ambient room temperature, and uses a PID controller with feedforward compensation to maintain exact curing temperatures.

---

## 2. Architecture & File Structure

```
Project_Updated/
├── schedule_fetcher.py   # Reads and parses press schedules from schedule.csv
├── pid_controller.py     # PID controller with anti-windup and feedforward compensation
├── controller.py         # State machine node and mode management
├── simulation.py         # Thermal physics simulation model and execution loop
└── schedules/
    └── schedule.csv      # Press scheduling data (Start In / Start Out times)
```

### Module Responsibilities

1. **`schedule_fetcher.py`**
   - Loads schedule data from `schedules/schedule.csv` using `pandas`.
   - Helper function `get_press_schedule(file_path, press_no)` returns `(start_in_time, start_out_time)`.

2. **`pid_controller.py`**
   - Implements standard PID control ($K_p = 0.8$, $K_i = 0.01$, $K_d = 0.2$).
   - **Anti-Windup (Conditional Integration)**: Prevents integral saturation during long heating phases.
   - **Feedforward Bias (38.75%)**: Pre-calculates the exact steady-state heat loss valve requirement at 180 °C.
   - **Spike-Free Derivative**: Safely computes derivative terms on initial step.

3. **`controller.py`**
   - Manages mode-specific output (`PREHEAT`, `CURING`, `BREAK`, `IDLE`).
   - Drives 100% valve during `PREHEAT` ramp-up.
   - Smoothly hands over control to the PID controller in `CURING` mode.
   - Resets PID memory when entering active phases.

4. **`simulation.py`**
   - Models thermal plant dynamics (Heating Rate vs Natural Air Cooling).
   - Dynamically predicts preheat start time based on room temperature.
   - Runs a strict state machine (`IDLE` -> `PREHEAT` -> `CURING` -> `IDLE`).

---

## 3. Thermal Physics Model

The plant temperature updates at each 1-minute time step ($dt = 1.0$) according to:

- **Heating Rate**: `valve_position * 0.02` °C per minute
- **Cooling Rate**: `(current_temperature - ambient_temperature) * 0.005` °C per minute
- **Net Change**: `temperature += (heating_rate - cooling_rate) * dt`

### Steady-State Heat Loss Balance
At target curing temperature (130 °C) and room temperature (25 °C):
- Cooling Rate = `(130 - 25) * 0.005 = 0.525` °C per minute
- Required Valve Position = `0.525 / 0.02 = 26.25%`

This 26.25% baseline feedforward ensures zero lag, zero oscillation, and zero overshoot when transitioning into curing mode.

---

## 4. Predictive Pre-Heating Logic

Instead of starting pre-heat at an arbitrary fixed time or starting curing cold, the system dynamically calculates required pre-heating minutes based on current room temperature.

### Formula & Calculation Step

1. **Calculate Needed Temperature Rise**:
   `temp_gap = target_temperature - current_room_temperature`

2. **Average Net Heating Rate**:
   At 100% valve opening, net heating rate is approximately **1.4 °C per minute**.

3. **Required Preheat Duration**:
   `preheat_minutes = temp_gap / net_heating_rate`

4. **Dynamic Start Time**:
   `preheat_start_time = start_in_time - preheat_minutes`

### Example (Sri Lanka Room Temp: 25 °C)
- Room Temp: 25 °C
- Target Temp: 180 °C
- Required Preheat Time: **101 minutes** (approx 1 hour 41 mins)
- If `Start In` = **08:00 AM**, `PREHEAT` automatically starts at **06:19 AM**.
- Machine reaches **180.0 °C** exactly at **08:00 AM**.

---

## 5. Strict State Machine & Dynamic Energy-Saving Standby (Option 1)

To optimize energy efficiency during changeovers between tyres, the controller dynamically manages standby setpoints:

```text
[ IDLE ] ──> [ PREHEAT (100% Valve) ] ──> [ CURING (180 °C, ~38.75% Valve) ]
                                                │
                                  ┌─────────────┴─────────────┐
                    (Gap ≤ 60 mins)                          (Gap > 60 mins / End of Day)
                          │                                               │
             [ STANDBY (150 °C, ~10-31% Valve) ]                    [ COOLING (0% Valve) ]
                          │                                               │
             [ PREHEAT (Sensor-Triggered) ]                             [ IDLE ]
                          │
             [ CURING (Next Tyre) ]
```

### Option 1 Mode Behaviors
- **`IDLE`**: Valve = 0.00% (Ambient Room Temp).
- **`PREHEAT`**: Valve = 100.00% (Full heating power to reach 180 °C).
- **`CURING`**: PID Control maintaining 180 °C (Valve ≈ 38.75%).
- **`STANDBY` (Option 1 - Short Gaps $\le 60$ mins)**: Throttles valve down to $\approx 10-31\%$ toward a reduced standby setpoint (150 °C), saving substantial energy while keeping the press warm.
- **`PREHEAT` (Inter-cycle)**: Dynamically triggered based on real-time sensor temperature so the press ramps back to 180 °C exactly on time for the next tyre.
- **`COOLING` (Long Gaps $> 60$ mins or End of Day)**: Valve = 0.00% (Natural air cooling down to room temperature).

---

## 6. How to Run the Simulation

Run the main simulation file:

```bash
python3 simulation.py
```

### Expected Output Summary
```
Loaded Schedule for P001: Start In = 08:00, Start Out = 12:00
Initial Room Temp: 25.0 °C -> Calculated Preheat Time: 101 mins
Smart Preheat Start Time: 06:19

Time: 06:00 | Temp: 25.00 °C | Valve: 0.00% | Mode: IDLE
Time: 06:19 | Temp: 25.00 °C | Valve: 100.00% | Mode: PREHEAT
Time: 08:00 | Temp: 179.95 °C | Valve: 38.75% | Mode: CURING
Time: 12:00 | Temp: 179.20 °C | Valve: 0.00% | Mode: IDLE
Simulation complete for press P001.
```
