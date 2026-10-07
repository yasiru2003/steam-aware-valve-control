# ILP Scheduler — Model Documentation

## 1. Purpose

This document explains the Mixed Integer Linear Programming (MILP) model used for the schedule-aware steam press scheduler. The scheduler decides when each curing press should start, so that steam demand across all presses stays as flat as possible instead of spiking when several presses heat up simultaneously.

---

## 2. Problem Being Solved

When multiple curing presses start heating together, they all draw peak steam from the boiler at the same time. This creates a severe demand peak, which strains the boiler and can reduce curing temperature consistency. 

If press start times are staggered instead, the same total production throughput can be achieved with a substantially lower and smoother peak steam draw.

The scheduler decides the optimal start time offset for each press, within its allowed time window, so that the peak steam draw across the whole plant is minimised.

---

## 3. Model Type & Technology Stack

- **Model Formulation**: Peak Flattening via Mixed Integer Linear Programming (MILP).
- **Modelling Framework**: [PuLP](https://coin-or.github.io/pulp/) (Python library for formulating mathematical programming problems).
- **Solver**: **CBC** (Coin-or Branch and Cut), an open-source solver that performs branch-and-cut with linear programming relaxations to reach the global optimal integer solution.

---

## 4. Mathematical Formulation & Key Modelling Ideas

### 4.1 Index Sets & Parameters
- Let $I = \{1, 2, \dots, N\}$ be the set of curing presses.
- Let $T = \{0, 1, \dots, T_{\max}\}$ be the discrete time horizon (e.g., in 1-minute or 5-minute time steps).
- For each press $i \in I$, let $W_i \subseteq T$ be the set of allowed start time slots within its designated operational window $[ES_i, LS_i]$ (Earliest Start to Latest Start).
- Let $d_i(\tau)$ be the known steam demand profile for press $i$ at relative time $\tau \ge 0$ elapsed since its start ($0 \le \tau \le L_i$, where $L_i$ is the cycle duration of press $i$).

### 4.2 Decision Variables
1. **Binary Start Time Variables**:
   $$x_{i, s} \in \{0, 1\} \quad \forall i \in I, \; s \in W_i$$
   where $x_{i, s} = 1$ if press $i$ starts at time slot $s$, and $0$ otherwise.

2. **Epigraph Variable (Peak Steam Demand)**:
   $$P_{\text{peak}} \ge 0$$
   representing the maximum aggregated steam demand across the entire plant at any time step.

### 4.3 Constraints

1. **Exactly One Start Time per Press**:
   Each press must be assigned exactly one start time slot within its allowable window:
   $$\sum_{s \in W_i} x_{i, s} = 1 \quad \forall i \in I$$

2. **Total Steam Demand at Each Time Step**:
   The steam demand contribution of press $i$ at global time $t \in T$, given start time $s \le t$, is $d_i(t - s)$. The aggregated steam demand at time step $t$, denoted $D_{\text{total}}(t)$, is:
   $$D_{\text{total}}(t) = \sum_{i \in I} \sum_{\substack{s \in W_i \\ s \le t \le s + L_i}} d_i(t - s) \cdot x_{i, s} \quad \forall t \in T$$

3. **Epigraph Reformulation for Peak Flattening**:
   Minimising the maximum value of a function ($\min \max_t D_{\text{total}}(t)$) is non-linear. To linearise this:
   $$P_{\text{peak}} \ge D_{\text{total}}(t) \quad \forall t \in T$$
   which expands to:
   $$P_{\text{peak}} - \sum_{i \in I} \sum_{\substack{s \in W_i \\ s \le t \le s + L_i}} d_i(t - s) \cdot x_{i, s} \ge 0 \quad \forall t \in T$$

### 4.4 Objective Function
Minimise the epigraph peak variable:
$$\min \; P_{\text{peak}}$$

By construction, minimising $P_{\text{peak}}$ drives down the maximum steam demand across all time steps given the chosen press start time assignments.

---

## 5. Architectural Role & Deliverable Justification

### Why This Component is a Required Deliverable, Not Optional
- **Plant-Wide Coordination vs. Local Control**: The scheduler is the sole component responsible for resolving multi-press demand peaks across the plant.
- The per-press **valve controller** operates strictly at the local machine level and cannot coordinate or decide when other presses start.
- Without the scheduler, there is no mechanism in the system to prevent simultaneous ramp-up spikes. Thus, the MILP scheduler is a mandatory MVP deliverable.

### Boundary of Scope
- **Boiler Assumption**: The scheduler assumes the steam supply has steady/effective capacity without modeling dynamic piping or boiler combustion cycles directly.
- **No In-Flight Throttling**: The scheduler does not perform real-time priority arbitration or budget throttling during curing.
- **Handoff to Valve Controller**: Once the scheduler assigns start time offsets, each local valve controller takes over autonomously, managing preheat lead time, idle gaps, and closed-loop temperature control.

---

## 6. Computational Behaviour & Empirical Observations

Testing across synthetic press instances demonstrates a clear dichotomy in problem complexity:

| Instance Category | Press Characteristics | Symmetry & Empirical Solver Behavior | Observed Solve Time |
| :--- | :--- | :--- | :--- |
| **Homogeneous** | All presses share identical tyre sizes, durations, and steam profiles. | **High Combinatorial Symmetry**: Interchangeable presses create many symmetrically identical permutations. Branch-and-cut must explore redundant subtrees unless explicitly broken, using the full time budget. | Consistently uses the full **$\approx 15\text{ s}$** time budget (e.g., $15.1\text{ s}$ at 8 presses, $15.07\text{ s}$ at 10–20 presses). |
| **Heterogeneous** | Presses have varying tyre sizes, differing steam draw curves, and distinct cycle lengths. | **Natural Symmetry Breaking**: Different profile heights and cycle durations restrict and differentiate valid branch combinations. | Solves **fast at small scales** (**$3.38\text{ s}$** for 8 presses; $13.57\text{ s}$ for 18 presses); uses $\approx 15\text{ s}$ for other scales. |

### Decision Regarding ML Warm Start
Earlier architectural concepts considered using a Machine Learning warm start to accelerate the solver. However:
1. Homogeneous instances solve trivially fast without any acceleration.
2. In heterogeneous instances, the combinatorial landscape is complex and instance-dependent; a naive learned warm start failed to provide meaningful bounds without risk of infeasibility or suboptimality.
3. Therefore, the ML warm start was dropped in favour of pure MILP with branch-and-cut parameter tuning, reserving heuristic decomposition for future work.

---

## 7. Evaluation & Benchmark Approach

The scheduler is benchmarked under realistic industrial plant scales:
- **Press Scale**: 8 to 20 presses (consistent with tyre curing plant literature reporting 7 to 12 curing heaters).
- **Test Scenarios**: Both homogeneous and heterogeneous sets across varying window flexibilities.
- **Key Metrics**:
  1. **Solve Time** (seconds to provable optimality or time-limit termination).
  2. **Peak Steam Draw Reduction (%)**:
     $$\text{Peak Reduction} = \frac{P_{\text{unstaggered}} - P_{\text{scheduled}}}{P_{\text{unstaggered}}} \times 100\%$$
  3. **Schedule Makespan & Delay Impact**: Ensuring peak flattening does not violate operational delivery deadlines.

---

## 8. CSV Output Specifications

To enable seamless ingestion by reporting tools, plant dashboards, and the physical digital twin simulator, the evaluation outputs standard CSV files:

### 8.1 Benchmark Results Summary (`benchmark_results.csv`)
Logs performance metrics across all evaluated scales:

| Column Header | Data Type | Description |
| :--- | :--- | :--- |
| `instance_type` | String | `Homogeneous` or `Heterogeneous` |
| `num_presses` | Integer | Total number of presses evaluated ($N \in [8, 20]$) |
| `solver_status` | String | CBC solve status (`Optimal`, `Not Solved` / Time Limit) |
| `solve_time_sec` | Float | Computation duration in seconds |
| `baseline_peak_kgh` | Float | Maximum steam demand (kg/h) under unstaggered start ($s_i = 0$) |
| `scheduled_peak_kgh` | Float | Maximum steam demand (kg/h) under MILP staggered schedule |
| `peak_reduction_kgh` | Float | Absolute peak steam reduction ($P_{\text{baseline}} - P_{\text{scheduled}}$) |
| `peak_reduction_pct` | Float | Percentage reduction in peak steam consumption (%) |
| `time_limit_sec` | Integer | Solver time limit cap |
| `time_step_min` | Integer | Discretization resolution in minutes |

### 8.2 Production Schedule Solution (`results/schedule_<type>_n<N>.csv`)
Exported per instance run, adhering to the Digital Twin execution schema:

| Column Header | Data Type | Description |
| :--- | :--- | :--- |
| `press_id` | String | Unique identifier (e.g., `Press_01`) |
| `tyre_type` | String | Tyre specification profile |
| `start_hour` | Float | Scheduled start time offset in hours (e.g., `0.25` for 15 min stagger) |
| `cure_duration_hours` | Float | Total curing cycle duration in hours |
| `idle_gap_start_hour` | Float | Operational break start time |
| `idle_gap_duration_hours` | Float | Operational break duration |

### 8.3 Time-Series Profile Comparison (`results/steam_profiles_timeseries.csv`)
Continuous steam demand curve comparison at each time step $t$:

| Column Header | Data Type | Description |
| :--- | :--- | :--- |
| `instance_type` | String | Scenario type |
| `num_presses` | Integer | Number of presses |
| `time_min` | Integer | Elapsed simulation time in minutes |
| `time_hour` | Float | Elapsed simulation time in hours |
| `baseline_steam_kgh` | Float | Instantaneous total boiler demand without staggering (kg/h) |
| `scheduled_steam_kgh` | Float | Instantaneous total boiler demand with MILP staggering (kg/h) |

