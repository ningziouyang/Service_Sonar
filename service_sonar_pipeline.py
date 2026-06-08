import json
import sqlite3
import streamlit as st

# 1. Grundlegende Seiteneinrichtung
st.set_page_config(page_title="Service Sonar | Command Center", layout="wide", initial_sidebar_state="collapsed")

# 2. Premium Dark Mode & Enterprise SaaS CSS
custom_css = """<style>
/* 🔴 HIER IST DER FIX: Streamlit-Standard-Header (den weißen Balken) komplett ausblenden */
[data-testid="stHeader"] {
    display: none !important;
}
footer {
    display: none !important;
}

/* Hintergrund extrem dunkel (Zinc 950) für High-End SaaS Look */
[data-testid="stAppViewContainer"], .stApp {
    background-color: #09090b !important; 
    color: #e4e4e7;
}

/* Moderne Schriftarten importieren */
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;600&family=JetBrains+Mono:wght@400;700&display=swap');

.block-container {
    font-family: 'Geist', -apple-system, sans-serif;
    padding-top: 2rem !important; /* Etwas mehr Abstand nach oben, da der Header weg ist */
    max-width: 1400px;
}

/* Dashboard Header - Minimalistisch und Technisch */
.dash-header {
    border-bottom: 1px solid rgba(255,255,255,0.1);
    padding-bottom: 15px;
    margin-bottom: 30px;
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
}
.dash-title { 
    font-size: 28px; 
    font-weight: 600; 
    color: #ffffff; 
    margin: 0; 
    letter-spacing: -0.5px; 
}
.dash-subtitle { 
    font-size: 12px; 
    color: #a1a1aa; 
    text-transform: uppercase; 
    letter-spacing: 2px; 
}
.status-indicator { 
    font-size: 12px; 
    color: #10b981; 
    display: flex; 
    align-items: center; 
    gap: 8px;
    font-family: 'JetBrains Mono', monospace;
}
.pulse-dot { 
    width: 8px; 
    height: 8px; 
    background-color: #10b981; 
    border-radius: 50%; 
    box-shadow: 0 0 12px #10b981; 
}

/* Bento Card Style - Glasmorphismus & dunkle Rahmen */
.bento-card {
    background: #18181b;
    border: 1px solid #27272a;
    border-radius: 12px;
    padding: 24px;
    box-shadow: 0 10px 30px rgba(0,0,0,0.5);
    height: 100%;
}
.bento-card-glow {
    border-top: 2px solid #3b82f6; /* Dezenter blauer Akzent oben */
}

/* Typografie für Daten und Metriken */
.metric-value { 
    font-size: 56px; 
    font-weight: 700; 
    color: #ffffff; 
    line-height: 1; 
    font-family: 'JetBrains Mono', monospace; 
}
.metric-label { 
    font-size: 12px; 
    color: #a1a1aa; 
    text-transform: uppercase; 
    letter-spacing: 1px; 
    margin-top: 12px; 
}
.sec-label { 
    font-size: 11px; 
    color: #71717a; 
    text-transform: uppercase; 
    letter-spacing: 1px; 
    margin-bottom: 6px; 
    margin-top: 24px; 
}
.main-text { 
    font-size: 15px; 
    color: #d4d4d8; 
    line-height: 1.6; 
}
.highlight { 
    font-size: 18px; 
    font-weight: 600; 
    color: #60a5fa; 
}

/* Konsolen-Look für Raw-Daten (Agent 1-3) */
.console-box {
    background: #000000;
    border: 1px solid #27272a;
    border-radius: 8px;
    padding: 16px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: #a1a1aa;
    margin-bottom: 16px;
}
.console-header { 
    color: #52525b; 
    font-size: 11px; 
    margin-bottom: 8px; 
    border-bottom: 1px solid #27272a; 
    padding-bottom: 4px;
    display: flex;
    justify-content: space-between;
}
.json-key { color: #38bdf8; }
.json-string { color: #a3e635; }

/* Streamlit Tabs anpassen */
.stTabs [data-baseweb="tab-list"] {
    background-color: transparent;
    gap: 24px;
}
.stTabs [data-baseweb="tab"] {
    color: #a1a1aa;
    border-bottom-color: transparent !important;
}
.stTabs [aria-selected="true"] {
    color: #ffffff !important;
    border-bottom-color: #3b82f6 !important;
}
</style>"""
st.markdown(custom_css, unsafe_allow_html=True)

# 3. Datenbank-Verbindung
DB_FILE = "service_sonar.db"

def get_db_records(status_code, limit=5):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, raw_content, cleaned_content, analysis_json FROM forum_posts WHERE status = ? LIMIT ?", (status_code, limit))
        data = cursor.fetchall()
        conn.close()
        return data
    except sqlite3.OperationalError:
        return []

