"""
app.py — Hospital Surgery Scheduling GUI
=========================================
Person 5 — Streamlit Interface
Integrates agent.py + planner.py (backtracking, preemption, safety gates).
"""

import streamlit as st
import pandas as pd
import os
import re
import json
import subprocess
import time
from datetime import datetime, timedelta

# Graceful import to support both root execution and organized execution
try:
    from scenario import (
        scenario_normal, scenario_rooms_closed, scenario_tool_blocked, 
        scenario_preemption, scenario_random_failure, scenario_timeout, scenario_rate_limit
    )
except ImportError:
    pass # Scenarios will be run via subprocess to ensure clean state and logs

# ── Page Config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Hôpital Charles Nicolle — Tunisian Healthcare Orchestration",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@500;600;700&family=Jost:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap');

/* ═══════════════════════════════════════
   NUCLEAR LIGHT THEME OVERRIDE
═══════════════════════════════════════ */
html, body, [class*="css"], .stApp,
[data-testid="stAppViewContainer"],
[data-testid="stAppViewBlockContainer"],
[data-testid="stVerticalBlock"],
[data-testid="stHorizontalBlock"],
.block-container, .main, section.main {
    background-color: #ffffff !important;
    color: #1e3a5f !important;
    font-family: 'Jost', sans-serif;
}

