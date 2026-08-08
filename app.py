import math
import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from controller import ControllerNode
from disturbance import ThermalDisturbance
from pid_controller import PIDController
from schedule_fetcher import get_all_press_schedules

# Page Configuration
st.set_page_config(
    page_title="Thermal Control System",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    /* Global styles */
    .main {
        background-color: #0e1117;
    }
    .stApp {
        max-width: 1400px;
        margin: 0 auto;
    }
    
    /* Header Card */
    .header-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 24px;
        margin-bottom: 24px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }
    .header-title {
        color: #f8fafc;
        font-size: 28px;
        font-weight: 700;
        margin-bottom: 8px;
    }
    .header-subtitle {
        color: #94a3b8;
        font-size: 15px;
    }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Sidebar Controls & Schedule Discovery
# ---------------------------------------------------------
try:
    sched_df = pd.read_csv("schedules/schedule.csv")
    available_presses = [str(p).strip() for p in sched_df["Press No"].dropna().unique()]
except Exception:
    available_presses = ["P001"]

if not available_presses:
    available_presses = ["P001"]

st.sidebar.header("Physical Press Controls")

press_unit = st.sidebar.selectbox(
    "Select Industrial Press",
    available_presses,
    index=0,
    help="Select physical press unit from schedule.csv to monitor and control."
)

press_power = st.sidebar.toggle(
    f"Press {press_unit} Production Switch (ON / OFF)",
    value=True,
    help="Physical switch to manually start making tyres (ON) or shut down production (OFF)."
)

st.sidebar.header("Simulation Parameters")

schedule_source = st.sidebar.radio(
    "Schedule Source",
    [f"Load schedule.csv ({press_unit} Multi-Tyre)", "Single Tyre Manual Input"],
    index=0
)

target_temperature = st.sidebar.number_input(
    "Target Cure Temperature (°C)",
    min_value=50.0,
    max_value=250.0,
    value=130.0,
    step=5.0,
    help="Target temperature for holding flat during curing."
)

ambient_temperature = st.sidebar.slider(
    "Ambient Room Temperature (°C)",
    min_value=10.0,
    max_value=45.0,
    value=25.0,
    step=1.0
)

enable_disturbance = st.sidebar.checkbox(
    "Simulate Cold Tyre Heat Shock (-8 °C drop)",
    value=True,
    help="Simulates real-world temperature drop when cold raw rubber is inserted into the hot press."
)

if schedule_source == "Single Tyre Manual Input":
    st.sidebar.subheader("Schedule Timeline")
    start_hour = st.sidebar.number_input("Cure Start Hour (e.g. 8 for 08:00)", min_value=1, max_value=23, value=8)
    cure_duration_hours = st.sidebar.slider("Cure Duration (Hours)", min_value=1, max_value=12, value=4)
    cooling_duration_hours = st.sidebar.slider("Cooling Observation (Hours)", min_value=1, max_value=18, value=12)

with st.sidebar.expander("PID & Thermal Parameters"):
    kp = st.number_input("Kp (Proportional)", value=0.8, step=0.1)
    ki = st.number_input("Ki (Integral)", value=0.01, step=0.005, format="%.3f")
    kd = st.number_input("Kd (Derivative)", value=0.2, step=0.05)
    heating_coeff = st.number_input("Heating Coeff (°C/min per % valve)", value=0.02, step=0.005, format="%.3f")
    cooling_coeff = st.number_input("Cooling Coeff (°C/min per °C delta)", value=0.005, step=0.001, format="%.3f")

# ---------------------------------------------------------
# Simulation Physics & Plotting Engine
# ---------------------------------------------------------
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
    """
    Calculates the dynamic break-even idle gap duration (in minutes).
    Replaces the fixed cutoff with a cost-based decision:
    - hold_cost: Steam spent keeping the press near cure temperature for the whole gap.
    - shut_cost: Extra reheat energy needed because the press cooled down during the gap.
    
    If gap < threshold, holding warm (STANDBY) is cheaper.
    If gap >= threshold, shutting off completely (COOLING) is cheaper.
    """
    import math
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

