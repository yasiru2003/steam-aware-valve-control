import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from simulation import PressParams, run_simulation

# Set up page styling and layout
st.set_page_config(
    page_title="Tyre Curing Press Digital Twin",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded"
)

# Premium dark theme and styling injection
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');

/* Apply custom font across the app */
html, body, [class*="css"] {
    font-family: 'Outfit', sans-serif;
}

/* Custom header gradient styling */
.header-container {
    background: linear-gradient(135deg, #1e1b4b 0%, #311042 100%);
    border-radius: 16px;
    padding: 30px;
    margin-bottom: 25px;
    border: 1px solid #4338ca;
    box-shadow: 0 10px 30px rgba(67, 56, 202, 0.15);
}

.header-title {
    color: #f8fafc;
    font-size: 2.5rem;
    font-weight: 700;
    margin-bottom: 8px;
    background: linear-gradient(90deg, #a5b4fc, #f472b6);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}

.header-subtitle {
    color: #cbd5e1;
    font-size: 1.1rem;
    font-weight: 400;
}

/* Custom premium KPI card */
.kpi-card {
    background: linear-gradient(135deg, #0f172a 0%, #1e293b 100%);
    border: 1px solid #334155;
    border-radius: 14px;
    padding: 24px;
    text-align: center;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.kpi-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 24px rgba(67, 56, 202, 0.12);
    border-color: #6366f1;
}

.kpi-title {
    font-size: 0.85rem;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-weight: 600;
    margin-bottom: 10px;
}

.kpi-value {
    font-size: 2.2rem;
    font-weight: 700;
    color: #f8fafc;
    margin-bottom: 4px;
}

.kpi-unit {
    font-size: 1rem;
    font-weight: 500;
    color: #cbd5e1;
}

.kpi-badge {
    display: inline-block;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 0.8rem;
    font-weight: 600;
    margin-top: 10px;
}

.badge-green {
    background-color: rgba(16, 185, 129, 0.15);
    color: #34d399;
    border: 1px solid rgba(16, 185, 129, 0.3);
}

.badge-blue {
    background-color: rgba(59, 130, 246, 0.15);
    color: #60a5fa;
    border: 1px solid rgba(59, 130, 246, 0.3);
}

.badge-red {
    background-color: rgba(239, 68, 68, 0.15);
    color: #f87171;
    border: 1px solid rgba(239, 68, 68, 0.3);
}
</style>
""", unsafe_allow_html=True)

# Application Header
st.markdown("""
<div class="header-container">
    <div class="header-title">Tyre Curing Press Digital Twin</div>
    <div class="header-subtitle">Analyze real-time simulation and optimization of a single solid tyre curing press. Compare normal control vs. schedule-aware smart valve control.</div>
</div>
""", unsafe_allow_html=True)

# ----------------- SIDEBAR PARAMETERS -----------------
st.sidebar.title("Parameters Configuration")

# Expander for Physical Press Parameters
with st.sidebar.expander("Press Physical Parameters", expanded=True):
    ua_steam = st.slider("UA_steam (Steam Conductance, W/K)", min_value=100.0, max_value=1000.0, value=450.0, step=10.0)
    ua_amb = st.slider("UA_amb (Loss Conductance, W/K)", min_value=5.0, max_value=100.0, value=25.0, step=1.0)
    m_cp = st.number_input("m_cp (Thermal Mass, J/K)", min_value=50000.0, max_value=500000.0, value=180000.0, step=10000.0)
    t_sat = st.slider("T_sat (Steam Temp, °C)", min_value=100.0, max_value=200.0, value=152.0, step=1.0)
    t_amb = st.slider("T_amb (Ambient Temp, °C)", min_value=10.0, max_value=50.0, value=30.0, step=1.0)
    h_fg = st.number_input("h_fg (Latent Heat, J/kg)", min_value=1500000.0, max_value=2500000.0, value=2114000.0, step=10000.0)

# Expander for PID Settings
with st.sidebar.expander("PID Controller Gains", expanded=True):
    kp = st.slider("Kp (Proportional)", min_value=0.001, max_value=0.200, value=0.02, step=0.001, format="%.3f")
    ki = st.slider("Ki (Integral)", min_value=0.00000, max_value=0.00200, value=0.00015, step=0.00001, format="%.5f")
    kd = st.slider("Kd (Derivative)", min_value=0.000, max_value=0.100, value=0.01, step=0.001, format="%.3f")

# Expander for Curing & Idle Schedule
with st.sidebar.expander("Curing & Idle Schedule", expanded=True):
    cure_temp = st.slider("Target Curing Temp (°C)", min_value=100.0, max_value=150.0, value=130.0, step=1.0)
    cure_time_h = st.slider("Curing Duration (hours)", min_value=1.0, max_value=12.0, value=6.5, step=0.5)
    sim_hours = st.slider("Simulation Duration (hours)", min_value=1.0, max_value=24.0, value=10.0, step=0.5)
    gap_start_h = st.slider("Idle Gap Start (hours)", min_value=0.0, max_value=sim_hours, value=7.0, step=0.1)
    gap_dur_h = st.slider("Idle Gap Duration (hours)", min_value=0.0, max_value=sim_hours - gap_start_h, value=1.5, step=0.1)
    dt_sec = st.slider("Simulation Step dt (seconds)", min_value=1.0, max_value=60.0, value=5.0, step=1.0)

# Expander for Animation Settings
with st.sidebar.expander("Visualization Settings", expanded=True):
    animate = st.checkbox("Animate Live Simulation", value=True)
    animation_speed = st.slider("Animation Speed (Steps/sec)", min_value=10, max_value=60, value=25)

# Create PressParams
params = PressParams(
    UA_steam=ua_steam,
    UA_amb=ua_amb,
    m_cp=m_cp,
    T_sat=t_sat,
    T_amb=t_amb,
    h_fg=h_fg
)

# ----------------- SIMULATION RUNS -----------------
# Run Smart Simulation
t_s, T_s, u_s, flow_s, stages_s, total_s = run_simulation(
    params=params,
    cure_temp=cure_temp,
    cure_time_s=cure_time_h * 3600,
    hours=sim_hours,
    dt=dt_sec,
    gap_start_s=gap_start_h * 3600,
    gap_duration_s=gap_dur_h * 3600,
    kp=kp,
    ki=ki,
    kd=kd,
    smart_idle_shutoff=True
)

# Run Naive Simulation
t_n, T_n, u_n, flow_n, stages_n, total_n = run_simulation(
    params=params,
    cure_temp=cure_temp,
    cure_time_s=cure_time_h * 3600,
    hours=sim_hours,
    dt=dt_sec,
    gap_start_s=gap_start_h * 3600,
    gap_duration_s=gap_dur_h * 3600,
    kp=kp,
    ki=ki,
    kd=kd,
    smart_idle_shutoff=False
)

# Convert times to hours for display
hours_s = t_s / 3600
hours_n = t_n / 3600

# Cumulative steam calculations
cum_steam_s = np.cumsum(flow_s) * dt_sec
cum_steam_n = np.cumsum(flow_n) * dt_sec

# Calculate saved metrics
steam_saved = total_n - total_s
pct_saved = (steam_saved / total_n) * 100 if total_n > 0 else 0

# ----------------- MAIN LAYOUT -----------------

# Control button container
btn_col1, btn_col2 = st.columns([1, 3])
with btn_col1:
    run_btn = st.button("Start Curing Simulation", type="primary", use_container_width=True)
with btn_col2:
    if run_btn and animate:
        st.info("Animating simulation in real-time. Please wait.")
    else:
        st.success("Simulation loaded. Adjust settings in the sidebar or click 'Start Curing Simulation' to animate.")

st.write("")

# Placeholders for metrics cards and charts
kpi_placeholder = st.empty()
st.write("---")

chart_col1, chart_col2 = st.columns(2)
with chart_col1:
    st.subheader("Press Temperature Profile")
    chart_placeholder1 = st.empty()

with chart_col2:
    st.subheader("Valve Opening (Control Signal)")
    chart_placeholder2 = st.empty()

st.subheader("Cumulative Steam Consumption")
chart_placeholder3 = st.empty()

st.write("---")

import time

# Function to render charts and KPIs at a specific index limit (for animation)
def render_dashboard_state(idx):
    # Calculate intermediate metrics
    flow_s_slice = flow_s[:idx]
    flow_n_slice = flow_n[:idx]
    total_s_temp = np.sum(flow_s_slice) * dt_sec
    total_n_temp = np.sum(flow_n_slice) * dt_sec
    steam_saved_temp = total_n_temp - total_s_temp
    pct_saved_temp = (steam_saved_temp / total_n_temp) * 100 if total_n_temp > 0 else 0
    
    # Update KPI cards
    kpi_placeholder.markdown(f"""
    <div style="display: flex; gap: 1rem; width: 100%;">
        <div class="kpi-card" style="flex: 1;">
            <div class="kpi-title">Naive Control (Default)</div>
            <div class="kpi-value">{total_n_temp:.2f} <span class="kpi-unit">kg</span></div>
            <div class="kpi-badge badge-red">Valve stays cracked at 15%</div>
        </div>
        <div class="kpi-card" style="flex: 1;">
            <div class="kpi-title">Smart Idle Shutoff</div>
            <div class="kpi-value">{total_s_temp:.2f} <span class="kpi-unit">kg</span></div>
            <div class="kpi-badge badge-blue">Valve fully closed during idle</div>
        </div>
        <div class="kpi-card" style="flex: 1;">
            <div class="kpi-title">Steam Savings</div>
            <div class="kpi-value">{steam_saved_temp:.2f} <span class="kpi-unit">kg</span></div>
            <div class="kpi-badge badge-green">-{pct_saved_temp:.1f}% Consumption</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Temperature profile chart
    fig_temp = go.Figure()
    fig_temp.add_hline(
        y=cure_temp, 
        line_dash="dot", 
        line_color="#94a3b8", 
        annotation_text="Target Curing Temp", 
        annotation_position="bottom right"
    )
    fig_temp.add_trace(go.Scatter(
        x=hours_n[:idx], y=T_n[:idx],
        mode='lines',
        name='Naive Control',
        line=dict(color='#f87171', width=2, dash='dash')
    ))
    fig_temp.add_trace(go.Scatter(
        x=hours_s[:idx], y=T_s[:idx],
        mode='lines',
        name='Smart Control',
        line=dict(color='#6366f1', width=3)
    ))
    fig_temp.update_layout(
        template="plotly_dark",
        xaxis_title="Time (hours)",
        yaxis_title="Press Temperature (°C)",
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(range=[0, sim_hours]),
        yaxis=dict(range=[t_amb - 5, max(T_n.max(), T_s.max()) + 5])
    )
    chart_placeholder1.plotly_chart(fig_temp, use_container_width=True)

    # Valve opening chart
    fig_valve = go.Figure()
    fig_valve.add_trace(go.Scatter(
        x=hours_n[:idx], y=u_n[:idx],
        mode='lines',
        name='Naive Control',
        line=dict(color='#f87171', width=2, dash='dash')
    ))
    fig_valve.add_trace(go.Scatter(
        x=hours_s[:idx], y=u_s[:idx],
        mode='lines',
        name='Smart Control',
        line=dict(color='#6366f1', width=3)
    ))
    fig_valve.update_layout(
        template="plotly_dark",
        xaxis_title="Time (hours)",
        yaxis_title="Valve Opening Ratio (0 to 1)",
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(range=[0, sim_hours]),
        yaxis=dict(range=[-0.05, 1.05])
    )
    chart_placeholder2.plotly_chart(fig_valve, use_container_width=True)

    # Cumulative steam usage chart
    fig_steam = go.Figure()
    fig_steam.add_trace(go.Scatter(
        x=hours_n[:idx], y=cum_steam_n[:idx],
        mode='lines',
        name='Naive Cumulative Steam',
        line=dict(color='#f87171', width=2, dash='dash')
    ))
    fig_steam.add_trace(go.Scatter(
        x=hours_s[:idx], y=cum_steam_s[:idx],
        mode='lines',
        name='Smart Cumulative Steam',
        line=dict(color='#10b981', width=3)
    ))
    fig_steam.update_layout(
        template="plotly_dark",
        xaxis_title="Time (hours)",
        yaxis_title="Cumulative Steam (kg)",
        margin=dict(l=40, r=40, t=20, b=40),
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)',
        xaxis=dict(range=[0, sim_hours]),
        yaxis=dict(range=[-2, max(cum_steam_n.max(), cum_steam_s.max()) + 5])
    )
    chart_placeholder3.plotly_chart(fig_steam, use_container_width=True)

# Run animation or render static results
if run_btn and animate:
    n_frames = 30
    step_size = len(T_s) // n_frames
    for frame in range(1, n_frames + 1):
        idx = frame * step_size
        if idx > len(T_s):
            idx = len(T_s)
        render_dashboard_state(idx)
        time.sleep(1.0 / animation_speed)
    # Ensure final state is perfectly rendered
    render_dashboard_state(len(T_s))
else:
    # Render static final state immediately
    render_dashboard_state(len(T_s))

# Expandable simulation data logs
with st.expander("Detailed Simulation Logs"):
    st.markdown("Here is the dynamic time-step data generated by the physical models.")
    
    # Construct a dataframe for review/download
    log_df = pd.DataFrame({
        "Time (seconds)": t_s,
        "Time (hours)": hours_s,
        "Smart Stage": stages_s,
        "Smart Temp (°C)": T_s,
        "Smart Valve Ratio": u_s,
        "Smart Steam (kg)": cum_steam_s,
        "Naive Stage": stages_n,
        "Naive Temp (°C)": T_n,
        "Naive Valve Ratio": u_n,
        "Naive Steam (kg)": cum_steam_n,
    })
    
    st.dataframe(log_df.style.format(precision=3), use_container_width=True)
    
    csv_data = log_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="Download Simulation Data as CSV",
        data=csv_data,
        file_name="curing_press_simulation_data.csv",
        mime="text/csv",
    )
