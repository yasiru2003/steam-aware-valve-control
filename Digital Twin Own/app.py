"""
app.py

Interactive Streamlit Dashboard for Steam-Aware Tyre Curing Digital Twin.
Supports switching between 5 Pre-Built Schedule Scenarios & Custom CSV Uploads.
"""

import os
from collections import defaultdict

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from parameters import DEFAULT_PARAMS, TARGET_TEMP
from press_model import CuringPress
from pid_controller import PIDController
from schedule_reader import load_schedule, is_curing
from controller import ControllerNode
from simulation import run_simulation, total_steam_used

# ---------------------------------------------------------------------------
# Page Config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Tyre Curing Digital Twin",
    page_icon="♨️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Clean Modern CSS Design System
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* Header Container */
.header-container {
    padding: 8px 0 16px 0;
    border-bottom: 1px solid #334155;
    margin-bottom: 20px;
}
.header-title {
    font-size: 1.6rem;
    font-weight: 700;
    color: #F8FAFC;
    letter-spacing: -0.02em;
    margin: 0;
}

/* Metric Cards */
.metric-box {
    background-color: #1E293B;
    border: 1px solid #334155;
    border-radius: 8px;
    padding: 16px;
}
.metric-box-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    color: #94A3B8;
    margin-bottom: 6px;
}
.metric-box-val {
    font-size: 1.45rem;
    font-weight: 700;
    line-height: 1.2;
}
.metric-box-sub {
    font-size: 0.8rem;
    color: #94A3B8;
    margin-top: 4px;
}