def build_simulation_plot(with_disturbance):
    # Fetch Schedule
    if "schedule.csv" in schedule_source:
        cycles = get_all_press_schedules("schedules/schedule.csv", press_unit)
        if not cycles:
            cycles = [{
                "tyre_id": f"{press_unit}_T1",
                "start_in": datetime.strptime("08:00", "%H:%M").time(),
                "start_out": datetime.strptime("15:00", "%H:%M").time()
            }]
    else:
        cure_start_time = datetime.strptime(f"{start_hour:02d}:00", "%H:%M").time()
        today = datetime.today()
        dt_start = datetime.combine(today, cure_start_time)
        dt_end = dt_start + timedelta(hours=cure_duration_hours)
        cycles = [{
            "tyre_id": f"{press_unit}_T1",
            "start_in": cure_start_time,
            "start_out": dt_end.time()
        }]

    # Compute Cold Preheat Requirements for First Tyre
    first_start_in = cycles[0]["start_in"]
    preheat_minutes = calculate_preheat_minutes(
        ambient_temperature,
        target_temperature,
        ambient_temperature,
        heating_coeff,
        cooling_coeff
    )

    today_date = datetime.today()
    start_in_dt = datetime.combine(today_date, first_start_in)
    preheat_start_dt = start_in_dt - timedelta(minutes=preheat_minutes)
    sim_start_dt = preheat_start_dt - timedelta(minutes=30)
    last_cycle_end = cycles[-1]["start_out"]

    # Simulation loop settings
    plant = PlantSimulation(ambient_temperature, ambient_temperature, heating_coeff, cooling_coeff)
    pid = PIDController(
        kp=kp,
        ki=ki,
        kd=kd,
        feedforward=(target_temperature - ambient_temperature) * cooling_coeff / heating_coeff
    )
    disturbance_model = ThermalDisturbance(enable_tyre_shock=with_disturbance)
    STANDBY_TEMP = 100.0

    history = []
    current_dt = sim_start_dt
    previous_mode = None
    elapsed_minutes = 0
    max_sim_minutes = 24 * 60  # 24 Hours simulation max

    while elapsed_minutes < max_sim_minutes:
        cur_time = current_dt.time()
        setpoint = target_temperature

        # Manual Physical Switch Override (If Press Power is turned OFF)
        if not press_power:
            mode = "SHUTDOWN (OFF)"
            setpoint = ambient_temperature
            valve = 0.0
            pid.reset()
        else:
            # State Machine Logic when Press Power is ON
            if cur_time < preheat_start_dt.time() and elapsed_minutes < 600:
                mode = "IDLE"
                setpoint = ambient_temperature
            elif preheat_start_dt.time() <= cur_time < first_start_in and elapsed_minutes < 600:
                mode = "PREHEAT"
                setpoint = target_temperature
            elif elapsed_minutes >= 990 or (cur_time >= last_cycle_end and elapsed_minutes > 500):
                if plant.temperature > ambient_temperature + 1.0:
                    mode = "COOLING"
                else:
                    mode = "IDLE"
                setpoint = ambient_temperature
            else:
                in_curing_cycle = False
                for c in cycles:
                    if c["start_in"] <= cur_time < c["start_out"]:
                        mode = "CURING"
                        setpoint = target_temperature
                        in_curing_cycle = True
                        break
                if not in_curing_cycle:
                    # Inter-cycle gap handling
                    for i in range(len(cycles) - 1):
                        prev_out = cycles[i]["start_out"]
                        next_in = cycles[i + 1]["start_in"]
                        if prev_out <= cur_time < next_in:
                            dummy_date = datetime.today().date()
                            gap_mins = (
                                datetime.combine(dummy_date, next_in) -
                                datetime.combine(dummy_date, prev_out)
                            ).total_seconds() / 60.0

                            dynamic_hold_threshold = calculate_hold_threshold(
                                target_temperature,
                                ambient_temperature,
                                heating_coeff,
                                cooling_coeff
                            )

                            if gap_mins <= dynamic_hold_threshold:
                                needed_reheat = calculate_preheat_minutes(
                                    plant.temperature,
                                    target_temperature,
                                    ambient_temperature,
                                    heating_coeff,
                                    cooling_coeff
                                )
                                dt_next_in = datetime.combine(dummy_date, next_in)
                                dt_cur_time = datetime.combine(dummy_date, cur_time)
                                time_rem_mins = (dt_next_in - dt_cur_time).total_seconds() / 60.0

                                if time_rem_mins > needed_reheat:
                                    mode = "STANDBY"
                                    setpoint = STANDBY_TEMP
                                else:
                                    mode = "PREHEAT"
                                    setpoint = target_temperature
                            else:
                                mode = "COOLING"
                                setpoint = ambient_temperature
                            break

            # Calculate disturbance effect
            dist_effect = disturbance_model.get_disturbance(mode, dt=1.0)

            # Reset PID on mode transition into CURING
            if mode == "CURING" and previous_mode != "CURING":
                pid.reset()
            previous_mode = mode

            # Determine Valve Output
            if mode == "IDLE":
                valve = 0.0
                pid.reset()
            elif mode == "PREHEAT":
                valve = 100.0
            elif mode in ("CURING", "STANDBY"):
                pid.feedforward = (setpoint - ambient_temperature) * cooling_coeff / heating_coeff
                valve = pid.compute(setpoint, plant.temperature, dt=1.0)
            elif mode == "COOLING":
                valve = 0.0
                pid.reset()

            valve = max(0.0, min(100.0, valve))

        history.append({
            "DateTime": current_dt,
            "Timestamp": current_dt.strftime("%H:%M"),
            "TimeMinutes": elapsed_minutes,
            "Temperature": plant.temperature,
            "Target": setpoint,
            "Valve": valve,
            "Mode": mode
        })
        
        # Update plant physics
        plant.update(valve, disturbance_delta=dist_effect if press_power else 0.0, dt=1.0)
        current_dt += timedelta(minutes=1)
        elapsed_minutes += 1

        # Stop after last cycle ends and plant cools down
        if elapsed_minutes > 990 and plant.temperature <= ambient_temperature + 1.0:
            break

    df = pd.DataFrame(history)

    # Plotly Interactive Thermal Curve
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.12,
        subplot_titles=(
            f"Press Temperature Over Time (°C) {'[With Disturbances]' if with_disturbance else '[Ideal Baseline]'}",
            f"PID Control Valve Opening (%) {'[With Disturbances]' if with_disturbance else '[Ideal Baseline]'}"
        )
    )

    # Color mapping for modes
    mode_colors = {
        "IDLE": "#94a3b8",
        "PREHEAT": "#f59e0b",
        "CURING": "#10b981",
        "STANDBY": "#a855f7",
        "COOLING": "#38bdf8"
    }

    # 1. Main Continuous Temperature Curve (No Criss-Crossing Lines)
    fig.add_trace(
        go.Scatter(
            x=df["DateTime"],
            y=df["Temperature"],
            name="Press Temperature (°C)",
            line=dict(color="#38bdf8", width=3),
            customdata=df["Mode"],
            text=df["Timestamp"],
            hovertemplate="<b>Mode: %{customdata}</b><br>Time: %{text}<br>Temp: %{y:.2f} °C<extra></extra>"
        ),
        row=1, col=1
    )

    # Target Setpoint Line Reference
    fig.add_trace(
        go.Scatter(
            x=df["DateTime"],
            y=df["Target"],
            name=f"Target Setpoint ({target_temperature:.1f} °C)",
            line=dict(color="#ef4444", width=2, dash="dash"),
            hovertemplate="Target: %{y:.1f} °C<extra></extra>"
        ),
        row=1, col=1
    )

    # 2. Valve Opening Line
    fig.add_trace(
        go.Scatter(
            x=df["DateTime"],
            y=df["Valve"],
            name="Valve Opening (%)",
            line=dict(color="#10b981", width=2),
            fill="tozeroy",
            fillcolor="rgba(16, 185, 129, 0.15)",
            customdata=df["Mode"],
            text=df["Timestamp"],
            hovertemplate="<b>Mode: %{customdata}</b><br>Time: %{text}<br>Valve: %{y:.2f}%<extra></extra>"
        ),
        row=2, col=1
    )

    # Plotly Layout Styling
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="#1e293b",
        height=650,
        margin=dict(l=40, r=40, t=50, b=80),
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.18,
            xanchor="center",
            x=0.5,
            font=dict(size=12, color="#94a3b8")
        )
    )

    fig.update_yaxes(title_text="Temperature (°C)", row=1, col=1, gridcolor="#334155", range=[0, max(160.0, target_temperature + 20)])
    fig.update_yaxes(title_text="Valve Opening (%)", row=2, col=1, gridcolor="#334155", range=[-5, 105])
    fig.update_xaxes(title_text="Simulation Time", row=2, col=1, gridcolor="#334155", tickformat="%H:%M")

    return df, fig

