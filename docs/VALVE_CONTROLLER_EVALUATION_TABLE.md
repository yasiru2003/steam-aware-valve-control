# 🎛️ Valve Controller Evaluation & Verification Results

**Project**: Steam-Aware Scheduling and Smart Valve Control for Solid Tyre Curing  
**Component**: Per-Press Smart Valve Controller (`Digital Twin Own/` — `app.py`, `controller.py`, `pid_controller.py`, `simulation.py`)  
**Scope**: Single-Press Autonomous Execution (Solid tyre curing: single circuit, mould-only heating, ~130°C setpoint, ~7-hour cycle)  
**Submission Date**: September 2026  

---

## 🏛️ System Architecture & Scope Boundary

The project comprises **two separate, complementary components** working together for a solid tyre curing plant:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                       1. MILP STEAM SCHEDULER                           │
│   • Global Plant-Wide Optimization (PuLP + CBC)                         │
│   • Decides start time offsets BEFORE curing begins                     │
│   • Epigraph formulation with binary start variables                    │
│   • Where multi-press coordination happens: FLATTENS BOILER PEAK DEMAND │
│     (Achieves 58% - 62% peak reduction across 8-20 presses)             │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ Scheduled Start Times & Gaps
                                     ▼
┌─────────────────────────────────────────────────────────────────────────┐
│               2. PER-PRESS SMART VALVE CONTROLLER (Local)               │
│   • Runs independently — ONE autonomous instance per curing press       │
│   • Strictly SINGLE-PRESS scope (NO multi-press live arbitration)       │
│   • Strictly THREE schedule-driven jobs:                                │
│     1. Dynamic Nonlinear Preheat Lead Time                              │
│     2. Schedule-Driven Idle Gap Decision (Standby vs Shutoff)           │
│     3. Closed-Loop PID Temperature Control with Anti-Windup             │
└─────────────────────────────────────────────────────────────────────────┘
```

> [!IMPORTANT]
> **Strict Scope Boundary for the Valve Controller:**
> - The valve controller **never coordinates, arbitrates, or shares a steam budget** between multiple presses during runtime.
> - It **never assigns priority** to one press over another.
> - The boiler is assumed to have steady, effectively infinite supply capacity.
> - **Peak steam demand reduction across multiple presses belongs entirely to the MILP Scheduler**, not the local valve controller. The valve controller independently executes each press's preheat, cure, and idle states at the times assigned by the scheduler.

---

## 📊 Summary Table: Single-Press Smart Valve Controller Proof Tests

| Test Requirement | Evaluation Objective & Conditions | Ordinary / Uncontrolled Baseline | Smart Valve Controller | Performance Improvement & Result | Status |
| :--- | :--- | :--- | :--- | :--- | :---: |
| **1. Dynamic Preheat Lead Time** | **Nonlinear Warm-up Timing**<br>• Cold start from room temp ($25.0^\circ\text{C}$)<br>• Target curing temp: $130.0^\circ\text{C}$<br>• Scheduled Start In: `08:00` | **Fixed static preheat guess**<br>• Starts too early: wastes steam holding at $130^\circ\text{C}$ before tyre is loaded.<br>• Starts too late: delays production schedule. | **Dynamic simulation from cooling curve**<br>• Integrates differential model: $\frac{dT}{dt} = \dot{Q}_{\text{in}} - \dot{Q}_{\text{loss}}$<br>• Calculates exact required lead time: **61 minutes**.<br>• Valve triggers at `06:59`. | **Zero Schedule Delay & Zero Premature Waste**<br>• Reaches **$130.37^\circ\text{C}$** at exactly `08:00`<br>• Perfectly ready for tyre insertion without idle overheating. | ✅ **VERIFIED** |
| **2. Idle Gap Decision (Standby vs Shutoff)** | **Inter-Job Gap Energy Management**<br>• Compares holding cost vs reheat recovery cost<br>• Decision threshold: $60\text{ minutes}$ | **Manual human oversight**<br>• Valve left cracked or fully open between batches.<br>• Continuous parasitic steam loss throughout shift gaps. | **Autonomous threshold logic**<br>• **Short gaps ($\le 60\text{ m}$)**: Enters **STANDBY** ($100.0^\circ\text{C}$ setpoint), then triggers dynamic reheat.<br>• **Long gaps ($> 60\text{ m}$)**: Enters **COOLING** (Valve $0.0\%$, auto-shutoff). | **Optimized Trade-Off**<br>• Eliminates idle steam venting on long breaks.<br>• Minimizes thermal shock and reheat time on short changeovers ($30\text{ min}$). | ✅ **VERIFIED** |
| **3. Closed-Loop PID Temperature Tracking** | **Steady-State Cure Holding**<br>• Long solid tyre cure cycle ($7.0\text{ hours}$)<br>• Setpoint: $130.0^\circ\text{C}$<br>• Feedforward equilibrium: $26.25\%$ | **Unthrottled / manual valve control**<br>• Severe thermal overshoot.<br>• Large cycling oscillations damaging rubber vulcanization. | **PID with Anti-Windup & Feedforward**<br>• $K_p = 0.8$, $K_i = 0.01$, $K_d = 0.2$<br>• Feedforward bias matches natural cooling: $\frac{(130-25)\times 0.005}{0.02} = 26.25\%$ | **Tight Holding Around Setpoint**<br>• Temperature holds stably at **$130.0^\circ\text{C} \pm 0.4^\circ\text{C}$** (ideal) / **$\pm 1 - 3^\circ\text{C}$** (with disturbance)<br>• Conditional integration prevents integral saturation. | ✅ **VERIFIED** |

---

## 🔬 Detailed Technical Breakdown of Valve Controller Functions

### 1. Dynamic Preheat Lead Time Calculation (Nonlinear Cooling Curve)
- **Problem**: In manual factory operations, operators either turn steam on hours ahead (burning excess boiler fuel to maintain an empty mould at $130^\circ\text{C}$) or turn it on late (delaying tyre vulcanization start times).
- **Physical Model**: Rather than using a static constant (e.g., fixed 90 min), the controller evaluates the instantaneous thermal model:
  $$\frac{dT}{dt} = \frac{u \cdot \alpha_{\text{heat}} - (T - T_{\text{ambient}}) \cdot \beta_{\text{cool}}}{m \cdot C_p}$$
  Where $\alpha_{\text{heat}} = 0.02^\circ\text{C}/\text{min per }\%$ and $\beta_{\text{cool}} = 0.005^\circ\text{C}/\text{min per }^\circ\text{C}\Delta T$.
- **Empirical Execution (P001 Cycle 1)**:
  - Ambient room temperature: $25.0^\circ\text{C}$.
  - Target temperature: $130.0^\circ\text{C}$.
  - Computed lead time: **61 minutes**.
  - Cycle start: `08:00` $\rightarrow$ Preheat dynamically triggered at `06:59` with valve = $100.0\%$.
  - At `08:00`: Press temperature measures **$130.37^\circ\text{C}$**, seamlessly transitioning to `CURING` mode with zero wasted pre-curing holding time.

### 2. Schedule-Driven Idle Gap Decision (Standby vs Shutoff)
- **Problem**: Solid tyre production schedules include changeover intervals between tyres (e.g., 30 min) as well as shift breaks or maintenance halts (several hours).
- **Decision Logic**:
  - The controller inspects the gap duration $\Delta t_{\text{gap}} = t_{\text{next\_in}} - t_{\text{prev\_out}}$.
  - **Case A: Short Gap ($\Delta t_{\text{gap}} \le 60\text{ mins}$)**:
    - Holding warm at a reduced setpoint ($100.0^\circ\text{C}$) requires less energy than letting the heavy steel mould drop to ambient and reheating from cold.
    - Press enters `STANDBY` mode; valve throttles down.
    - When remaining time equals required dynamic reheat duration, the controller automatically fires `PREHEAT` ($100\%$ valve), bringing mould back to $130^\circ\text{C}$ right on schedule.
  - **Case B: Long Gap ($\Delta t_{\text{gap}} > 60\text{ mins}$ or End-of-Day)**:
    - Continuous holding cost exceeds reheat recovery energy.
    - Press enters `COOLING` mode; valve completely shut ($0.0\%$). Zero parasitic leakage.

### 3. Closed-Loop PID Temperature Regulation with Anti-Windup
- **Equilibrium Feedforward Bias**:
  - At steady-state cure ($130.0^\circ\text{C}$ in a $25.0^\circ\text{C}$ ambient):
    $$\text{Natural Cooling Rate} = (130 - 25) \times 0.005 = 0.525^\circ\text{C}/\text{min}$$
    $$\text{Valve Equilibrium} = \frac{0.525}{0.02} = \mathbf{26.25\%}$$
  - Providing this feedforward bias enables the PID terms to handle only disturbances without needing to build up excessive integral action.
- **Anti-Windup Protection (Conditional Integration)**:
  - During the 61-minute preheat ramp when error is large ($e = 130 - T$), tentative integral accumulation is checked against output limits ($[0.0, 100.0\%]$).
  - Clamping integration while the actuator is saturated prevents large overshoot when the temperature arrives at $130.0^\circ\text{C}$.
- **Steady-State Performance**:
  - Steady-state curing holds at **$130.0^\circ\text{C} \pm 0.4^\circ\text{C}$** in ideal conditions, and within **$\pm 1 - 3^\circ\text{C}$** under insertion heat shock disturbances, satisfying solid tyre vulcanization consistency requirements.

---

## 📌 Note on Multi-Press Peak Steam Demand Results

| Component | Responsibility | Where Results are Documented |
| :--- | :--- | :--- |
| **MILP Scheduler** (`Scheduler_MLIP/`) | **Multi-Press Peak Demand Reduction** (staggering start offsets across 8–20 presses to flatten aggregate boiler load) | [Scheduler Model Documentation](file:///Users/yasiru/Desktop/Academic%20/Sem%205/Embedded%20Project/Scheduler_MLIP/MODEL_DOCUMENTATION.md) & [Benchmark Results](file:///Users/yasiru/Desktop/Academic%20/Sem%205/Embedded%20Project/Scheduler_MLIP/benchmark_results.csv) |
| **Valve Controller** (`Digital Twin Own/`) | **Single-Press Autonomous Control** (Preheat lead time, idle standby/shutoff decision, PID temperature tracking) | [Valve Controller Evaluation Table](file:///Users/yasiru/Desktop/Academic%20/Sem%205/Embedded%20Project/Digital%20Twin/VALVE_CONTROLLER_EVALUATION_TABLE.md) *(This Document)* |