# 4. Header: System Command Center
st.markdown("""<div class="dash-header">
<div>
    <div class="dash-subtitle">SYSTEM OPERATIONS COMMAND</div>
    <div class="dash-title">Service Sonar</div>
</div>
<div class="status-indicator">
    <div class="pulse-dot"></div> SYSTEM ONLINE
</div>
</div>""", unsafe_allow_html=True)

# 5. Cleane Tabs ohne Emoji
tab1, tab2, tab3, tab4 = st.tabs([
    "Deep Scraper", 
    "Cleaner", 
    "Analyzer", 
    "Innovator"
])

with tab1:
    st.markdown('<div class="sec-label" style="margin-top:0;">Raw Data Stream (DOM Extraction)</div>', unsafe_allow_html=True)
    raw_records = get_db_records(0, 5)
    if not raw_records:
        st.info("Awaiting data stream...")
    else:
        for db_id, raw_text, _, _ in raw_records:
            st.markdown(f"""<div class="console-box">
<div class="console-header"><span>STREAM_ID: {db_id}</span><span>STATUS: 0</span></div>
<div style="color: #d4d4d8;">{raw_text}</div>
</div>""", unsafe_allow_html=True)

with tab2:
    st.markdown('<div class="sec-label" style="margin-top:0;">Privacy & Noise Reduction Filter</div>', unsafe_allow_html=True)
    cleaned_records = get_db_records(1, 5)
    if not cleaned_records:
        st.info("Awaiting sanitization output...")
    else:
        for db_id, _, cleaned_text, _ in cleaned_records:
            st.markdown(f"""<div class="console-box" style="border-color: #064e3b; background: rgba(6,78,59,0.1);">
<div class="console-header" style="border-color: #064e3b; color: #10b981;"><span>STREAM_ID: {db_id}</span><span>STATUS: 1 [CLEAN]</span></div>
<div style="color: #a1a1aa;">{cleaned_text}</div>
</div>""", unsafe_allow_html=True)

with tab3:
    st.markdown('<div class="sec-label" style="margin-top:0;">Vector Space Mapping & Structuring</div>', unsafe_allow_html=True)
    analyzed_records = get_db_records(2, 3)
    if not analyzed_records:
        st.info("Awaiting semantic mapping...")
    else:
        for db_id, _, cleaned_text, json_str in analyzed_records:
            st.markdown(f"""<div class="console-box" style="border-left: 2px solid #6366f1;">
<div class="console-header"><span>TARGET_ID: {db_id}</span><span>STATUS: 2 [MAPPED]</span></div>
<div style="margin-bottom: 12px; color: #d4d4d8;">{cleaned_text}</div>
<div style="background: #000; padding: 10px; border-radius: 4px; color: #38bdf8;">{json_str if json_str else '{"cluster": "unassigned", "confidence": 0.0}'}</div>
</div>""", unsafe_allow_html=True)

with tab4:
    # Dummy-Daten
    agent4_mock_output = {
        "cluster": "Bürokratie & Formular-Überforderung",
        "signal_count": "45",
        "origin": "Unstructured anomalies in cluster 'Sonstiges'",
        "opportunity": "Bürokratie-Navigator",
        "solution": "Autonomes Assistenz-System zur schrittweisen Navigation durch hochschulinterne und staatliche Formularlandschaften.",
        "target": "Immatrikulierte Erstsemester, Internationals",
        "stakeholder": "Studierendenwerk, Prüfungsamt"
    }

    col1, col2 = st.columns([1, 2.5], gap="large")

    with col1:
        st.markdown(f"""<div class="bento-card">
<div class="metric-value">{agent4_mock_output['signal_count']}</div>
<div class="metric-label">Anomalies Detected</div>
<div class="sec-label">Data Origin</div>
<div class="main-text" style="font-size: 13px; font-family: 'JetBrains Mono', monospace;">{agent4_mock_output['origin']}</div>
</div>""", unsafe_allow_html=True)

    with col2:
        st.markdown(f"""<div class="bento-card bento-card-glow">
<div class="sec-label" style="margin-top: 0;">Emergent Vector Cluster</div>
<div class="highlight">{agent4_mock_output['cluster']}</div>

<div class="sec-label">Synthesized Service Opportunity</div>
<div class="highlight" style="color: #ffffff; font-size: 24px;">{agent4_mock_output['opportunity']}</div>

<div class="sec-label">Architecture / Concept</div>
<div class="main-text">{agent4_mock_output['solution']}</div>

<div style="display: flex; gap: 60px; margin-top: 30px; border-top: 1px solid #27272a; padding-top: 20px;">
    <div>
        <div class="sec-label" style="margin-top: 0;">Target Group</div>
        <div class="main-text" style="font-size: 14px;">{agent4_mock_output['target']}</div>
    </div>
    <div>
        <div class="sec-label" style="margin-top: 0;">System Owner / Stakeholder</div>
        <div class="main-text" style="font-size: 14px;">{agent4_mock_output['stakeholder']}</div>
    </div>
</div>
</div>""", unsafe_allow_html=True)