status_badge = f'<span style="background-color: #10b981; color: #022c22; font-weight: 700; font-size: 13px; padding: 4px 12px; border-radius: 20px;">Press {press_unit} Status: RUNNING (Production Active)</span>' if press_power else f'<span style="background-color: #ef4444; color: #ffffff; font-weight: 700; font-size: 13px; padding: 4px 12px; border-radius: 20px;">Press {press_unit} Status: MANUAL SHUTDOWN (OFF) — Valve 0.0%</span>'

st.markdown(f"""
<div class="header-card">
    <div class="header-title">Press Thermal Control System — Unit {press_unit}</div>
    <div style="margin-top: 10px;">{status_badge}</div>
</div>
""", unsafe_allow_html=True)

tab1, tab2 = st.tabs([
    "Real-World Simulation (With Thermal Disturbances)",
    "Ideal Baseline (Without Disturbances)"
])

with tab1:
    st.caption("Simulates real-world cold tyre heat shock (-8 °C drop), showing PID controller spiking to recover target temperature.")
    df_dist, fig_dist = build_simulation_plot(with_disturbance=True)
    st.plotly_chart(fig_dist, use_container_width=True)
    
    with st.expander("View Complete Data Table (With Disturbances)"):
        st.dataframe(df_dist, use_container_width=True)
        csv_dist = df_dist.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download CSV (With Disturbances)",
            data=csv_dist,
            file_name=f"press_simulation_with_disturbances_{target_temperature:.0f}C.csv",
            mime="text/csv",
            key="dl_dist"
        )

with tab2:
    st.caption("Simulates pure ideal thermal physics without external heat loss disturbances.")
    df_ideal, fig_ideal = build_simulation_plot(with_disturbance=False)
    st.plotly_chart(fig_ideal, use_container_width=True)
    
    with st.expander("View Complete Data Table (Without Disturbances)"):
        st.dataframe(df_ideal, use_container_width=True)
        csv_ideal = df_ideal.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="Download CSV (Without Disturbances)",
            data=csv_ideal,
            file_name=f"press_simulation_ideal_{target_temperature:.0f}C.csv",
            mime="text/csv",
            key="dl_ideal"
        )
