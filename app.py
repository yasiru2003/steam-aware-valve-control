import time
from datetime import datetime, timedelta

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from schedule_fetcher import read_csv, get_all_press_schedules
from multi_simulation import PressSimulationState
from hardware_bridge import ESP32SerialBridge

# Page Configuration
st.set_page_config(
    page_title="Multi-Press Live Control Demo",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stApp { max-width: 1500px; margin: 0 auto; }
    
    .header-card {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 12px 20px;
        margin-bottom: 12px;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
    }
    .header-title { color: #f8fafc; font-size: 28px; font-weight: 700; margin-bottom: 8px; }
    
    /* Metrics Box */
    div[data-testid="metric-container"] {
        background-color: #1e293b;
        border: 1px solid #334155;
        padding: 10px;
        border-radius: 8px;
        box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
    }
    
    /* Prevent iframe collapsing which pulls the page up */
    div[data-testid="column"] {
        min-height: 450px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="header-card">
    <div class="header-title">Live Multi-Press Thermal Orchestration Dashboard</div>
    <div style="color: #94a3b8;">Real-time execution of per-press predictive pre-heating and PID control.</div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# Sidebar Configuration & Schedule Load
# ---------------------------------------------------------
st.sidebar.header("Global Schedule & Control")

try:
    sched_df = pd.read_csv("schedules/schedule.csv")
    available_presses = [str(p).strip() for p in sched_df["Press No"].dropna().unique()]
except Exception:
    available_presses = ["P001", "P002"]
    sched_df = pd.DataFrame([
        {"Press No": "P001", "Start In": "2026-08-10 08:00", "Start Out": "2026-08-10 15:00"},
        {"Press No": "P002", "Start In": "2026-08-10 09:00", "Start Out": "2026-08-10 16:00"}
    ])

# Session State Initialization
if "running" not in st.session_state:
    st.session_state.running = False

if "sim_initialized" not in st.session_state:
    st.session_state.sim_initialized = False
    st.session_state.elapsed_minutes = 0
    st.session_state.sim_clock = None
    st.session_state.press_states = {}
    st.session_state.hw_bridge = None

with st.sidebar.expander("PID & Thermal Parameters", expanded=False):
    target_temperature = st.number_input("Target Cure Temperature (°C)", value=130.0, step=5.0)
    ambient_temperature = st.slider("Ambient Room Temp (°C)", min_value=10.0, max_value=45.0, value=25.0)
    enable_disturbance = st.checkbox("Simulate Thermal Shock", value=True)
    kp = st.number_input("Kp (Proportional)", value=0.8, step=0.1)
    ki = st.number_input("Ki (Integral)", value=0.01, step=0.005, format="%.3f")
    kd = st.number_input("Kd (Derivative)", value=0.2, step=0.05)
    heating_coeff = st.number_input("Heating Coeff (°C/min per % valve)", value=0.02, step=0.005, format="%.3f")
    cooling_coeff = st.number_input("Cooling Coeff (°C/min per °C delta)", value=0.005, step=0.001, format="%.3f")

sim_config = {
    'target_temperature': target_temperature,
    'ambient_temperature': ambient_temperature,
    'enable_disturbance': enable_disturbance,
    'kp': kp,
    'ki': ki,
    'kd': kd,
    'heating_coeff': heating_coeff,
    'cooling_coeff': cooling_coeff
}

# Live Schedule Table in Sidebar
st.sidebar.subheader("Production Schedule")
st.sidebar.dataframe(sched_df, use_container_width=True, hide_index=True)

# Hardware / Simulation Mode
st.sidebar.subheader("Execution Mode")
sim_mode = st.sidebar.radio("Mode", ["Software Simulation", "ESP32 Hardware-in-the-Loop"])
serial_port = st.sidebar.text_input("ESP32 Serial Port", value="/dev/ttyUSB0" if sim_mode == "ESP32 Hardware-in-the-Loop" else "")

# Power Switches
st.sidebar.subheader("Manual Overrides")
press_power_switches = {}
for pid in available_presses:
    press_power_switches[pid] = st.sidebar.toggle(f"{pid} Power (ON / OFF)", value=True, key=f"power_{pid}")

col1, col2 = st.sidebar.columns(2)
if col1.button("▶️ Start Live Demo", use_container_width=True, type="primary"):
    if not st.session_state.sim_initialized:
        # Connect hardware bridge if required
        if sim_mode == "ESP32 Hardware-in-the-Loop" and serial_port:
            st.session_state.hw_bridge = ESP32SerialBridge(port=serial_port)
            if not st.session_state.hw_bridge.connect():
                st.sidebar.error("Failed to connect to ESP32! Check port and pyserial.")
                st.stop()
        
        # Initialize presses
        earliest_start = None
        for pid in available_presses:
            cycles = get_all_press_schedules("schedules/schedule.csv", pid)
            if not cycles: continue
            
            # If in hardware mode, only apply the bridge to the first press for now 
            # (since there's only one ESP32 connected to this port)
            bridge = st.session_state.hw_bridge if pid == available_presses[0] else None
            
            state = PressSimulationState(pid, cycles, sim_config, hardware_bridge=bridge)
            st.session_state.press_states[pid] = state
            
            if state.preheat_start_dt:
                if earliest_start is None or state.preheat_start_dt < earliest_start:
                    earliest_start = state.preheat_start_dt
                
        # Start clock 30 mins before earliest preheat
        st.session_state.sim_clock = earliest_start - timedelta(minutes=30)
        st.session_state.sim_initialized = True
        
    st.session_state.running = True
    st.rerun()

if col2.button("⏸️ Stop Demo", use_container_width=True):
    st.session_state.running = False
    st.rerun()
    
if st.sidebar.button("🔄 Reset Demo", use_container_width=True):
    if st.session_state.get("hw_bridge"):
        st.session_state.hw_bridge.disconnect()
        st.session_state.hw_bridge = None
    st.session_state.running = False
    st.session_state.sim_initialized = False
    st.rerun()

# ---------------------------------------------------------
# Main UI Placeholders
# ---------------------------------------------------------
if not st.session_state.sim_initialized:
    st.info("Simulation is standing by. Press **Start Live Demo** in the sidebar to begin.")
    st.stop()

# 1. Metrics Placeholders
st.subheader("Live Press Status")
metric_cols = st.columns(len(available_presses))
metric_placeholders = {pid: col.empty() for pid, col in zip(available_presses, metric_cols)}

# 2. Graph Placeholders (Side by Side)
st.subheader("Side-by-Side Live Telemetry")
graph_cols = st.columns(len(available_presses))
graph_placeholders = {pid: col.empty() for pid, col in zip(available_presses, graph_cols)}

# ---------------------------------------------------------
# Live Simulation Tick Logic
# ---------------------------------------------------------
if st.session_state.running:
    # Advance time by 15 minutes per tick for ~45 sec demo execution (to reduce Plotly render flickering)
    dt_step = 15.0
    
    for pid, state in st.session_state.press_states.items():
        state.step(
            st.session_state.sim_clock, 
            st.session_state.elapsed_minutes, 
            press_power_switches[pid], 
            dt_step_minutes=dt_step
        )
        
    st.session_state.sim_clock += timedelta(minutes=dt_step)
    st.session_state.elapsed_minutes += dt_step
    # Stop condition: check if all presses have finished their last cycle and cooled down
    all_done = True
    for state in st.session_state.press_states.values():
        if state.last_cycle_end:
            # We consider a press "done" if we are 12 hours past its last cycle
            if st.session_state.sim_clock < state.last_cycle_end + timedelta(hours=12):
                all_done = False
                break
                
    if all_done:
        st.session_state.running = False

# ---------------------------------------------------------
# Update UI
# ---------------------------------------------------------
# Update Metrics
mode_colors = {
    "IDLE": "gray",
    "PREHEAT": "orange",
    "CURING": "green",
    "STANDBY": "purple",
    "COOLING": "blue",
    "SHUTDOWN (OFF)": "red"
}

for pid, state in st.session_state.press_states.items():
    current_mode = state.mode
    color = mode_colors.get(current_mode, "gray")
    
    metric_html = f"""
    <div style="text-align: center;">
        <h4 style="margin-bottom:0;">{pid}</h4>
        <p style="font-size: 20px; font-weight: bold; margin: 2px 0;">{state.plant.temperature:.1f} °C</p>
        <span style="background-color: {color}; padding: 2px 10px; border-radius: 12px; color: white; font-weight: bold; font-size: 12px;">
            {current_mode}
        </span>
    </div>
    """
    metric_placeholders[pid].markdown(metric_html, unsafe_allow_html=True)

colors = ["#38bdf8", "#f472b6", "#fbbf24", "#34d399"]

for idx, (pid, state) in enumerate(st.session_state.press_states.items()):
    if not state.history: continue
    
    df = pd.DataFrame(state.history)
    color = colors[idx % len(colors)]
    
    # Draw Plotly Chart individually per press
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.1,
        subplot_titles=(f"{pid} Temperatures (°C)", f"{pid} Valve Actuation (%)")
    )
    
    # Temperature line
    fig.add_trace(
        go.Scatter(
            x=df["DateTime"], y=df["Temperature"],
            name=f"{pid} Temp",
            line=dict(color=color, width=2),
            customdata=df["Mode"], text=df["Timestamp"],
            hovertemplate="<b>%{customdata}</b><br>%{text}<br>Temp: %{y:.1f}°C<extra></extra>"
        ),
        row=1, col=1
    )
    
    # Valve line
    fig.add_trace(
        go.Scatter(
            x=df["DateTime"], y=df["Valve"],
            name=f"{pid} Valve",
            line=dict(color=color, width=1.5, dash="dot"),
            customdata=df["Mode"], text=df["Timestamp"],
            hovertemplate="<b>%{customdata}</b><br>%{text}<br>Valve: %{y:.1f}%<extra></extra>"
        ),
        row=2, col=1
    )
    
    # Add vertical line for first start_in
    if state.first_start_in:
        fig.add_vline(x=state.first_start_in.strftime('%Y-%m-%d %H:%M:%S'), line_dash="dash", line_color=color, opacity=0.5, row=1, col=1)

    # Formatting
    fig.update_layout(
        template="plotly_dark", paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="#1e293b",
        height=380, margin=dict(l=30, r=30, t=30, b=20),
        hovermode="x unified",
        showlegend=False
    )
    fig.update_yaxes(title_text="Temperature (°C)", row=1, col=1, range=[15, target_temperature + 20])
    fig.update_yaxes(title_text="Valve %", row=2, col=1, range=[-5, 105])

    # Inject chart into its specific column placeholder
    graph_placeholders[pid].plotly_chart(fig, use_container_width=True)

# Loop triggers
if st.session_state.running:
    time.sleep(0.45)
    st.rerun()