/* Color Classes */
.text-emerald { color: #10B981 !important; }
.text-rose    { color: #F43F5E !important; }
.text-amber   { color: #F59E0B !important; }
.text-blue    { color: #3B82F6 !important; }
.text-slate   { color: #F8FAFC !important; }

/* Subheaders */
.section-title {
    font-size: 1.05rem;
    font-weight: 600;
    color: #F8FAFC;
    margin: 16px 0 10px 0;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Simple Slate Color Palette
# ---------------------------------------------------------------------------
HUMAN_COLOR = "#F43F5E"   # Muted Rose Red
SMART_COLOR = "#10B981"   # Clean Emerald Green
LIMIT_COLOR = "#F59E0B"   # Soft Amber
PRESS_COLORS = ["#3B82F6", "#8B5CF6", "#F59E0B", "#10B981"]  # Muted Blue, Violet, Amber, Emerald


def fmt_h(h: float) -> str:
    """Convert decimal hours to both decimal and 'Xh Ym' format e.g. '0.25h (0h 15m)'."""
    total_mins = int(round(h * 60))
    hh, mm = divmod(total_mins, 60)
    time_str = f"{hh}h {mm:02d}m" if mm else f"{hh}h"
    if mm != 0:
        return f"{h:.2f}h ({time_str})"
    return f"{h:.1f}h ({time_str})"


def run_app_simulation(schedule_entries, num_presses, shift_hours, dt_seconds, kp, ki, kd, steam_budget):
    press_ids = list(range(1, num_presses + 1))
    shift_duration_s = int(shift_hours * 3600)
    results = {}
    for mode in ["naive", "smart"]:
        presses = {pid: CuringPress(pid) for pid in press_ids}
        pid_ctrl = {pid: PIDController(kp, ki, kd) for pid in press_ids}
        node = ControllerNode(press_ids, steam_budget=steam_budget)
        log = []
        t = 0.0
        while t < shift_duration_s:
            cs = {pid: is_curing(pid, t, schedule_entries) for pid in press_ids}
            rd = {pid: pid_ctrl[pid].compute(TARGET_TEMP, presses[pid].temperature, dt_seconds) for pid in press_ids}
            pt = {pid: presses[pid].temperature for pid in press_ids}
            if mode == "smart":
                fv = node.resolve(rd, cs, dt_seconds, pt)
            else:
                fv = {pid: (rd[pid] if cs[pid] else 0.15) for pid in press_ids}
            entry = {"time_seconds": t, "time_hours": t / 3600.0}
            tf = 0.0
            for pid in press_ids:
                presses[pid].update(fv[pid], cs[pid], dt_seconds)
                state = presses[pid].get_state()
                tf += state["steam_flow_kg_s"]
                for k, v in state.items():
                    entry[f"press{pid}_{k}"] = v
            entry["total_steam_flow_kg_s"] = tf
            log.append(entry)
            t += dt_seconds
        results[mode] = pd.DataFrame(log)
    return results, press_ids


def build_gantt(schedule_entries, press_ids):
    """
    Build a hand-verified, dynamic Gantt chart from schedule entries.
    Accurately renders Batch 1, Idle Gap (if present), and Batch 2 for all 5 schedules.
    """
    fig = go.Figure()
    all_press_ids = set()

    for idx, e in enumerate(schedule_entries):
        raw = str(e.get("press_id", "")).replace("Press_", "").strip()
        try:
            pid = int(raw)
        except ValueError:
            pid = raw
        all_press_ids.add(pid)

        color = PRESS_COLORS[(pid - 1) if isinstance(pid, int) else idx % len(PRESS_COLORS)]

        start_h    = float(e.get("start_s", 0.0)) / 3600.0
        cure_dur_h = float(e.get("cure_dur_s", 23400.0)) / 3600.0
        gap_start_h= float(e.get("gap_start_s", 999999.0)) / 3600.0
        gap_dur_h  = float(e.get("gap_dur_s", 0.0)) / 3600.0

        if gap_start_h < 9000 and gap_dur_h > 0:
            # Batch 1
            b1_start, b1_end = start_h, gap_start_h
            fig.add_trace(go.Bar(
                x=[b1_end - b1_start], y=[f"Press {pid}"], base=[b1_start],
                orientation="h",
                name=f"Press {pid} (Batch 1)",
                legendgroup=f"Press {pid}",
                showlegend=True,
                marker=dict(color=color, opacity=0.9, line=dict(color="rgba(255,255,255,0.4)", width=1)),
                hovertemplate=(
                    f"<b>Press {pid} — Batch 1</b><br>"
                    f"Start:    {fmt_h(b1_start)}<br>"
                    f"End:      {fmt_h(b1_end)}<br>"
                    f"Duration: {fmt_h(b1_end - b1_start)}<extra></extra>"
                )
            ))

            # Idle Gap (Subtle Slate Muted)
            gap_start, gap_end = gap_start_h, gap_start_h + gap_dur_h
            fig.add_trace(go.Bar(
                x=[gap_end - gap_start], y=[f"Press {pid}"], base=[gap_start],
                orientation="h",
                name="Idle Gap (15% Leak)" if idx == 0 else None,
                showlegend=(idx == 0),
                marker=dict(color="rgba(148, 163, 184, 0.2)", line=dict(color="#64748B", width=1)),
                hovertemplate=(
                    f"<b>Press {pid} — Idle Gap</b><br>"
                    f"Start:    {fmt_h(gap_start)}<br>"
                    f"End:      {fmt_h(gap_end)}<br>"
                    f"Duration: {fmt_h(gap_end - gap_start)}<extra></extra>"
                )
            ))

            # Batch 2
            b2_start, b2_end = gap_end, gap_end + cure_dur_h
            fig.add_trace(go.Bar(
                x=[b2_end - b2_start], y=[f"Press {pid}"], base=[b2_start],
                orientation="h",
                name=f"Press {pid} (Batch 2)",
                legendgroup=f"Press {pid}",
                showlegend=False,
                marker=dict(color=color, opacity=0.75, line=dict(color="rgba(255,255,255,0.4)", width=1)),
                hovertemplate=(
                    f"<b>Press {pid} — Batch 2</b><br>"
                    f"Start:    {fmt_h(b2_start)}<br>"
                    f"End:      {fmt_h(b2_end)}<br>"
                    f"Duration: {fmt_h(b2_end - b2_start)}<extra></extra>"
                )
            ))
        else:
            # Single Batch
            b_start, b_end = start_h, start_h + cure_dur_h
            fig.add_trace(go.Bar(
                x=[b_end - b_start], y=[f"Press {pid}"], base=[b_start],
                orientation="h",
                name=f"Press {pid}",
                showlegend=True,
                marker=dict(color=color, opacity=0.9, line=dict(color="rgba(255,255,255,0.4)", width=1)),
                hovertemplate=(
                    f"<b>Press {pid} — Curing Batch</b><br>"
                    f"Start:    {fmt_h(b_start)}<br>"
                    f"End:      {fmt_h(b_end)}<br>"
                    f"Duration: {fmt_h(b_end - b_start)}<extra></extra>"
                )
            ))

    sorted_pids = sorted(list(all_press_ids))

    # Reference line for 6.5h Cure Hold
    cure_h = DEFAULT_PARAMS["cure_time_s"] / 3600.0
    fig.add_vline(
        x=cure_h, line_dash="dash", line_color=LIMIT_COLOR, line_width=1.5,
        annotation_text=f"Cure Hold ({fmt_h(cure_h)})",
        annotation_font=dict(color=LIMIT_COLOR, size=11),
        annotation_position="top right"
    )

    # Calculate x-axis bounds
    max_h = 16.0
    for e in schedule_entries:
        s_h = float(e.get("start_s", 0.0)) / 3600.0
        d_h = float(e.get("cure_dur_s", 23400.0)) / 3600.0
        g_s = float(e.get("gap_start_s", 999999.0)) / 3600.0
        g_d = float(e.get("gap_dur_s", 0.0)) / 3600.0
        if g_s < 9000 and g_d > 0:
            max_h = max(max_h, g_s + g_d + d_h)
        else:
            max_h = max(max_h, s_h + d_h)

    tick_vals = [i * 0.5 for i in range(int(max_h / 0.5) + 3)]
    tick_text = [f"{v:.1f}h ({fmt_h(v).split('(')[-1][:-1]})" if v % 1 != 0 else f"{int(v)}h" for v in tick_vals]

    fig.update_layout(
        barmode="overlay",
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15, 23, 42, 0.4)",
        height=130 + 55 * len(sorted_pids),
        font=dict(family="Inter, sans-serif", color="#F8FAFC"),
        xaxis=dict(
            title="Shift Time (Hours)",
            tickvals=tick_vals, ticktext=tick_text, tickangle=-35,
            gridcolor="rgba(255,255,255,0.06)",
            range=[-0.15, max_h + 0.5],
        ),
        yaxis=dict(
            title=None,
            categoryorder="array",
            categoryarray=[f"Press {pid}" for pid in reversed(sorted_pids)],
            tickfont=dict(size=12, color="#F8FAFC"),
            gridcolor="rgba(255,255,255,0.05)",
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.05, xanchor="left", x=0, font=dict(size=11, color="#F8FAFC")),
        margin=dict(l=80, r=30, t=40, b=80),
        hovermode="closest",
        dragmode="pan",
    )
    fig.update_xaxes(fixedrange=False)
    return fig, sorted_pids


# ---------------------------------------------------------------------------
# Main Application
# ---------------------------------------------------------------------------
def main():
    base_dir = os.path.dirname(__file__)
    schedules_dir = os.path.join(base_dir, "schedules")

    # -----------------------------------------------------------------------
    # Sidebar Navigation & Settings
    # -----------------------------------------------------------------------
    with st.sidebar:
        st.subheader("Control Settings")

        schedule_option = st.selectbox(
            "Production Schedule",
            [
                "Schedule 1: Heavy Overlap (0m, 0m, 0m)",
                "Schedule 2: 15-Min Staggered (0m, 15m, 30m)",
                "Schedule 3: 30-Min Staggered (0m, 30m, 60m)",
                "Schedule 4: Long Idle Break Test (3h gap)",
                "Schedule 5: 4-Press Heavy Double Shift",
                "Upload Custom CSV",
            ]
        )

        sched_map = {
            "Schedule 1": ("schedule_1_peak_overlap.csv", 3),
            "Schedule 2": ("schedule_2_staggered_15m.csv", 3),
            "Schedule 3": ("schedule_3_staggered_30m.csv", 3),
            "Schedule 4": ("schedule_4_idle_waste_test.csv", 3),
            "Schedule 5": ("schedule_5_full_shift_heavy.csv", 4),
        }

        schedule_entries = None
        default_presses = 3
        csv_filename = None
        for key, (fname, n) in sched_map.items():
            if key in schedule_option:
                csv_filename = os.path.join(schedules_dir, fname)
                schedule_entries = load_schedule(csv_filename)
                default_presses = n
                break

        if schedule_entries is None:
            uploaded = st.file_uploader("Upload Schedule CSV", type=["csv"])
            if uploaded:
                schedule_entries = load_schedule(uploaded)
            else:
                csv_filename = os.path.join(schedules_dir, "schedule_1_peak_overlap.csv")
                schedule_entries = load_schedule(csv_filename)
            default_presses = 3

        st.divider()
        st.subheader("Factory Parameters")
        num_presses = st.slider("Active Presses", 1, 4, default_presses)
        shift_hours = st.slider("Simulation Window (Hours)", 1.0, 24.0, 16.0, 0.5)
        dt_seconds = st.select_slider("Timestep Δt (Seconds)", [1, 5, 10, 30], 10)

        st.divider()
        st.subheader("Controller Tuning")
        steam_budget = st.slider("Steam Budget (Press Eq.)", 0.5, 3.0, 1.8, 0.1)
        kp = st.number_input("PID Kp", value=0.01, format="%.4f")
        ki = st.number_input("PID Ki", value=0.001, format="%.5f")
        kd = st.number_input("PID Kd", value=0.005, format="%.4f")

    # -----------------------------------------------------------------------
    # Clean Header
    # -----------------------------------------------------------------------
    st.markdown("""
    <div class="header-container">
        <div class="header-title">Tyre Curing Digital Twin</div>
    </div>
    """, unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Run Simulations
    # -----------------------------------------------------------------------
    with st.spinner("Simulating..."):
        results, press_ids = run_app_simulation(
            schedule_entries, num_presses, shift_hours, dt_seconds, kp, ki, kd, steam_budget
        )
        _sched_csv = csv_filename or os.path.join(schedules_dir, "schedule_1_peak_overlap.csv")
        hl, hc_s = run_simulation(_sched_csv, mode="human")
        sl, sc_s = run_simulation(_sched_csv, mode="smart")

    df_h = results["naive"]
    df_s = results["smart"]

    # Calculate key physical completion metrics
    _pids = hl[-1].get("press_ids", press_ids)
    h_st = total_steam_used(hl, _pids)
    s_st = total_steam_used(sl, _pids)
    _saved_kg = h_st - s_st
    _saved_pct = (_saved_kg / h_st * 100) if h_st > 0 else 0
    h_time = hc_s / 3600
    s_time = sc_s / 3600
    delay_m = (s_time - h_time) * 60
    h_pk = max(r["total_steam_flow_kg_s"] for r in hl)
    s_pk = max(r["total_steam_flow_kg_s"] for r in sl)
    pk_red = ((h_pk - s_pk) / h_pk * 100) if h_pk > 0 else 0

    # -----------------------------------------------------------------------
    # Metric Summary Bar
    # -----------------------------------------------------------------------
    m1, m2, m3, m4 = st.columns(4)

    with m1:
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-box-title">Peak Flow Reduction</div>
            <div class="metric-box-val text-emerald">-{pk_red:.1f}%</div>
            <div class="metric-box-sub">Smart: {s_pk:.4f} kg/s (vs {h_pk:.4f})</div>
        </div>
        """, unsafe_allow_html=True)

    with m2:
        saved_cls = "text-emerald" if _saved_kg >= 0 else "text-rose"
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-box-title">Steam Saved (Cure Window)</div>
            <div class="metric-box-val {saved_cls}">{_saved_kg:+.2f} kg</div>
            <div class="metric-box-sub">{_saved_pct:+.1f}% vs Human Operator</div>
        </div>
        """, unsafe_allow_html=True)

    with m3:
        delay_cls = "text-rose" if delay_m > 0 else "text-emerald"
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-box-title">Physical Completion Delay</div>
            <div class="metric-box-val {delay_cls}">{delay_m:+.1f} mins</div>
            <div class="metric-box-sub">Smart: {s_time:.2f}h (vs {h_time:.2f}h)</div>
        </div>
        """, unsafe_allow_html=True)

    with m4:
        naive_steam = sum(df_h[f"press{p}_total_steam_used_kg"].iloc[-1] for p in press_ids)
        smart_steam = sum(df_s[f"press{p}_total_steam_used_kg"].iloc[-1] for p in press_ids)
        full_saved = naive_steam - smart_steam
        st.markdown(f"""
        <div class="metric-box">
            <div class="metric-box-title">Full-Shift Steam Used</div>
            <div class="metric-box-val text-slate">{smart_steam:.1f} kg</div>
            <div class="metric-box-sub">Human: {naive_steam:.1f} kg (Diff: {full_saved:+.1f} kg)</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown('<div style="height: 16px;"></div>', unsafe_allow_html=True)

    # -----------------------------------------------------------------------
    # Dashboard Tabs
    # -----------------------------------------------------------------------
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Production Gantt Chart",
        "Steam Demand & Flow",
        "Temperature Trajectories",
        "Valve Control Signals u(t)",
        "Simulation Data Log",
    ])

    base_plot_layout = dict(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(15, 23, 42, 0.4)",
        font=dict(family="Inter, sans-serif", color="#F8FAFC"),
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11, color="#F8FAFC")),
        margin=dict(l=50, r=20, t=50, b=60),
        xaxis=dict(
            gridcolor="rgba(255,255,255,0.06)",
            showgrid=True,
            rangeselector=dict(
                buttons=[
                    dict(count=1, label="1h", step="hour", stepmode="backward"),
                    dict(count=4, label="4h", step="hour", stepmode="backward"),
                    dict(count=8, label="8h", step="hour", stepmode="backward"),
                    dict(label="All", step="all"),
                ],
                bgcolor="#1E293B", activecolor="#3B82F6", font=dict(size=11, color="#F8FAFC")
            ),
            type="linear",
        ),
        yaxis=dict(gridcolor="rgba(255,255,255,0.06)", showgrid=True),
    )

    # --- Tab 1: Production Gantt Chart ---
    with tab1:
        st.markdown('<div class="section-title">Production Schedule Gantt Visualization</div>', unsafe_allow_html=True)
        gantt_fig, sorted_pids = build_gantt(schedule_entries, press_ids)
        st.plotly_chart(gantt_fig, use_container_width=True)

        with st.expander("View Schedule Raw CSV Data", expanded=False):
            df_sched = pd.DataFrame(schedule_entries)
            st.dataframe(df_sched, use_container_width=True)

    # --- Tab 2: Steam Flow ---
    with tab2:
        st.markdown('<div class="section-title">Aggregate Steam Flow Rate (kg/s)</div>', unsafe_allow_html=True)
        fig1 = go.Figure()
        fig1.add_trace(go.Scatter(
            x=df_h["time_hours"], y=df_h["total_steam_flow_kg_s"],
            mode="lines", name="Human Operator (u=0.15 Idle)",
            line=dict(color=HUMAN_COLOR, width=1.8, dash="dash")
        ))
        fig1.add_trace(go.Scatter(
            x=df_s["time_hours"], y=df_s["total_steam_flow_kg_s"],
            mode="lines", name="Smart Supervisory Control",
            line=dict(color=SMART_COLOR, width=2.2),
            fill="tozeroy", fillcolor="rgba(16, 185, 129, 0.08)"
        ))
        budget_line = steam_budget * 0.01333
        fig1.add_hline(
            y=budget_line, line_dash="dash", line_color=LIMIT_COLOR, line_width=1.2,
            annotation_text=f"Steam Budget Cap ({steam_budget} Press Eq.)",
            annotation_font=dict(size=11, color=LIMIT_COLOR)
        )

        layout1 = dict(**base_plot_layout, height=480)
        layout1["xaxis"] = dict(**base_plot_layout["xaxis"], title="Shift Time (Hours)")
        layout1["yaxis"] = dict(**base_plot_layout["yaxis"], title="Steam Flow Rate (kg/s)")
        fig1.update_layout(**layout1)
        st.plotly_chart(fig1, use_container_width=True)

    # --- Tab 3: Temperature ---
    with tab3:
        st.markdown('<div class="section-title">Curing Temperature Trajectories (°C)</div>', unsafe_allow_html=True)
        fig2 = go.Figure()
        for idx, pid in enumerate(press_ids):
            color = PRESS_COLORS[idx % len(PRESS_COLORS)]
            fig2.add_trace(go.Scatter(
                x=df_h["time_hours"], y=df_h[f"press{pid}_temperature"],
                mode="lines", name=f"Press {pid} (Human)",
                line=dict(color=color, width=1.2, dash="dot")
            ))
            fig2.add_trace(go.Scatter(
                x=df_s["time_hours"], y=df_s[f"press{pid}_temperature"],
                mode="lines", name=f"Press {pid} (Smart)",
                line=dict(color=color, width=2.2)
            ))
        fig2.add_hline(
            y=TARGET_TEMP, line_dash="dash", line_color=LIMIT_COLOR, line_width=1.2,
            annotation_text=f"Target Setpoint ({TARGET_TEMP}°C)",
            annotation_font=dict(size=11, color=LIMIT_COLOR)
        )
        layout2 = dict(**base_plot_layout, height=500)
        layout2["xaxis"] = dict(**base_plot_layout["xaxis"], title="Shift Time (Hours)")
        layout2["yaxis"] = dict(**base_plot_layout["yaxis"], title="Temperature (°C)", range=[25, 145])
        fig2.update_layout(**layout2)
        st.plotly_chart(fig2, use_container_width=True)

    # --- Tab 4: Valve Signals ---
    with tab4:
        st.markdown('<div class="section-title">Valve Control Commands u(t)</div>', unsafe_allow_html=True)
        fig3 = make_subplots(
            rows=len(press_ids), cols=1, shared_xaxes=True,
            subplot_titles=[f"Press {pid} Valve Signal" for pid in press_ids],
            vertical_spacing=0.08
        )
        for idx, pid in enumerate(press_ids):
            row = idx + 1
            fig3.add_trace(go.Scatter(
                x=df_h["time_hours"], y=df_h[f"press{pid}_valve_opening"],
                mode="lines", name="Human Operator",
                line=dict(color=HUMAN_COLOR, width=1.5, dash="dash"),
                showlegend=(idx == 0)
            ), row=row, col=1)
            fig3.add_trace(go.Scatter(
                x=df_s["time_hours"], y=df_s[f"press{pid}_valve_opening"],
                mode="lines", name="Smart Control",
                line=dict(color=SMART_COLOR, width=2.0),
                showlegend=(idx == 0)
            ), row=row, col=1)

        fig3.update_layout(
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(15, 23, 42, 0.4)",
            font=dict(family="Inter, sans-serif", color="#F8FAFC"),
            height=260 * len(press_ids),
            hovermode="x unified",
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(size=11, color="#F8FAFC")),
            margin=dict(l=50, r=20, t=40, b=50)
        )
        fig3.update_xaxes(title_text="Shift Time (Hours)", row=len(press_ids), col=1, gridcolor="rgba(255,255,255,0.05)")
        fig3.update_yaxes(range=[-0.05, 1.1], gridcolor="rgba(255,255,255,0.05)")
        st.plotly_chart(fig3, use_container_width=True)

    # --- Tab 5: Raw Simulation Log ---
    with tab5:
        st.markdown('<div class="section-title">Smart Control Simulation Output Log</div>', unsafe_allow_html=True)
        st.dataframe(df_s.style.format(precision=4), use_container_width=True)


if __name__ == "__main__":
    main()
