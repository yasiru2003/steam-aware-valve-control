"""
app.py

Interactive Streamlit Dashboard for Steam-Aware Tyre Curing Digital Twin.
Supports switching between 5 Pre-Built Schedule Scenarios & Custom CSV Uploads.
"""

import os
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from parameters import DEFAULT_PARAMS, TARGET_TEMP
from press_model import CuringPress
from pid_controller import PIDController
from schedule_reader import load_schedule, is_curing
from controller import ControllerNode

# Page Configuration
st.set_page_config(
    page_title="Steam-Aware Tyre Curing Digital Twin",
    page_icon="♨️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Styling
st.markdown("""
    <style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #FF4B4B, #FF8C00);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1.05rem;
        color: #888888;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: rgba(255, 255, 255, 0.05);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 12px;
        padding: 18px;
        text-align: center;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #00E676;
    }
    .metric-value-warn {
        font-size: 1.8rem;
        font-weight: 700;
        color: #FF5252;
    }
    .metric-label {
        font-size: 0.9rem;
        color: #B0BEC5;
        margin-top: 4px;
    }
    </style>
""", unsafe_allow_html=True)


def run_app_simulation(schedule_entries, num_presses, shift_hours, dt_seconds, kp, ki, kd, steam_budget):
    """Executes Naive vs Smart runs for given schedule entries."""
    press_ids = list(range(1, num_presses + 1))
    shift_duration_s = int(shift_hours * 3600)

    results = {}
    for mode in ["naive", "smart"]:
        presses = {pid: CuringPress(pid) for pid in press_ids}
        pids = {pid: PIDController(kp, ki, kd) for pid in press_ids}
        controller_node = ControllerNode(press_ids, steam_budget=steam_budget)

        log = []
        current_time = 0.0

        while current_time < shift_duration_s:
            curing_status = {
                pid: is_curing(pid, current_time, schedule_entries)
                for pid in press_ids
            }

            raw_demands = {
                pid: pids[pid].compute(TARGET_TEMP, presses[pid].temperature, dt_seconds)
                for pid in press_ids
            }

            press_temps = {pid: presses[pid].temperature for pid in press_ids}

            if mode == "smart":
                final_valves = controller_node.resolve(raw_demands, curing_status, dt_seconds, press_temps)
            else:
                # Human Operator: full PID during curing, 15% cracked open during idle (u=0.15)
                final_valves = {
                    pid: (raw_demands[pid] if curing_status[pid] else 0.15)
                    for pid in press_ids
                }

            step_entry = {"time_seconds": current_time, "time_hours": current_time / 3600.0}
            total_flow_step = 0.0

            for pid in press_ids:
                presses[pid].update(final_valves[pid], curing_status[pid], dt_seconds)
                state = presses[pid].get_state()
                total_flow_step += state["steam_flow_kg_s"]

                for key, value in state.items():
                    step_entry[f"press{pid}_{key}"] = value

            step_entry["total_steam_flow_kg_s"] = total_flow_step
            log.append(step_entry)

            current_time += dt_seconds

        results[mode] = pd.DataFrame(log)

    return results, press_ids


def main():
    st.markdown('<div class="main-header">♨️ Steam-Aware Tyre Curing Digital Twin</div>', unsafe_allow_html=True)
    st.markdown('<div class="sub-header">Multi-Schedule Simulation: Real-Time Peak Smoothing & Schedule Optimization</div>', unsafe_allow_html=True)

    base_dir = os.path.dirname(__file__)
    schedules_dir = os.path.join(base_dir, "schedules")

    # --- Sidebar Controls ---
    st.sidebar.header("🎯 Production Schedule Selection")
    schedule_option = st.sidebar.selectbox(
        "Select Factory Schedule (schedules/)",
        [
            "🔥 Schedule 1: Heavy Overlap Peak Test (schedule_1_peak_overlap.csv)",
            "⏱️ Schedule 2: 15-Min Staggered Schedule (schedule_2_staggered_15m.csv)",
            "📅 Schedule 3: 30-Min Staggered Schedule (schedule_3_staggered_30m.csv)",
            "💤 Schedule 4: Long Idle Break Test (schedule_4_idle_waste_test.csv)",
            "🏭 Schedule 5: 4-Press Heavy Double Shift (schedule_5_full_shift_heavy.csv)",
            "📁 Upload Custom Schedule CSV"
        ]
    )

    if "Schedule 1" in schedule_option:
        file_path = os.path.join(schedules_dir, "schedule_1_peak_overlap.csv")
        st.sidebar.info("Stresses supervisory controller with simultaneous cold-start ramp-ups.")
        schedule_entries = load_schedule(file_path)
        default_num_presses = 3
    elif "Schedule 2" in schedule_option:
        file_path = os.path.join(schedules_dir, "schedule_2_staggered_15m.csv")
        st.sidebar.info("15-minute staggered start times for balanced energy & speed.")
        schedule_entries = load_schedule(file_path)
        default_num_presses = 3
    elif "Schedule 3" in schedule_option:
        file_path = os.path.join(schedules_dir, "schedule_3_staggered_30m.csv")
        st.sidebar.info("30-minute staggered start times for zero ramp-up overlap.")
        schedule_entries = load_schedule(file_path)
        default_num_presses = 3
    elif "Schedule 4" in schedule_option:
        file_path = os.path.join(schedules_dir, "schedule_4_idle_waste_test.csv")
        st.sidebar.info("Features 3.0-hour idle breaks to test idle valve shut-off vs cracked valve leakage.")
        schedule_entries = load_schedule(file_path)
        default_num_presses = 3
    elif "Schedule 5" in schedule_option:
        file_path = os.path.join(schedules_dir, "schedule_5_full_shift_heavy.csv")
        st.sidebar.info("4-press heavy production schedule over a full double shift.")
        schedule_entries = load_schedule(file_path)
        default_num_presses = 4
    else:
        uploaded_file = st.sidebar.file_uploader("Upload Custom CSV Schedule", type=["csv"])
        if uploaded_file is not None:
            schedule_entries = load_schedule(uploaded_file)
        else:
            file_path = os.path.join(schedules_dir, "schedule_1_peak_overlap.csv")
            schedule_entries = load_schedule(file_path)
        default_num_presses = 3

    st.sidebar.subheader("🏭 Factory Parameters")
    num_presses = st.sidebar.slider("Number of Active Presses", min_value=1, max_value=4, value=default_num_presses)
    shift_hours = st.sidebar.slider("Simulation Duration (Hours)", min_value=1.0, max_value=24.0, value=16.0, step=0.5)
    dt_seconds = st.sidebar.select_slider("Timestep Δt (Seconds)", options=[1, 5, 10, 30], value=10)

    st.sidebar.subheader("🕹️ Supervisory Controller")
    steam_budget = st.sidebar.slider("Steam Budget (Press Equivalents)", min_value=0.5, max_value=3.0, value=1.8, step=0.1)

    st.sidebar.subheader("🎯 Local PID Gains")
    kp = st.sidebar.number_input("Kp", value=0.01, format="%.4f")
    ki = st.sidebar.number_input("Ki", value=0.001, format="%.5f")
    kd = st.sidebar.number_input("Kd", value=0.005, format="%.4f")

    # Run Simulation
    results, press_ids = run_app_simulation(
        schedule_entries, num_presses, shift_hours, dt_seconds,
        kp, ki, kd, steam_budget
    )

    df_naive = results["naive"]
    df_smart = results["smart"]

    # Calculate Key Metrics
    naive_total_steam = sum(df_naive[f"press{pid}_total_steam_used_kg"].iloc[-1] for pid in press_ids)
    smart_total_steam = sum(df_smart[f"press{pid}_total_steam_used_kg"].iloc[-1] for pid in press_ids)
    steam_saved_kg = naive_total_steam - smart_total_steam
    steam_saved_pct = (steam_saved_kg / naive_total_steam * 100.0) if naive_total_steam > 0 else 0.0

    naive_peak_flow = df_naive["total_steam_flow_kg_s"].max()
    smart_peak_flow = df_smart["total_steam_flow_kg_s"].max()
    peak_flattened_pct = ((naive_peak_flow - smart_peak_flow) / naive_peak_flow * 100.0) if naive_peak_flow > 0 else 0.0

    # --- KPI Dashboard Row ---
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value-warn">{naive_total_steam:.2f} kg</div>
                <div class="metric-label">Human Operator Steam (u=0.15 idle)</div>
            </div>
        """, unsafe_allow_html=True)

    with col2:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{smart_total_steam:.2f} kg</div>
                <div class="metric-label">Smart Control Steam (u=0.00 idle)</div>
            </div>
        """, unsafe_allow_html=True)

    with col3:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{steam_saved_kg:.2f} kg ({steam_saved_pct:.1f}%)</div>
                <div class="metric-label">Steam Saved</div>
            </div>
        """, unsafe_allow_html=True)

    with col4:
        st.markdown(f"""
            <div class="metric-card">
                <div class="metric-value">{peak_flattened_pct:.1f}%</div>
                <div class="metric-label">Boiler Peak Flattened</div>
            </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # --- Interactive Tabs for Visualizations ---
    tab1, tab2, tab3, tab4 = st.tabs([
        "♨️ Aggregate Steam Flow & Peak Demand Spike",
        "🌡️ Temperature Trajectories",
        "🎛️ Valve Control Signals u(t)",
        "📊 Log Data & Export"
    ])

    with tab1:
        st.subheader("Boiler Line Aggregate Steam Flow Rate (kg/s)")
        st.caption("🔴 Human Operator: Full PID demand during curing + valve left **15% cracked open** (u=0.15) during idle — no budget cap.  "
                   "🟢 Smart Control: Budget-throttled, staggered, auto valve shut-off (u=0.00) during idle.")
        fig_flow = go.Figure()
        fig_flow.add_trace(go.Scatter(
            x=df_naive["time_hours"], y=df_naive["total_steam_flow_kg_s"],
            mode="lines", name="Human Operator (u=0.15 idle, no budget cap)",
            line=dict(color="#FF5252", width=2, dash="dash")
        ))
        fig_flow.add_trace(go.Scatter(
            x=df_smart["time_hours"], y=df_smart["total_steam_flow_kg_s"],
            mode="lines", name="Smart Control (budget-throttled, u=0.00 idle)",
            line=dict(color="#00E676", width=3),
            fill="tozeroy", fillcolor="rgba(0, 230, 118, 0.1)"
        ))
        fig_flow.add_hline(y=steam_budget * 0.01333 / 1.0, line_dash="dash", line_color="#FFD54F", annotation_text=f"Boiler Line Budget Limit ({steam_budget} Press Eq)")
        fig_flow.update_layout(
            xaxis_title="Shift Time (Hours)",
            yaxis_title="Steam Flow Rate (kg/s)",
            template="plotly_dark",
            height=600,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(
                rangeselector=dict(
                    buttons=[
                        dict(count=1, label="1h", step="hour", stepmode="backward"),
                        dict(count=4, label="4h", step="hour", stepmode="backward"),
                        dict(count=8, label="8h", step="hour", stepmode="backward"),
                        dict(label="All", step="all")
                    ],
                    bgcolor="#1E1E1E", activecolor="#FF8C00"
                ),
                rangeslider=dict(visible=True, thickness=0.06),
                type="linear"
            ),
            margin=dict(l=60, r=30, t=80, b=80)
        )
        st.plotly_chart(fig_flow, use_container_width=True)

    with tab2:
        st.subheader("Curing Press Temperature Trajectories (°C)")
        st.caption("Dotted = Human Operator path | Solid = Smart Control path. Both must reach 130°C setpoint for a valid cure.")
        fig_temp = go.Figure()
        colors = ["#29B6F6", "#AB47BC", "#FFA726", "#26A69A", "#EC407A"]

        for idx, pid in enumerate(press_ids):
            color = colors[idx % len(colors)]
            fig_temp.add_trace(go.Scatter(
                x=df_naive["time_hours"], y=df_naive[f"press{pid}_temperature"],
                mode="lines", name=f"Press {pid} — Human Operator",
                line=dict(color=color, width=1.5, dash="dot")
            ))
            fig_temp.add_trace(go.Scatter(
                x=df_smart["time_hours"], y=df_smart[f"press{pid}_temperature"],
                mode="lines", name=f"Press {pid} — Smart Control",
                line=dict(color=color, width=2.5)
            ))

        fig_temp.add_hline(y=TARGET_TEMP, line_dash="dash", line_color="#FFD54F", annotation_text=f"Target Setpoint ({TARGET_TEMP}°C)")
        fig_temp.update_layout(
            xaxis_title="Shift Time (Hours)",
            yaxis_title="Temperature (°C)",
            template="plotly_dark",
            height=650,
            hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            xaxis=dict(
                rangeselector=dict(
                    buttons=[
                        dict(count=1, label="1h", step="hour", stepmode="backward"),
                        dict(count=4, label="4h", step="hour", stepmode="backward"),
                        dict(count=8, label="8h", step="hour", stepmode="backward"),
                        dict(label="All", step="all")
                    ],
                    bgcolor="#1E1E1E", activecolor="#FF8C00"
                ),
                rangeslider=dict(visible=True, thickness=0.06),
                type="linear"
            ),
            yaxis=dict(range=[25, 145]),
            margin=dict(l=60, r=30, t=80, b=80)
        )
        st.plotly_chart(fig_temp, use_container_width=True)

    with tab3:
        st.subheader("Valve Opening Control Signals u(t) [0.0 - 1.0]")
        st.caption("🔴 Dashed = Human Operator (u=0.15 during idle) | 🟢 Solid = Smart Control (u=0.00 auto shut-off during idle)")
        fig_valve = make_subplots(rows=len(press_ids), cols=1, shared_xaxes=True,
                                  subplot_titles=[f"Press {pid} Valve Signal" for pid in press_ids])

        for idx, pid in enumerate(press_ids):
            fig_valve.add_trace(go.Scatter(
                x=df_naive["time_hours"], y=df_naive[f"press{pid}_valve_opening"],
                mode="lines", name=f"Press {pid} — Human Operator",
                line=dict(color="#FF5252", width=1.5, dash="dash")
            ), row=idx+1, col=1)

            fig_valve.add_trace(go.Scatter(
                x=df_smart["time_hours"], y=df_smart[f"press{pid}_valve_opening"],
                mode="lines", name=f"Press {pid} — Smart Control",
                line=dict(color="#00E676", width=2)
            ), row=idx+1, col=1)

        fig_valve.update_layout(
            template="plotly_dark",
            height=380 * len(press_ids),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.01, xanchor="right", x=1),
            hovermode="x unified",
            margin=dict(l=60, r=30, t=60, b=60)
        )
        fig_valve.update_xaxes(title_text="Shift Time (Hours)", row=len(press_ids), col=1)
        fig_valve.update_yaxes(title_text="Valve u(t)", range=[-0.05, 1.1])
        st.plotly_chart(fig_valve, use_container_width=True)

    with tab4:
        st.subheader("Simulation Log Inspection & Download")
        st.dataframe(df_smart.style.format(precision=3), use_container_width=True)


if __name__ == "__main__":
    main()