/* ALL elements forced dark text */
* { color: #1e3a5f; }

/* ── Inputs ── */
input, textarea {
    background-color: #ffffff !important;
    color: #1e3a5f !important;
    border: 1.5px solid #bdd7f0 !important;
    border-radius: 7px !important;
    font-family: 'Jost', sans-serif !important;
}
input::placeholder, textarea::placeholder {
    color: #7ea8c9 !important; opacity: 1 !important;
}

/* ── Selectbox container + inner text ── */
[data-baseweb="select"],
[data-baseweb="select"] > div,
[data-baseweb="select"] > div > div,
[data-baseweb="select"] input,
[data-baseweb="select"] span,
[data-baseweb="select"] div,
[data-testid="stSelectbox"] > div > div {
    background-color: #ffffff !important;
    color: #1e3a5f !important;
    border-color: #bdd7f0 !important;
}

/* ── Dropdown open menu ── */
[data-baseweb="popover"], [data-baseweb="popover"] *,
[data-baseweb="menu"], [data-baseweb="menu"] *,
[data-baseweb="list"], [data-baseweb="list"] * {
    background-color: #ffffff !important;
    color: #1e3a5f !important;
}
[data-baseweb="option"]:hover,
[data-baseweb="option"][aria-selected="true"] {
    background-color: #e8f4fd !important;
    color: #1e3a5f !important;
}

/* ── Number input +/- ── */
[data-testid="stNumberInput"] button,
[data-baseweb="input"] button {
    background-color: #f0f6ff !important;
    color: #1e3a5f !important;
    border: 1px solid #bdd7f0 !important;
}

/* ── Date input ── */
[data-testid="stDateInput"] input,
[data-baseweb="datepicker"] input {
    background-color: #ffffff !important;
    color: #1e3a5f !important;
}

/* ── All widget labels ── */
label, [data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] * {
    color: #1e3a5f !important;
    font-weight: 500 !important;
}

/* ── Markdown / text blocks ── */
.stMarkdown *, [data-testid="stMarkdownContainer"] * {
    color: #1e3a5f !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] *, .stDataFrame *, .dataframe *,
thead tr th, tbody tr td {
    background-color: #ffffff !important;
    color: #1e3a5f !important;
}
thead tr th { background-color: #e8f4fd !important; font-weight: 600 !important; }
tbody tr:nth-child(even) td { background-color: #f0f6ff !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"], [data-testid="stSidebar"] > div {
    background: #f0f6ff !important;
    border-right: 1px solid #bdd7f0;
}
[data-testid="stSidebar"] * { color: #1e3a5f !important; }
[data-testid="stSidebar"] label {
    font-size: 0.75rem !important; font-weight: 600 !important;
    text-transform: uppercase; letter-spacing: 0.08em; color: #64748b !important;
}
[data-testid="stSidebar"] input,
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: #ffffff !important;
    border: 1px solid #bdd7f0 !important;
    color: #1e3a5f !important;
}

#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 2.5rem 3.5rem 3rem; max-width: 1500px; }

/* Header */
.main-header {
    background: linear-gradient(135deg, #e8f4fd 0%, #f0f7ff 100%);
    border: 1px solid #bdd7f0; border-radius: 12px;
    padding: 1.8rem 2.4rem; margin-bottom: 2.2rem;
    display: flex; align-items: center; justify-content: space-between;
}
.main-header h1 {
    font-family: 'Cormorant Garamond', serif;
    color: #1a3f6b !important; font-size: 2.1rem; margin: 0; letter-spacing: 0.01em;
}
.main-header .subtitle { color: #4a6fa5; font-size: 0.85rem; margin-top: 0.3rem; font-weight: 300; }
.header-date { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #4a6fa5; }
.header-status {
    display: inline-block; margin-top: 0.4rem;
    background: #d4edda; border: 1px solid #a3d9b1;
    border-radius: 4px; padding: 2px 10px; font-size: 0.72rem; color: #1a6b3a;
    letter-spacing: 0.06em; font-weight: 500; text-transform: uppercase;
}

/* KPI */
.kpi-card {
    background: #ffffff; border: 1px solid #e8e3db;
    border-top: 3px solid var(--accent); border-radius: 10px;
    padding: 1.3rem 1.5rem; box-shadow: 0 2px 8px rgba(28,31,46,0.05);
}
.kpi-num { font-family: 'Cormorant Garamond', serif; font-size: 2.6rem; color: var(--accent); line-height: 1; }
.kpi-label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.07em; color: #64748b; font-weight: 600; margin-top: 0.3rem; }
.kpi-sub { font-size: 0.77rem; color: #a5a09a; margin-top: 0.15rem; }

/* Section */
.section-title {
    font-family: 'Cormorant Garamond', serif; font-size: 1.3rem; color: #1e3a5f;
    margin: 0 0 1.2rem; padding-bottom: 0.5rem; border-bottom: 1px solid #e8e3db;
}

/* Tabs */
.stTabs [data-baseweb="tab-list"] { background: #f5f3ef; border-radius: 8px; padding: 4px; gap: 3px; }
.stTabs [data-baseweb="tab"] {
    border-radius: 6px; font-size: 0.85rem; font-weight: 500;
    color: #64748b; padding: 0.45rem 1.2rem;
}
.stTabs [aria-selected="true"] {
    background: #ffffff !important; color: #1e3a5f !important;
    box-shadow: 0 1px 6px rgba(28,31,46,0.1);
}

/* Badges */
.badge {
    display: inline-block; padding: 2px 9px; border-radius: 3px;
    font-size: 0.72rem; font-weight: 600; letter-spacing: 0.05em; text-transform: uppercase;
}
.badge-high          { background: #fde8e8; color: #dc2626; border: 1px solid #f5bcbc; }
.badge-medium        { background: #fef3cd; color: #b45309; border: 1px solid #fde68a; }
.badge-low           { background: #e8f5e9; color: #15803d; border: 1px solid #a5d6a7; }
.badge-scheduled     { background: #e3f2fd; color: #1d4ed8; border: 1px solid #90caf9; }
.badge-not_scheduled { background: #ede9fe; color: #6d28d9; border: 1px solid #c4b5fd; }

/* Patient row */
.pat-row {
    background: #ffffff; border: 1px solid #ece7e0;
    border-left: 3px solid var(--accent-left, #d4cfc6); border-radius: 8px;
    padding: 0.85rem 1.1rem; margin-bottom: 0.55rem;
    display: flex; align-items: center; justify-content: space-between;
    transition: box-shadow 0.15s;
}
.pat-row:hover { box-shadow: 0 3px 12px rgba(28,31,46,0.1); }
.pat-id { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #a5a09a; min-width: 38px; }
.pat-name { font-weight: 600; color: #1e3a5f; font-size: 0.92rem; }
.pat-meta { font-size: 0.76rem; color: #a5a09a; margin-top: 2px; }

/* Room cards */
.room-card { background: #ffffff; border: 1px solid #ece7e0; border-radius: 10px; padding: 1.2rem; box-shadow: 0 1px 6px rgba(28,31,46,0.05); }
.room-header { font-family: 'Cormorant Garamond', serif; font-size: 1.05rem; color: #1e3a5f; margin-bottom: 0.9rem; display: flex; align-items: center; gap: 0.6rem; }
.room-pill { border-radius: 4px; padding: 2px 10px; font-family: 'Jost', sans-serif; font-size: 0.78rem; font-weight: 600; color: #ffffff !important; letter-spacing: 0.05em; text-transform: uppercase; }
.slot-card { border-radius: 6px; padding: 0.6rem 0.85rem; margin-bottom: 0.45rem; border-left: 3px solid var(--slot-accent); background: #f9f7f4; }
.slot-time { font-family: 'JetBrains Mono', monospace; font-size: 0.78rem; color: #64748b; }
.slot-name { font-weight: 600; font-size: 0.88rem; color: #1e3a5f; margin-top: 1px; }
.slot-meta { font-size: 0.74rem; color: #a5a09a; margin-top: 1px; }

/* Terminal */
.terminal {
    background: #f8fafc; border: 1px solid #cbd5e1; border-radius: 10px;
    padding: 1.4rem 1.6rem; font-family: 'JetBrains Mono', monospace;
    font-size: 0.8rem; line-height: 1.75; min-height: 180px; max-height: 420px;
    overflow-y: auto;
}
.log-sys          { color: #64748b; }
.log-user         { color: #1e293b; font-weight: 600; }
.log-planner      { color: #7c3aed; }
.log-worker       { color: #059669; }
.log-critic       { color: #b45309; }
.log-orchestrator { color: #0369a1; }
.log-error        { color: #dc2626; }
.log-success      { color: #16a34a; }
.log-blocked      { color: #dc2626; font-weight: 600; }
.log-preempt      { color: #ea580c; }

/* Chat bubbles */
.bubble-user { display: flex; justify-content: flex-end; margin-bottom: 0.7rem; }
.bubble-user > div {
    background: #2563eb; color: #ffffff !important;
    border-radius: 14px 14px 2px 14px; padding: 0.65rem 1rem;
    max-width: 75%; font-size: 0.88rem; line-height: 1.5;
}
.bubble-agent { display: flex; justify-content: flex-start; margin-bottom: 0.7rem; }
.bubble-agent > div {
    background: #f5f3ef; border: 1px solid #e0dbd2; color: #1e3a5f;
    border-radius: 14px 14px 14px 2px; padding: 0.65rem 1rem;
    max-width: 80%; font-size: 0.88rem; line-height: 1.5;
}
.bubble-preempt { display: flex; justify-content: flex-start; margin-bottom: 0.7rem; }
.bubble-preempt > div {
    background: #fffbeb; border: 1px solid #fde68a; color: #c2410c;
    border-radius: 14px 14px 14px 2px; padding: 0.65rem 1rem;
    max-width: 80%; font-size: 0.85rem; line-height: 1.5;
}

/* Buttons */
.stButton > button {
    background: #2563eb; color: #ffffff !important; border: none; border-radius: 7px;
    padding: 0.55rem 1.3rem; font-family: 'Jost', sans-serif; font-weight: 600;
    font-size: 0.85rem; letter-spacing: 0.04em; width: 100%;
    transition: background 0.15s, box-shadow 0.15s;
}
.stButton > button:hover { background: #1d4ed8; box-shadow: 0 3px 10px rgba(37,99,235,0.25); }

/* Inputs */
.stTextInput > div > div > input,
.stNumberInput > div > div > input,
.stDateInput > div > div > input {
    border-radius: 7px; border: 1.5px solid #bdd7f0 !important;
    font-family: 'Jost', sans-serif; font-size: 0.88rem;
    color: #1e3a5f !important; background-color: #ffffff !important;
}

/* Selectbox / dropdowns */
.stSelectbox > div > div,
.stSelectbox > div > div > div,
[data-baseweb="select"] > div,
[data-baseweb="select"] input {
    background-color: #ffffff !important;
    color: #1e3a5f !important;
    border-color: #bdd7f0 !important;
}
[data-baseweb="popover"] ul,
[data-baseweb="menu"] {
    background-color: #ffffff !important;
    color: #1e3a5f !important;
}
[data-baseweb="option"]:hover { background-color: #e8f4fd !important; }

/* Number input buttons */
.stNumberInput button { background-color: #f0f6ff !important; color: #1e3a5f !important; }

/* Dataframe / table */
[data-testid="stDataFrame"] iframe,
.stDataFrame, .dataframe {
    background-color: #ffffff !important;
    color: #1e3a5f !important;
}
[data-testid="stDataFrame"] * { color: #1e3a5f !important; }
thead tr th {
    background-color: #e8f4fd !important;
    color: #1e3a5f !important;
}
tbody tr { background-color: #ffffff !important; color: #1e3a5f !important; }
tbody tr:nth-child(even) { background-color: #f0f6ff !important; }

/* Alerts */
.alert-success { background: #e8f5e9; border: 1px solid #a5d6a7; border-radius: 8px; padding: 0.75rem 1rem; color: #15803d; font-size: 0.86rem; }
.alert-error   { background: #fde8e8; border: 1px solid #f5bcbc; border-radius: 8px; padding: 0.75rem 1rem; color: #7f1d1d; font-size: 0.86rem; }
.alert-warning { background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; padding: 0.75rem 1rem; color: #c2410c; font-size: 0.86rem; }
.alert-info    { background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 0.75rem 1rem; color: #1e3a8a; font-size: 0.86rem; }

/* Safety panel */
.safety-row {
    display: flex; justify-content: space-between; align-items: center;
    background: #f9f7f4; border: 1px solid #e0dbd2; border-radius: 7px;
    padding: 0.6rem 0.9rem; margin-bottom: 0.45rem; font-size: 0.85rem;
}
.ind-open    { color: #15803d; font-weight: 600; font-size: 0.78rem; }
.ind-closed  { color: #dc2626; font-weight: 600; font-size: 0.78rem; }

::-webkit-scrollbar { width: 5px; }
::-webkit-scrollbar-track { background: #f5f3ef; }
::-webkit-scrollbar-thumb { background: #d4cfc6; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────
BASE_DIR       = os.path.dirname(os.path.abspath(__file__))
PATIENTS_FILE  = os.path.join(BASE_DIR, "patients.csv")
ROOMS_FILE     = os.path.join(BASE_DIR, "rooms_schedule.csv")
LOGS_FILE      = os.path.join(BASE_DIR, "logs.txt")
ROOMS_LIST     = ["room1", "room2", "room3"]
GAP_MINUTES    = 30
URGENCY_ORDER  = {"high": 1, "medium": 2, "low": 3}
ROOM_COLORS    = {"room1": "#2563eb", "room2": "#7c3aed", "room3": "#059669"}
URGENCY_ACCENT = {"high": "#dc2626", "medium": "#b45309", "low": "#15803d"}

# ── Data helpers ──────────────────────────────────────────────────────────────
def load_patients():
    if not os.path.exists(PATIENTS_FILE):
        return pd.DataFrame(columns=["patient_id","patient_name","urgency","duration","date","status"])
    df = pd.read_csv(PATIENTS_FILE, dtype=str)
    df.columns = df.columns.str.strip()
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    return df

def load_rooms():
    if not os.path.exists(ROOMS_FILE):
        return pd.DataFrame(columns=["room_id","patient_id","start_time","end_time"])
    df = pd.read_csv(ROOMS_FILE, dtype=str)
    df.columns = df.columns.str.strip()
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    df = df[df["patient_id"].str.strip() != ""]
    return df

def save_patients(df): df.to_csv(PATIENTS_FILE, index=False)
def save_rooms(df):    df.to_csv(ROOMS_FILE, index=False)

def add_minutes(t, mins):
    dt = datetime.strptime(t, "%H:%M") + timedelta(minutes=int(mins))
    return dt.strftime("%H:%M")

def duration_to_minutes(d): return int(float(d) * 60)
def strip_ansi(text): return re.sub(r'\x1b\[[0-9;]*m', '', text)

def run_admin_cmd(cmd: str):
    """Send an admin command (close_room:, open_room:, etc.) to agent.py."""
    try:
        agent_path = os.path.join(BASE_DIR, "agent.py")
        subprocess.run(
            ["python", agent_path],
            input=f"{cmd}\nquit\n",
            capture_output=True, text=True, timeout=15, cwd=BASE_DIR,
        )
    except Exception:
        pass

# ── Parse System Logs (Tache 2 & 3) ───────────────────────────────────────────
def get_system_logs():
    runs = {}
    if os.path.exists(LOGS_FILE):
        with open(LOGS_FILE, "r") as f:
            for line in f:
                if not line.strip(): continue
                try:
                    entry = json.loads(line)
                    run_id = entry.get("run_id", "unknown")
                    if run_id not in runs:
                        runs[run_id] = []
                    runs[run_id].append(entry)
                except:
                    pass
    return runs

# ── Session state ─────────────────────────────────────────────────────────────
for k, v in {
    "logs": [], "agent_messages": [],
    "closed_rooms": set(), "absent_surgeons": [], "forbidden_actions": set(),
}.items():
    if k not in st.session_state:
        st.session_state[k] = v

def add_log(agent, message, level="info"):
    st.session_state.logs.append({
        "time": datetime.now().strftime("%H:%M:%S"),
        "agent": agent, "message": message, "level": level,
    })

# ── Header ────────────────────────────────────────────────────────────────────
now_str = datetime.now().strftime("%A, %d %B %Y  |  %H:%M")
st.markdown(f"""
<div class="main-header">
    <div>
        <h1>Hôpital Charles Nicolle</h1>
        <div class="subtitle">Secure Multi-Agent Tool-Orchestration for the Tunisian Healthcare Economy</div>
    </div>
    <div style="text-align:right">
        <div class="header-date">{now_str}</div>
        <span class="header-status">System Online</span>
    </div>
</div>
""", unsafe_allow_html=True)

# ── KPI Row ───────────────────────────────────────────────────────────────────
patients = load_patients()
rooms    = load_rooms()

total_p     = len(patients)
scheduled   = len(patients[patients["status"]=="scheduled"])  if total_p > 0 else 0
unscheduled = total_p - scheduled
high_urg    = len(patients[patients["urgency"]=="high"])      if total_p > 0 else 0

cols = st.columns(4)
for col, (label, val, sub, color) in zip(cols, [
    ("Total Patients",      total_p,     "All registered patients",        "#2563eb"),
    ("Scheduled",           scheduled,   "Assigned to an operating room",  "#0369a1"),
    ("Awaiting Allocation", unscheduled, "Not yet assigned to a room",     "#7c3aed"),
    ("High Urgency",        high_urg,    "Priority surgical cases",        "#dc2626"),
]):
    with col:
        st.markdown(f"""
        <div class="kpi-card" style="--accent:{color}">
            <div class="kpi-num">{val}</div>
            <div class="kpi-label">{label}</div>
            <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3, tab6, tab4, tab5, tab7 = st.tabs([
    "Patient Registry", "Room Schedule", "AI Agent Console", "Trace Panel & Logs",
    "Manage Patients", "Safety Controls", "Analytics & Metrics"
])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Patient Registry
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown('<div class="section-title">Patient Registry</div>', unsafe_allow_html=True)

    fc1, fc2, fc3 = st.columns([2.5, 1, 1])
    with fc1:
        search = st.text_input("Search", placeholder="Search by name...", label_visibility="collapsed")
    with fc2:
        filt_urg = st.selectbox("Urgency", ["All Urgencies","High","Medium","Low"], label_visibility="collapsed")
    with fc3:
        filt_stat = st.selectbox("Status", ["All Statuses","Scheduled","Not Scheduled"], label_visibility="collapsed")

    df_show = patients.copy()
    if search:
        df_show = df_show[df_show["patient_name"].str.contains(search, case=False, na=False)]
    if filt_urg != "All Urgencies":
        df_show = df_show[df_show["urgency"].str.lower() == filt_urg.lower()]
    if filt_stat == "Scheduled":
        df_show = df_show[df_show["status"] == "scheduled"]
    elif filt_stat == "Not Scheduled":
        df_show = df_show[df_show["status"] == "not_scheduled"]

    pat_room_map = {}
    if not rooms.empty:
        for _, r in rooms.iterrows():
            pat_room_map[str(r["patient_id"])] = r

    if df_show.empty:
        st.markdown('<div class="alert-info">No patients match the current filters.</div>', unsafe_allow_html=True)
    else:
        for _, row in df_show.iterrows():
            urg    = str(row["urgency"]).lower()
            stat   = str(row["status"]).lower()
            pid    = str(row["patient_id"])
            accent = URGENCY_ACCENT.get(urg, "#64748b")
            rr     = pat_room_map.get(pid)
            room_info = (
                f'<span style="font-family:\'JetBrains Mono\',monospace;font-size:0.78rem;color:#1d4ed8">'
                f'{rr["room_id"].upper()} &nbsp; {rr["start_time"]} &ndash; {rr["end_time"]}</span>'
            ) if rr is not None else ""

            st.markdown(f"""<div class="pat-row" style="--accent-left:{accent}">
<div style="display:flex;align-items:center;gap:1.1rem;flex:1">
<div class="pat-id">#{pid}</div>
<div>
<div class="pat-name">{row['patient_name']}</div>
<div class="pat-meta">{row['date']} &nbsp;&middot;&nbsp; {row['duration']}h surgery</div>
</div>
</div>
<div style="display:flex;align-items:center;gap:0.75rem">{room_info}
<span class="badge badge-{urg}">{urg.upper()}</span>
<span class="badge badge-{stat.replace(' ','_')}">{stat.replace('_',' ').upper()}</span>
</div>
</div>""", unsafe_allow_html=True)

        st.markdown(f'<div style="color:#a5a09a;font-size:0.78rem;margin-top:0.4rem">Showing {len(df_show)} of {len(patients)} patients</div>',
                    unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Room Schedule
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.markdown('<div class="section-title">Operating Room Schedule</div>', unsafe_allow_html=True)

    if rooms.empty:
        st.markdown('<div class="alert-info">No room assignments found. Use the Manage Patients tab or AI Agent Console to allocate patients.</div>', unsafe_allow_html=True)
    else:
        pat_lookup = {str(r["patient_id"]): r for _, r in patients.iterrows()}
        room_cols  = st.columns(3)

        for col, room in zip(room_cols, ROOMS_LIST):
            with col:
                color   = ROOM_COLORS.get(room, "#1e3a5f")
                r_slots = rooms[rooms["room_id"] == room]
                count   = len(r_slots)
                st.markdown(f"""
                <div class="room-card">
                    <div class="room-header">
                        <span class="room-pill" style="background:{color}">{room.upper()}</span>
                        <span style="font-size:0.8rem;color:#a5a09a">{count} patient{'s' if count!=1 else ''}</span>
                    </div>""", unsafe_allow_html=True)

                if r_slots.empty:
                    st.markdown('<div style="color:#a5a09a;font-size:0.82rem">No patients assigned</div>', unsafe_allow_html=True)
                else:
                    for _, slot in r_slots.iterrows():
                        pid   = str(slot["patient_id"])
                        pinfo = pat_lookup.get(pid)
                        pname = pinfo["patient_name"] if pinfo is not None else f"Patient #{pid}"
                        urg   = pinfo["urgency"].lower() if pinfo is not None else ""
                        acc   = URGENCY_ACCENT.get(urg, "#64748b")
                        st.markdown(f"""
                        <div class="slot-card" style="--slot-accent:{acc}">
                            <div class="slot-time">{slot['start_time']} &ndash; {slot['end_time']}</div>
                            <div class="slot-name">{pname}</div>
                            <div class="slot-meta">{urg.capitalize() if urg else ''} urgency &nbsp;&middot;&nbsp; ID #{pid}</div>
                        </div>""", unsafe_allow_html=True)

                st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<div class="section-title">Full Schedule Table</div>', unsafe_allow_html=True)
        merged = rooms.copy()
        merged["Patient Name"] = merged["patient_id"].map(
            lambda pid: pat_lookup.get(pid, {}).get("patient_name", "Unknown")
            if pat_lookup.get(pid) is not None else "Unknown"
        )
        merged["Urgency"] = merged["patient_id"].map(
            lambda pid: pat_lookup.get(pid, {}).get("urgency", "")
            if pat_lookup.get(pid) is not None else ""
        )
        merged = merged.rename(columns={"room_id":"Room","patient_id":"ID","start_time":"Start","end_time":"End"})
        st.dataframe(merged[["Room","ID","Patient Name","Urgency","Start","End"]], use_container_width=True, hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — AI Agent Console
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    st.markdown('<div class="section-title">AI Agent Console</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="alert-info" style="margin-bottom:1.2rem">
        <strong>Natural language interface</strong> &mdash; the multi-agent pipeline (Planner, Worker, Critic, Orchestrator)
        handles your request with backtracking, preemption, and safety validation built in.<br>
        <span style="color:#374151">Examples:</span>
        <em>"Add patient Ahmed Ben Salah, high urgency, 2 hours, 20-04-2026"</em> &nbsp;&middot;&nbsp;
        <em>"Allocate all patients to rooms"</em> &nbsp;&middot;&nbsp;
        <em>"Update patient 3, change urgency to low"</em>
    </div>""", unsafe_allow_html=True)

    # Chat history
    for msg in st.session_state.agent_messages:
        role    = msg["role"]
        content = msg["content"]
        kind    = msg.get("kind", "normal")
        if role == "user":
            st.markdown(f'<div class="bubble-user"><div>{content}</div></div>', unsafe_allow_html=True)
        elif kind == "preempt":
            st.markdown(f'<div class="bubble-preempt"><div><strong>Scheduling Notice</strong><br>{content}</div></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="bubble-agent"><div>{content}</div></div>', unsafe_allow_html=True)

    # Input
    with st.form("agent_form", clear_on_submit=True):
        ic1, ic2 = st.columns([5, 1])
        with ic1:
            user_cmd = st.text_input("Command", placeholder="Type your scheduling command here...", label_visibility="collapsed")
        with ic2:
            submitted = st.form_submit_button("Send")

    if submitted and user_cmd.strip():
        st.session_state.agent_messages.append({"role": "user", "content": user_cmd})
        add_log("user", f"Request: {user_cmd}", "info")

        with st.spinner("Agent pipeline running..."):
            try:
                agent_path = os.path.join(BASE_DIR, "agent.py")
                if os.path.exists(agent_path):
                    # Force child process to use UTF-8 for print() to prevent cp1252 crashes
                    env = os.environ.copy()
                    env["PYTHONIOENCODING"] = "utf-8"
                    
                    proc = subprocess.run(
                        ["python", agent_path],
                        input=user_cmd + "\nquit\n",
                        capture_output=True, text=True, encoding="utf-8", timeout=90, cwd=BASE_DIR,
                        env=env
                    )
                    raw = strip_ansi(proc.stdout + proc.stderr)

                    agent_reply  = None
                    preempt_note = None
                    for line in raw.splitlines():
                        if "AGENT:" in line:
                            agent_reply = line.split("AGENT:", 1)[-1].strip()
                        if "moved out" in line.lower():
                            preempt_note = line.strip()

                    for line in raw.splitlines():
                        clean = line.strip()
                        for tag, key in [("[PLANNER]","planner"),("[WORKER]","worker"),
                                         ("[CRITIC]","critic"),("[ORCHESTRATOR]","orchestrator")]:
                            if tag in clean:
                                lvl = "error" if any(w in clean for w in ["BLOCKED","REJECTED","error"]) else "info"
                                add_log(key, clean.replace(tag,"").strip(), lvl)

                    if not agent_reply:
                        if proc.returncode != 0:
                            err_msg = [line for line in raw.splitlines() if "Error:" in line or "Exception:" in line or "ERROR:" in line]
                            err_text = err_msg[-1] if err_msg else raw.splitlines()[-1] if raw.strip() else "Unknown error"
                            agent_reply = f"The AI agent crashed. Details: {err_text}"
                            add_log("system", f"Agent crash: {err_text}", "error")
                            
                            # Also save it to logs.txt
                            with open(LOGS_FILE, "a") as f:
                                f.write(json.dumps({
                                    "time": datetime.now().isoformat(), "run_id": "unknown",
                                    "agent": "system", "message": f"Agent crashed: {err_text}", "detail": None
                                }) + "\n")
                        else:
                            agent_reply = "Operation completed. Refresh the page to see updated data."

                    if proc.returncode == 0:
                        add_log("orchestrator", "Task completed.", "success")
                    st.session_state.agent_messages.append({"role": "agent", "content": agent_reply})
                    if preempt_note:
                        st.session_state.agent_messages.append({"role": "agent", "content": preempt_note, "kind": "preempt"})
                else:
                    st.session_state.agent_messages.append({"role":"agent","content":"agent.py not found. Ensure it is in the same directory as app.py."})
            except subprocess.TimeoutExpired:
                add_log("orchestrator", "Timeout.", "error")
                st.session_state.agent_messages.append({"role":"agent","content":"The agent timed out. Please try again."})
                
                # Write to logs.txt so the Trace Panel registers the timeout
                with open(LOGS_FILE, "a") as f:
                    timeout_entry = {
                        "time": datetime.now().isoformat(),
                        "run_id": "unknown",
                        "agent": "orchestrator",
                        "message": "Timeout. The agent took too long to respond.",
                        "detail": None
                    }
                    # Try to find the last run_id from the file
                    try:
                        with open(LOGS_FILE, "r") as log_r:
                            lines = [l for l in log_r if l.strip()]
                            if lines:
                                last_entry = json.loads(lines[-1])
                                timeout_entry["run_id"] = last_entry.get("run_id", "unknown")
                    except Exception:
                        pass
                    f.write(json.dumps(timeout_entry) + "\n")
            except Exception as exc:
                add_log("orchestrator", f"Error: {exc}", "error")
                st.session_state.agent_messages.append({"role":"agent","content":f"An error occurred: {exc}"})
        st.rerun()

    # Log panel
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown('<div class="section-title">Terminal Output</div>', unsafe_allow_html=True)

    LOG_CSS   = {"user":"log-user","planner":"log-planner","worker":"log-worker",
                 "critic":"log-critic","orchestrator":"log-orchestrator","system":"log-sys"}
    LEVEL_CSS = {"error":"log-error","success":"log-success"}

    if not st.session_state.logs:
        html_log = '<span class="log-sys">System ready. Waiting for commands.</span><br><span class="log-sys">Pipeline: Planner &rarr; Worker &rarr; Critic &rarr; Orchestrator</span>'
    else:
        lines = []
        for e in st.session_state.logs[-40:]:
            base = LOG_CSS.get(e["agent"], "log-sys")
            lvl  = LEVEL_CSS.get(e.get("level",""), "")
            cls  = f'{base} {lvl}'.strip()
            lines.append(f'<span class="{cls}">[{e["time"]}] [{e["agent"].upper()}] {e["message"]}</span>')
        html_log = "<br>".join(lines)

    st.markdown(f'<div class="terminal">{html_log}</div>', unsafe_allow_html=True)
    if st.button("Clear Log", key="clear_log"):
        st.session_state.logs = []
        st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 6 — Trace Panel & Run List (Tâche 2 & 3 Integration)
# ══════════════════════════════════════════════════════════════════════════════
with tab6:
    st.markdown('<div class="section-title">System Execution Traces</div>', unsafe_allow_html=True)
    system_runs = get_system_logs()
    run_ids = list(system_runs.keys())[::-1]

    if not run_ids:
        st.markdown('<div class="alert-info">No runs recorded in logs.txt yet. Run a scenario to see traces.</div>', unsafe_allow_html=True)
    else:
        rc1, rc2 = st.columns([1, 2.5])
        
        if "selected_system_run" not in st.session_state:
            st.session_state.selected_system_run = run_ids[0]

        with rc1:
            st.markdown("#### Run List")
            for rid in run_ids:
                run_events = system_runs[rid]
                
                # Try to find user request
                user_req = "Agent Execution"
                for ev in run_events:
                    if ev.get("agent") == "user":
                        user_req = ev.get("detail", {}).get("user_message", user_req)
                        break
                        
                # Check success/failure
                status_icon = "⏳"
                for ev in run_events:
                    msg_str = str(ev.get("message"))
                    if ev.get("agent") == "orchestrator" and ("MAX_STEPS reached" in msg_str or "Timeout" in msg_str):
                        status_icon = "[FAIL]"
                    elif ev.get("agent") == "critic" and "REJECTED" in msg_str:
                        status_icon = "[WARN]"
                    elif ev.get("agent") == "orchestrator" and "Generating final response" in msg_str:
                        status_icon = "[OK]"

                if st.button(f"{status_icon} {user_req[:20]}...", key=f"run_btn_{rid}", use_container_width=True):
                    st.session_state.selected_system_run = rid
                    st.rerun()

        with rc2:
            st.markdown("#### Trace Panel")
            if st.session_state.selected_system_run in system_runs:
                selected_events = system_runs[st.session_state.selected_system_run]
                for ev in selected_events:
                    agent = ev.get("agent", "system")
                    msg = ev.get("message", "")
                    time_str = ev.get("time", "").split("T")[-1][:8]
                    
                    if agent == "user":
                        st.markdown(f'<div class="alert-info"><strong>[{time_str}] Step 0 &rarr; USER:</strong> {msg}</div>', unsafe_allow_html=True)
                    elif agent == "planner":
                        st.markdown(f'<div style="color:#7c3aed;margin-left:15px;margin-top:10px"><strong>[{time_str}] Step 1 &rarr; PLANNER:</strong> {msg}</div>', unsafe_allow_html=True)
                    elif agent == "worker":
                        st.markdown(f'<div style="color:#059669;margin-left:30px;margin-top:10px"><strong>[{time_str}] Step 2 &rarr; WORKER:</strong> {msg}</div>', unsafe_allow_html=True)
                    elif agent == "critic":
                        color = "#b45309" if "REJECTED" not in msg else "#dc2626"
                        st.markdown(f'<div style="color:{color};margin-left:45px;margin-top:10px;margin-bottom:10px"><strong>[{time_str}] Step 3 &rarr; CRITIC:</strong> {msg}</div>', unsafe_allow_html=True)
                    elif agent == "orchestrator":
                        st.markdown(f'<div style="color:#0369a1;font-weight:bold;margin-top:10px;padding:10px;background:#f0f6ff;border-radius:5px">[{time_str}] ORCHESTRATOR: {msg}</div>', unsafe_allow_html=True)
            else:
                st.info("Select a run from the list.")

# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Manage Patients (Existing logic intact)
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.markdown('<div class="section-title">Manage Patients</div>', unsafe_allow_html=True)
    left_col, right_col = st.columns([1.4, 1])

    with left_col:
        action = st.radio("Action", ["Add Patient","Update Patient","Allocate Rooms", "Delete Patient", "Unschedule Patient"],
                          horizontal=True, label_visibility="collapsed")
        st.markdown("<br>", unsafe_allow_html=True)

        if action == "Add Patient":
            st.markdown("#### Add New Patient")
            name_in = st.text_input("Full Name")
            urg_in  = st.selectbox("Urgency", ["high","medium","low"], format_func=str.capitalize)
            dur_in  = st.number_input("Surgery Duration (hours)", 0.5, 12.0, 1.0, 0.5)
            date_in = st.date_input("Surgery Date", value=datetime.today())

            if st.button("Add Patient", key="btn_add"):
                if not name_in.strip():
                    st.markdown('<div class="alert-error">Please enter a patient name.</div>', unsafe_allow_html=True)
                else:
                    pats   = load_patients()
                    new_id = int(pats["patient_id"].astype(int).max()) + 1 if not pats.empty else 1
                    pats   = pd.concat([pats, pd.DataFrame([{
                        "patient_id":   new_id, "patient_name": name_in.strip(),
                        "urgency":      urg_in, "duration":     dur_in,
                        "date":         date_in.strftime("%d-%m-%Y"), "status": "not_scheduled",
                    }])], ignore_index=True)
                    save_patients(pats)
                    add_log("system", f"Patient '{name_in}' added with ID {new_id}.", "success")
                    st.markdown(f'<div class="alert-success">Patient <strong>{name_in}</strong> added with ID <strong>#{new_id}</strong>.</div>', unsafe_allow_html=True)
                    time.sleep(0.4); st.rerun()

        elif action == "Update Patient":
            st.markdown("#### Update Existing Patient")
            pats = load_patients()
            if pats.empty:
                st.markdown('<div class="alert-info">No patients to update.</div>', unsafe_allow_html=True)
            else:
                sel_pid  = st.selectbox("Select Patient", pats["patient_id"].tolist(),
                    format_func=lambda pid: f"#{pid} — {pats[pats['patient_id']==pid]['patient_name'].values[0]}")
                sel      = pats[pats["patient_id"] == sel_pid].iloc[0]
                is_sched = sel["status"] == "scheduled"

                if is_sched:
                    st.markdown('<div class="alert-warning">This patient is already scheduled. Only the name can be updated.</div>', unsafe_allow_html=True)

                new_name = st.text_input("Name", value=sel["patient_name"])
                if not is_sched:
                    new_urg = st.selectbox("Urgency", ["high","medium","low"],
                        index=["high","medium","low"].index(sel["urgency"]), format_func=str.capitalize)
                    new_dur = st.number_input("Duration (hours)", 0.5, 12.0, float(sel["duration"]), 0.5)
                else:
                    new_urg, new_dur = sel["urgency"], float(sel["duration"])

                if st.button("Update Patient", key="btn_upd"):
                    pats = load_patients()
                    idx  = pats[pats["patient_id"] == sel_pid].index[0]
                    pats.at[idx, "patient_name"] = new_name.strip()
                    if not is_sched:
                        pats.at[idx, "urgency"]  = new_urg
                        pats.at[idx, "duration"] = new_dur
                    save_patients(pats)
                    add_log("system", f"Patient #{sel_pid} updated.", "success")
                    st.markdown(f'<div class="alert-success">Patient <strong>#{sel_pid}</strong> updated successfully.</div>', unsafe_allow_html=True)
                    time.sleep(0.4); st.rerun()

        elif action == "Allocate Rooms":
            st.markdown("#### Allocate Unscheduled Patients")
            pats        = load_patients()
            unscheduled = pats[pats["status"]=="not_scheduled"] if not pats.empty else pd.DataFrame()

            if unscheduled.empty:
                st.markdown('<div class="alert-success">All patients are already scheduled.</div>', unsafe_allow_html=True)
            else:
                st.markdown(f'<div class="alert-warning"><strong>{len(unscheduled)} patient(s)</strong> awaiting allocation, ordered by urgency.</div>', unsafe_allow_html=True)
                st.markdown("<br>", unsafe_allow_html=True)
                for _, r in unscheduled.sort_values("urgency", key=lambda s: s.map(URGENCY_ORDER)).iterrows():
                    urg = r["urgency"].lower()
                    acc = URGENCY_ACCENT.get(urg, "#64748b")
                    st.markdown(f'<div style="font-size:0.86rem;margin-bottom:4px"><span style="color:{acc};font-weight:700">{urg.upper()}</span> &nbsp;&nbsp; <strong>#{r["patient_id"]}</strong> {r["patient_name"]} &nbsp;&middot;&nbsp; {r["duration"]}h</div>', unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)
                if st.button("Allocate Rooms Now", key="btn_alloc"):
                    pats   = load_patients()
                    rms    = load_rooms()
                    unsched = pats[pats["status"]=="not_scheduled"].copy()
                    unsched = unsched.sort_values("urgency", key=lambda s: s.map(URGENCY_ORDER))
                    room_next = {room: "12:00" for room in ROOMS_LIST}
                    if not rms.empty:
                        for room in ROOMS_LIST:
                            r_slots = rms[rms["room_id"]==room]
                            if not r_slots.empty:
                                cand = add_minutes(r_slots["end_time"].max(), GAP_MINUTES)
                                if cand > room_next[room]: room_next[room] = cand
                    new_allocs, room_idx = [], 0
                    for _, pat in unsched.iterrows():
                        rid   = ROOMS_LIST[room_idx % len(ROOMS_LIST)]
                        start = room_next[rid]
                        end   = add_minutes(start, duration_to_minutes(pat["duration"]))
                        room_next[rid] = add_minutes(end, GAP_MINUTES)
                        new_allocs.append({"room_id":rid,"patient_id":str(pat["patient_id"]),"start_time":start,"end_time":end})
                        pats.loc[pats["patient_id"]==pat["patient_id"], "status"] = "scheduled"
                        room_idx += 1
                    save_patients(pats)
                    save_rooms(pd.concat([rms, pd.DataFrame(new_allocs)], ignore_index=True))
                    add_log("system", f"Allocated {len(new_allocs)} patients.", "success")
                    st.markdown(f'<div class="alert-success">Allocated <strong>{len(new_allocs)} patient(s)</strong> to operating rooms.</div>', unsafe_allow_html=True)
                    time.sleep(0.4); st.rerun()

        elif action == "Delete Patient":
            st.markdown("#### Delete Patient")
            pats = load_patients()
            if pats.empty:
                st.markdown('<div class="alert-info">No patients to delete.</div>', unsafe_allow_html=True)
            else:
                del_pid = st.selectbox("Select Patient to Delete", pats["patient_id"].tolist(),
                    format_func=lambda pid: f"#{pid} — {pats[pats['patient_id']==pid]['patient_name'].values[0]}")
                
                if st.button("Delete Patient", key="btn_del"):
                    # Use tools.py logic directly or inline it
                    from tools import delete_patient
                    res = delete_patient(int(del_pid))
                    if res["status"] == "success":
                        add_log("system", f"Patient #{del_pid} deleted.", "success")
                        st.markdown(f'<div class="alert-success">Patient <strong>#{del_pid}</strong> deleted successfully.</div>', unsafe_allow_html=True)
                    else:
                        add_log("system", f"Error deleting patient #{del_pid}: {res['message']}", "error")
                        st.markdown(f'<div class="alert-error">Error: {res["message"]}</div>', unsafe_allow_html=True)
                    time.sleep(0.4); st.rerun()

        elif action == "Unschedule Patient":
            st.markdown("#### Unschedule Patient")
            pats = load_patients()
            sched_pats = pats[pats["status"] == "scheduled"]
            if sched_pats.empty:
                st.markdown('<div class="alert-info">No scheduled patients to unschedule.</div>', unsafe_allow_html=True)
            else:
                unsched_pid = st.selectbox("Select Patient to Unschedule", sched_pats["patient_id"].tolist(),
                    format_func=lambda pid: f"#{pid} — {sched_pats[sched_pats['patient_id']==pid]['patient_name'].values[0]}")
                
                if st.button("Unschedule Patient", key="btn_unsched"):
                    from tools import unschedule_patient
                    res = unschedule_patient(int(unsched_pid))
                    if res["status"] == "success":
                        add_log("system", f"Patient #{unsched_pid} unscheduled.", "success")
                        st.markdown(f'<div class="alert-success">Patient <strong>#{unsched_pid}</strong> unscheduled successfully.</div>', unsafe_allow_html=True)
                    else:
                        add_log("system", f"Error unscheduling patient #{unsched_pid}: {res['message']}", "error")
                        st.markdown(f'<div class="alert-error">Error: {res["message"]}</div>', unsafe_allow_html=True)
                    time.sleep(0.4); st.rerun()

    with right_col:
        st.markdown("#### Current Patient List")
        pats_disp = load_patients()
        rooms_df  = load_rooms()
        sched_pids = rooms_df["patient_id"].str.strip().tolist() if not rooms_df.empty else []
        
        if pats_disp.empty:
            st.markdown('<div class="alert-info">No patients registered.</div>', unsafe_allow_html=True)
        else:
            for _, row in pats_disp.iterrows():
                pid = str(row["patient_id"]).strip()
                rr  = rooms_df[rooms_df["patient_id"] == pid].iloc[0] if pid in sched_pids else None
                
                urg  = str(row["urgency"]).lower()
                stat = str(row["status"]).lower()
                accent = URGENCY_ACCENT.get(urg, "#64748b")
                
                room_info = (
                    f'<span style="font-family:\\\'JetBrains Mono\\\',monospace;font-size:0.78rem;color:#1d4ed8">'
                    f'{rr["room_id"].upper()} &nbsp; {rr["start_time"]} &ndash; {rr["end_time"]}</span>'
                ) if rr is not None else ""
                
                st.markdown(f"""<div class="pat-row" style="--accent-left:{accent}; margin-bottom:0.5rem; padding:0.6rem 0.8rem;">
<div style="display:flex;align-items:center;gap:1.1rem;flex:1">
<div class="pat-id">#{pid}</div>
<div>
<div class="pat-name" style="font-size:0.9rem;">{row['patient_name']}</div>
<div class="pat-meta" style="font-size:0.75rem;">{row['date']} &nbsp;&middot;&nbsp; {row['duration']}h surgery</div>
</div>
</div>
<div style="display:flex;align-items:center;gap:0.75rem">{room_info}
<span class="badge badge-{urg}">{urg.upper()}</span>
<span class="badge badge-{stat.replace(' ','_')}">{stat.replace('_',' ').upper()}</span>
</div>
</div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — Safety Controls (Existing logic intact)
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    st.markdown('<div class="section-title">Safety Controls</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="alert-info" style="margin-bottom:1.5rem">
        These controls mirror the admin commands exposed by <strong>planner.py</strong> and <strong>agent.py</strong>.
        Closing a room or marking a surgeon absent will prevent the planner from scheduling into those slots.
        Forbidden actions are blocked before they reach the worker.
    </div>""", unsafe_allow_html=True)

    sc1, sc2, sc3 = st.columns(3)

    # Room status
    with sc1:
        st.markdown("##### Room Status")
        for room in ROOMS_LIST:
            is_closed = room in st.session_state.closed_rooms
            st.markdown(f"""
            <div class="safety-row">
                <span style="font-weight:600">{room.upper()}</span>
                <span class="{'ind-closed' if is_closed else 'ind-open'}">{'CLOSED' if is_closed else 'OPEN'}</span>
            </div>""", unsafe_allow_html=True)
            if st.button("Open" if is_closed else "Close", key=f"toggle_{room}"):
                if is_closed:
                    st.session_state.closed_rooms.discard(room)
                    add_log("system", f"{room} opened.", "success")
                    run_admin_cmd(f"open_room:{room}")
                else:
                    st.session_state.closed_rooms.add(room)
                    add_log("system", f"{room} closed.", "info")
                    run_admin_cmd(f"close_room:{room}")
                st.rerun()

    # Surgeon availability
    with sc2:
        st.markdown("##### Surgeon Availability")
        absent = st.session_state.absent_surgeons
        if absent:
            for surg in list(absent):
                st.markdown(f"""
                <div class="safety-row">
                    <span>{surg}</span>
                    <span class="ind-closed">ABSENT</span>
                </div>""", unsafe_allow_html=True)
                if st.button(f"Mark Present", key=f"present_{surg}"):
                    st.session_state.absent_surgeons.remove(surg)
                    add_log("system", f"Surgeon {surg} marked present.", "success")
                    run_admin_cmd(f"surgeon_present:{surg}")
                    st.rerun()
        else:
            st.markdown('<div style="color:#a5a09a;font-size:0.84rem">No surgeons marked absent.</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        new_absent = st.text_input("Mark surgeon absent", placeholder="Surgeon name")
        if st.button("Mark Absent", key="btn_absent"):
            if new_absent.strip() and new_absent.strip() not in st.session_state.absent_surgeons:
                st.session_state.absent_surgeons.append(new_absent.strip())
                add_log("system", f"Surgeon {new_absent.strip()} marked absent.", "info")
                run_admin_cmd(f"surgeon_absent:{new_absent.strip()}")
                st.rerun()

    # Forbidden actions
    with sc3:
        st.markdown("##### Forbidden Actions")
        forbidden = st.session_state.forbidden_actions
        if forbidden:
            for act in list(forbidden):
                st.markdown(f"""
                <div class="safety-row">
                    <span style="font-family:'JetBrains Mono',monospace;font-size:0.8rem">{act}</span>
                    <span class="ind-closed">BLOCKED</span>
                </div>""", unsafe_allow_html=True)
                if st.button(f"Allow", key=f"allow_{act}"):
                    st.session_state.forbidden_actions.discard(act)
                    add_log("system", f"Action '{act}' allowed.", "success")
                    st.rerun()
        else:
            st.markdown('<div style="color:#a5a09a;font-size:0.84rem">No actions currently forbidden.</div>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        new_forbidden = st.selectbox("Forbid an action", ["-- select --","add_patient","allocate_rooms","update_patient"], key="forbid_sel")
        if st.button("Forbid Action", key="btn_forbid"):
            if new_forbidden != "-- select --":
                st.session_state.forbidden_actions.add(new_forbidden)
                add_log("system", f"Action '{new_forbidden}' forbidden.", "info")
                st.rerun()

# ══════════════════════════════════════════════════════════════════════════════
# TAB 7 — Analytics & Metrics
# ══════════════════════════════════════════════════════════════════════════════
with tab7:
    st.markdown('<div class="section-title">System Analytics & Metrics</div>', unsafe_allow_html=True)
    
    an_pats = load_patients()
    an_rooms = load_rooms()
    
    if an_pats.empty:
        st.info("No data available for analytics.")
    else:
        mc1, mc2, mc3 = st.columns(3)
        with mc1:
            st.markdown("#### Urgency Breakdown")
            urg_counts = an_pats['urgency'].value_counts().reset_index()
            urg_counts.columns = ['Urgency', 'Count']
            st.bar_chart(urg_counts.set_index('Urgency')['Count'], color="#0369a1")
            
        with mc2:
            st.markdown("#### Scheduling Status")
            stat_counts = an_pats['status'].value_counts().reset_index()
            stat_counts.columns = ['Status', 'Count']
            st.bar_chart(stat_counts.set_index('Status')['Count'], color="#7c3aed")
            
        with mc3:
            st.markdown("#### Expected Surgery Duration")
            if not an_rooms.empty and not an_pats.empty:
                # Merge rooms with patients to get the duration for each scheduled patient
                an_rooms['patient_id'] = an_rooms['patient_id'].astype(str).str.strip()
                an_pats['patient_id'] = an_pats['patient_id'].astype(str).str.strip()
                merged = pd.merge(an_rooms, an_pats, on='patient_id', how='left')
                merged['duration'] = pd.to_numeric(merged['duration'], errors='coerce').fillna(0)
                room_hours = merged.groupby('room_id')['duration'].sum().reset_index()
                st.bar_chart(room_hours.set_index('room_id')['duration'], color="#dc2626")
            else:
                st.info("No scheduled rooms yet.")
                
        st.markdown("<hr style='margin: 2rem 0; border: none; border-top: 1px solid #e0dbd2'>", unsafe_allow_html=True)
        
        # Second row of metrics
        st.markdown("#### Workload Metrics")
        w1, w2, w3 = st.columns(3)
        
        # Ensure duration is numeric before math operations
        an_pats['duration'] = pd.to_numeric(an_pats['duration'], errors='coerce').fillna(0)
        
        avg_dur = an_pats['duration'].mean() if not an_pats.empty else 0
        tot_dur = an_pats['duration'].sum() if not an_pats.empty else 0
        unsched_dur = an_pats[an_pats['status'] != 'scheduled']['duration'].sum() if not an_pats.empty else 0
        
        with w1:
            st.metric("Total Pending Workload", f"{tot_dur:.1f} Hours", help="Total hours of surgery required for all patients")
        with w2:
            st.metric("Average Surgery Length", f"{avg_dur:.1f} Hours", help="Average duration per patient")
        with w3:
            st.metric("Unscheduled Backlog", f"{unsched_dur:.1f} Hours", help="Hours of surgery waiting to be scheduled")

        st.markdown("<hr style='margin: 2rem 0; border: none; border-top: 1px solid #e0dbd2'>", unsafe_allow_html=True)
        st.markdown("#### Algorithmic Efficiency (BT vs DP)")
        st.markdown("Run a live computational analysis comparing standard Backtracking (BT) with Dynamic Programming (DP) for our constraint satisfaction engine.")
        
        if st.button("▶ Run Metrics Comparison", key="run_metrics_btn"):
            with st.spinner("Running performance analysis..."):
                try:
                    import sys
                    if BASE_DIR not in sys.path: sys.path.append(BASE_DIR)
                    from metrics import compare_algorithms
                    
                    # Create dummy lists proportional to our load to simulate the complexity
                    test_pats = list(range(max(5, len(an_pats))))
                    test_rooms = list(range(len(ROOM_COLORS)))
                    
                    res = compare_algorithms(test_pats, test_rooms)
                    
                    st.success("Analysis Complete!")
                    c1, c2, c3, c4 = st.columns(4)
                    c1.metric("Backtracking Time", f"{res['bt_time']:.6f} s")
                    c2.metric("DP Time", f"{res['dp_time']:.6f} s", delta=f"{(res['bt_time'] - res['dp_time']):.6f}s faster" if res['dp_faster'] else "")
                    c3.metric("BT States Explored", f"{res['bt_states']}")
                    c4.metric("DP States Explored", f"{res['dp_states']}")
                    
                    if res['dp_faster']:
                        st.markdown('<div class="alert-success"><strong>Verdict:</strong> Dynamic Programming is faster and explores fewer redundant states thanks to caching.</div>', unsafe_allow_html=True)
                    else:
                        st.markdown('<div class="alert-info"><strong>Verdict:</strong> Backtracking was faster for this specific load size.</div>', unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Error running metrics: {str(e)}")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:1.2rem 0 0.8rem;border-bottom:1px solid #e0dbd2;margin-bottom:1rem">
        <div style="font-family:'Cormorant Garamond',serif;font-size:1.35rem;font-weight:700;color:#1e3a5f">Hôpital Charles Nicolle</div>
        <div style="font-size:0.75rem;color:#64748b;margin-top:0.2rem;letter-spacing:0.05em">Healthcare Economy & OR Management</div>
    </div>""", unsafe_allow_html=True)

    # ── Tâche 2 & 3: Run Scenario Launcher ──
    st.markdown("**Run Scenario (Test Environments)**")
    scenario_options = {
        "Normal": "scenario_normal", 
        "Failure (Rooms Closed)": "scenario_rooms_closed", 
        "Tool Blocked": "scenario_tool_blocked", 
        "Preemption": "scenario_preemption", 
        "Random Failure": "scenario_random_failure", 
        "Timeout": "scenario_timeout", 
        "Rate Limit": "scenario_rate_limit"
    }
    selected_scen = st.selectbox("Select Scenario", list(scenario_options.keys()), label_visibility="collapsed")
    if st.button("▶ Run Scenario", use_container_width=True):
        func_name = scenario_options[selected_scen]
        
        # Determine path dynamically
        scen_path = os.path.join(BASE_DIR, "scenario.py")
        if not os.path.exists(scen_path):
            scen_path = os.path.join(BASE_DIR, "orchestrator", "scenario.py")
            
        with st.spinner(f"Running {selected_scen}..."):
            subprocess.run(["python", "-c", f"import sys; sys.path.append('{BASE_DIR}'); from scenario import {func_name}; {func_name}()"], cwd=BASE_DIR)
        st.success("Scenario completed. Logs recorded in System Traces tab.")
        time.sleep(1)
        st.rerun()

    st.markdown("<br>", unsafe_allow_html=True)

    st.markdown("**Quick Stats**")
    pats_s = load_patients()
    for label, val, color in [
        ("High Urgency",   len(pats_s[pats_s["urgency"]=="high"])   if not pats_s.empty else 0, "#dc2626"),
        ("Medium Urgency", len(pats_s[pats_s["urgency"]=="medium"]) if not pats_s.empty else 0, "#b45309"),
        ("Low Urgency",    len(pats_s[pats_s["urgency"]=="low"])    if not pats_s.empty else 0, "#15803d"),
    ]:
        st.markdown(f"""
        <div style="display:flex;justify-content:space-between;padding:0.45rem 0;
                    border-bottom:1px solid #e8e3db;font-size:0.84rem">
            <span>{label}</span><strong style="color:{color}">{val}</strong>
        </div>""", unsafe_allow_html=True)
    st.markdown(f"""
    <div style="display:flex;justify-content:space-between;padding:0.5rem 0;font-size:0.84rem">
        <strong>Total</strong><strong>{len(pats_s)}</strong>
    </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**Room Occupancy**")
    rms_s = load_rooms()
    for room, color in ROOM_COLORS.items():
        cnt        = len(rms_s[rms_s["room_id"]==room]) if not rms_s.empty else 0
        closed_tag = " &mdash; CLOSED" if room in st.session_state.closed_rooms else ""
        st.markdown(f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
                    margin-bottom:0.4rem;background:#f9f7f4;border:1px solid #e0dbd2;
                    border-left:3px solid {color};border-radius:5px;
                    padding:0.45rem 0.7rem;font-size:0.82rem">
            <span><strong>{room.upper()}</strong>{closed_tag}</span>
            <span>{cnt} patient{'s' if cnt!=1 else ''}</span>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button("Refresh Data", use_container_width=True):
        st.rerun()

    st.markdown(f"""
    <div style="font-size:0.73rem;color:#a5a09a;border-top:1px solid #e0dbd2;
                padding-top:0.8rem;margin-top:0.8rem;line-height:1.7">
        Pipeline: Planner &rarr; Worker &rarr; Critic &rarr; Orchestrator<br>
        Backtracking + Preemption active<br>
        Last update: {datetime.now().strftime('%H:%M:%S')}
    </div>""", unsafe_allow_html=True)
