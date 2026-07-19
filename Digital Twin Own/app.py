import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

from parameters import DEFAULT_PARAMS
from simulation import run_multi_press_simulation

# Set up page styling and layout
st.set_page_config(
    page_title="Multi-Press Tyre Curing Digital Twin",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Clean, professional high-contrast styling
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

.header-box {
    background-color: #0f172a;
    border: 1px solid #1e293b;
    border-radius: 8px;
    padding: 24px;
    margin-bottom: 24px;
}

.header-title {
    color: #f8fafc;
    font-size: 2.1rem;
    font-weight: 700;
    margin-bottom: 6px;
}

.header-subtitle {
    color: #94a3b8;
    font-size: 1.0rem;
    font-weight: 400;
}

.metric-container {
    background-color: #0f172a;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 18px;
    text-align: center;
}

.metric-label {
    font-size: 0.8rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-weight: 600;
    margin-bottom: 6px;
}

.metric-val {
    font-size: 1.9rem;
    font-weight: 700;
    color: #f8fafc;
}

.metric-sub {
    font-size: 0.85rem;
    color: #38bdf8;
    font-weight: 500;
    margin-top: 4px;
}

.stage-badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.75rem;
    font-weight: 600;
}

.stage-heating { background-color: #7f1d1d; color: #fca5a5; }
.stage-holding { background-color: #14532d; color: #86efac; }
.stage-cooling { background-color: #1e3a8a; color: #93c5fd; }
.stage-idle { background-color: #334155; color: #cbd5e1; }
</style>
""", unsafe_allow_html=True)

# Main Application Header
st.markdown("""
<div class="header-box">
    <div class="header-title">Multi-Press Solid Tyre Curing Digital Twin</div>
    <div class="header-subtitle">Schedule-Aware Valve Control, Peak Demand Demand Smoothing & Boiler Energy Optimization.</div>
</div>
""", unsafe_allow_html=True)

# ----------------- SIDEBAR CONTROLS -----------------
st.sidebar.title("Simulation & Schedule Setup")

# Schedule Feed File Selector
st.sidebar.subheader("1. Production Schedule Feed")
schedule_source = st.sidebar.radio(
    "Schedule Source",
    options=["Default 4-Press Schedule", "Upload Custom CSV Schedule"],
    index=0
)

schedule_file = "Digital Twin Own/sample_schedule.csv"

if schedule_source == "Upload Custom CSV Schedule":
    uploaded_file = st.sidebar.file_uploader("Upload Schedule CSV", type=["csv"])
    if uploaded_file is not None:
        schedule_file = uploaded_file
    else:
        st.sidebar.info("Using default schedule until custom CSV is uploaded.")

# Physical Parameters Expander
with st.sidebar.expander("2. Press Physical Parameters", expanded=False):
    mass = st.number_input("Press Mould Mass (kg)", min_value=50.0, max_value=2000.0, value=300.0, step=25.0)
    ua_steam = st.slider("Steam Conductance (UA_steam, W/K)", min_value=100.0, max_value=1000.0, value=DEFAULT_PARAMS["UA_steam"], step=25.0)
    h_loss = st.slider("Heat Loss Coeff (h_loss, W/m²·K)", min_value=2.0, max_value=50.0, value=DEFAULT_PARAMS["h_loss"], step=1.0)
    t_sat = st.slider("Steam Saturation Temp (T_sat, °C)", min_value=100.0, max_value=200.0, value=DEFAULT_PARAMS["T_sat"], step=1.0)
    t_amb = st.slider("Ambient Room Temp (T_amb, °C)", min_value=10.0, max_value=50.0, value=DEFAULT_PARAMS["T_ambient"], step=1.0)

# Control Logic Expander
with st.sidebar.expander("3. Control & Boiler Parameters", expanded=False):
    max_boiler_flow = st.slider("Max Boiler Limit (kg/s)", min_value=0.02, max_value=0.20, value=0.06, step=0.005)
    kp = st.slider("Kp (Proportional)", min_value=0.001, max_value=0.200, value=0.02, step=0.001, format="%.3f")
    ki = st.slider("Ki (Integral)", min_value=0.00000, max_value=0.00200, value=0.00015, step=0.00001, format="%.5f")
    kd = st.slider("Kd (Derivative)", min_value=0.000, max_value=0.100, value=0.01, step=0.001, format="%.3f")
    sim_hours = st.slider("Simulation Hours", min_value=1.0, max_value=24.0, value=12.0, step=0.5)

custom_params = {
    "UA_steam": ua_steam,
    "h_loss": h_loss,
    "T_sat": t_sat,
    "T_ambient": t_amb,
}

# ----------------- SIMULATION EXECUTION -----------------
# 1. Conventional Control Run (Simultaneous Peaks + 15% Idle Crack)
t_c, hist_c, flow_c, total_c, peak_c, df_sched = run_multi_press_simulation(
    schedule_filepath=schedule_file,
    mass=mass,
    params=custom_params,
    hours=sim_hours,
    dt=5.0,
    kp=kp, ki=ki, kd=kd,
    smart_idle_shutoff=False,
    enable_peak_smoothing=False,
    max_boiler_flow_kg_s=max_boiler_flow
)

# 2. Smart Managed Control Run (Staggered Peak Smoothing + 0% Idle Shutoff)
t_s, hist_s, flow_s, total_s, peak_s, _ = run_multi_press_simulation(
    schedule_filepath=schedule_file,
    mass=mass,
    params=custom_params,
    hours=sim_hours,
    dt=5.0,
    kp=kp, ki=ki, kd=kd,
    smart_idle_shutoff=True,
    enable_peak_smoothing=True,
    max_boiler_flow_kg_s=max_boiler_flow
)

hours_axis = t_c / 3600.0
steam_saved = total_c - total_s
pct_saved = (steam_saved / total_c) * 100.0 if total_c > 0 else 0.0
peak_flattened_pct = ((peak_c - peak_s) / peak_c) * 100.0 if peak_c > 0 else 0.0

# ----------------- KPI METRICS DISPLAY -----------------
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-label">Conventional Steam</div>
        <div class="metric-val">{total_c:.2f} <span style="font-size:1.0rem">kg</span></div>
        <div class="metric-sub" style="color:#ef4444">15% Idle Waste</div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-label">Smart Managed Steam</div>
        <div class="metric-val">{total_s:.2f} <span style="font-size:1.0rem">kg</span></div>
        <div class="metric-sub" style="color:#38bdf8">0% Auto Shutoff</div>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-label">Total Steam Saved</div>
        <div class="metric-val">{steam_saved:.2f} <span style="font-size:1.0rem">kg</span></div>
        <div class="metric-sub" style="color:#34d399">-{pct_saved:.1f}% Consumption</div>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-label">Boiler Peak Flattened</div>
        <div class="metric-val">{peak_s:.4f} <span style="font-size:1.0rem">kg/s</span></div>
        <div class="metric-sub" style="color:#a78bfa">-{peak_flattened_pct:.1f}% Peak Spike</div>
    </div>
    """, unsafe_allow_html=True)

st.write("")

# ----------------- COMBINED BOILER PEAK DEMAND CHART -----------------
st.subheader("Boiler Total Steam Demand (Problem 1: Peak Demand Flattening)")
st.markdown("Demonstrates how staggered ramp-up logic caps simultaneous warm-up peaks across presses to protect boiler pressure.")

fig_boiler = go.Figure()
fig_boiler.add_hline(
    y=max_boiler_flow,
    line_dash="dot",
    line_color="#f59e0b",
    annotation_text="Boiler Max Capacity Threshold",
    annotation_position="bottom right"
)
fig_boiler.add_trace(go.Scatter(
    x=hours_axis, y=flow_c,
    mode='lines',
    name='Conventional Unmanaged (Demand Peak Spike)',
    line=dict(color='#ef4444', width=2, dash='dash')
))
fig_boiler.add_trace(go.Scatter(
    x=hours_axis, y=flow_s,
    mode='lines',
    name='Smart Schedule-Aware (Peak Demand Smoothed)',
    line=dict(color='#38bdf8', width=3)
))
fig_boiler.update_layout(
    template="plotly_dark",
    xaxis_title="Time (hours)",
    yaxis_title="Total Boiler Steam Flow Rate (kg/s)",
    margin=dict(l=40, r=40, t=20, b=40),
    legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    plot_bgcolor='rgba(0,0,0,0)',
    paper_bgcolor='rgba(0,0,0,0)'
)
st.plotly_chart(fig_boiler, use_container_width=True)

st.write("---")

# ----------------- INDIVIDUAL PRESS MULTI-TAB VIEWS -----------------
st.subheader("Multi-Press Digital Twin Status & Stage Tracking")
st.markdown("Select a press tab below to inspect its temperature profile, valve signal, and explicit cure stages (`heating`, `holding`, `cooling`, `idle`).")

press_ids = list(hist_s.keys())
tabs = st.tabs([f"Press: {p_id}" for p_id in press_ids])

for idx, p_id in enumerate(press_ids):
    with tabs[idx]:
        col_left, col_right = st.columns([1, 1])

        # Current State Information
        current_stage = hist_s[p_id]["stage"][-1]
        current_temp = hist_s[p_id]["T"][-1]
        current_valve = hist_s[p_id]["u"][-1]

        st.markdown(f"**Live Press Status:** Stage: `{current_stage.upper()}` | Current Temp: `{current_temp:.2f} °C` | Valve Opening: `{current_valve * 100:.1f} %`")

        with col_left:
            st.markdown("#### Temperature Profile (°C)")
            fig_p_temp = go.Figure()
            fig_p_temp.add_hline(y=DEFAULT_PARAMS["T_target"], line_dash="dot", line_color="#94a3b8", annotation_text="Target Setpoint (130°C)")
            fig_p_temp.add_trace(go.Scatter(x=hours_axis, y=hist_c[p_id]["T"], mode='lines', name='Conventional', line=dict(color='#ef4444', width=2, dash='dash')))
            fig_p_temp.add_trace(go.Scatter(x=hours_axis, y=hist_s[p_id]["T"], mode='lines', name='Smart Control', line=dict(color='#818cf8', width=3)))
            fig_p_temp.update_layout(
                template="plotly_dark",
                xaxis_title="Time (hours)",
                yaxis_title="Temperature (°C)",
                margin=dict(l=30, r=30, t=20, b=30),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_p_temp, use_container_width=True)

        with col_right:
            st.markdown("#### Valve Control Signal (u)")
            fig_p_valve = go.Figure()
            fig_p_valve.add_trace(go.Scatter(x=hours_axis, y=hist_c[p_id]["u"], mode='lines', name='Conventional (15% Idle Crack)', line=dict(color='#ef4444', width=2, dash='dash')))
            fig_p_valve.add_trace(go.Scatter(x=hours_axis, y=hist_s[p_id]["u"], mode='lines', name='Smart Control (0% Auto Shutoff)', line=dict(color='#34d399', width=3)))
            fig_p_valve.update_layout(
                template="plotly_dark",
                xaxis_title="Time (hours)",
                yaxis_title="Valve Ratio (0.0 to 1.0)",
                margin=dict(l=30, r=30, t=20, b=30),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)'
            )
            st.plotly_chart(fig_p_valve, use_container_width=True)

st.write("---")

# ----------------- SCHEDULE FEED TABLE & EXPORT -----------------
with st.expander("Parsed Production Schedule Feed Data"):
    st.markdown("Here is the parsed production schedule loaded into the Digital Twin engine:")
    st.dataframe(df_sched, use_container_width=True)

    csv_data = df_sched.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Schedule CSV Template",
        data=csv_data,
        file_name="production_schedule_template.csv",
        mime="text/csv"
    )
