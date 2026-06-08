import json
import sqlite3
import streamlit as st
from collections import Counter

# =====================================================================
# 1. Grundlegende Seiteneinrichtung
# =====================================================================
st.set_page_config(page_title="Service Sonar | Command Center", layout="wide", initial_sidebar_state="collapsed")

# =====================================================================
# 2. Premium Dark Mode & Enterprise SaaS CSS
# =====================================================================
custom_css = """<style>
/* Ausblenden des Standard-Headers und Footers von Streamlit */
[data-testid="stHeader"] { display: none !important; }
footer { display: none !important; }

/* Extrem dunkler Hintergrund (Zinc 950) für High-End SaaS Look */
[data-testid="stAppViewContainer"], .stApp { background-color: #09090b !important; color: #e4e4e7; }

@import url('https://fonts.googleapis.com/css2?family=Geist:wght@300;400;600&family=JetBrains+Mono:wght@400;700&display=swap');

.block-container { font-family: 'Geist', -apple-system, sans-serif; padding-top: 2rem !important; max-width: 1400px; }

/* Dashboard Header Design */
.dash-header { border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 15px; margin-bottom: 30px; display: flex; justify-content: space-between; align-items: flex-end; }
.dash-title { font-size: 28px; font-weight: 600; color: #ffffff; margin: 0; letter-spacing: -0.5px; }
.dash-subtitle { font-size: 12px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 2px; }
.status-indicator { font-size: 12px; color: #10b981; display: flex; align-items: center; gap: 8px; font-family: 'JetBrains Mono', monospace; }
.pulse-dot { width: 8px; height: 8px; background-color: #10b981; border-radius: 50%; box-shadow: 0 0 12px #10b981; }

/* Bento Card Style (Glasmorphismus) */
.bento-card { background: #18181b; border: 1px solid #27272a; border-radius: 12px; padding: 24px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); height: 100%; }
.bento-card-glow { border-top: 2px solid #3b82f6; }

/* Typografie */
.metric-value { font-size: 56px; font-weight: 700; color: #ffffff; line-height: 1; font-family: 'JetBrains Mono', monospace; }
.metric-label { font-size: 12px; color: #a1a1aa; text-transform: uppercase; letter-spacing: 1px; margin-top: 12px; }
.sec-label { font-size: 11px; color: #71717a; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 6px; margin-top: 24px; }
.main-text { font-size: 15px; color: #d4d4d8; line-height: 1.6; }
.highlight { font-size: 18px; font-weight: 600; color: #60a5fa; }

/* Konsolen-Look für Code-Boxen */
.console-box { background: #000000; border: 1px solid #27272a; border-radius: 8px; padding: 16px; font-family: 'JetBrains Mono', monospace; font-size: 13px; color: #a1a1aa; margin-bottom: 16px; }
.console-header { color: #52525b; font-size: 11px; margin-bottom: 8px; border-bottom: 1px solid #27272a; padding-bottom: 4px; display: flex; justify-content: space-between; }

/* Tabs Styling */
.stTabs [data-baseweb="tab-list"] { background-color: transparent; gap: 24px; }
.stTabs [data-baseweb="tab"] { color: #a1a1aa; border-bottom-color: transparent !important; }
.stTabs [aria-selected="true"] { color: #ffffff !important; border-bottom-color: #3b82f6 !important; }
</style>"""
st.markdown(custom_css, unsafe_allow_html=True)

# =====================================================================
# 3. Datenbank-Verbindung & Hilfsfunktionen
# =====================================================================
DB_FILE = "service_sonar.db"

def get_db_records(status_code, limit=50):
    """Holt die aktuellsten Einträge basierend auf ihrem Status-Code."""
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT id, raw_content, cleaned_content, analysis_json FROM forum_posts WHERE status = ? ORDER BY id DESC LIMIT ?", (status_code, limit))
        data = cursor.fetchall()
        conn.close()
        return data
    except sqlite3.OperationalError:
        return []

# =====================================================================
# 4. Header UI
# =====================================================================
st.markdown("""<div class="dash-header">
<div>
    <div class="dash-subtitle">SYSTEM OPERATIONS COMMAND</div>
    <div class="dash-title">Service Sonar</div>
</div>
<div class="status-indicator">
    <div class="pulse-dot"></div> SYSTEM ONLINE
</div>
</div>""", unsafe_allow_html=True)

# =====================================================================
# 5. Interaktive Tabs
# =====================================================================
tab1, tab2, tab3, tab4 = st.tabs([
    "Deep Scraper (Agent 1)", 
    "Cleaner (Agent 2)", 
    "Analyzer (Agent 3)", 
    "Innovator Dashboard"
])

# --- Tab 1: Rohdaten ---
with tab1:
    st.markdown('<div class="sec-label" style="margin-top:0;">Raw Data Stream (DOM Extraction)</div>', unsafe_allow_html=True)
    raw_records = get_db_records(0, 5)
    if not raw_records:
        st.info("Keine Rohdaten (Status 0) vorhanden. Bitte Agent 1 ausführen.")
    else:
        for db_id, raw_text, _, _ in raw_records:
            st.markdown(f"""<div class="console-box">
<div class="console-header"><span>STREAM_ID: {db_id}</span><span>STATUS: 0</span></div>
<div style="color: #d4d4d8;">{raw_text[:300]}...</div>
</div>""", unsafe_allow_html=True)

# --- Tab 2: Bereinigte Daten ---
with tab2:
    st.markdown('<div class="sec-label" style="margin-top:0;">Privacy & Noise Reduction Filter</div>', unsafe_allow_html=True)
    cleaned_records = get_db_records(1, 5)
    if not cleaned_records:
        st.info("Keine bereinigten Daten (Status 1) vorhanden. Bitte Agent 2 ausführen.")
    else:
        for db_id, _, cleaned_text, _ in cleaned_records:
            st.markdown(f"""<div class="console-box" style="border-color: #064e3b; background: rgba(6,78,59,0.1);">
<div class="console-header" style="border-color: #064e3b; color: #10b981;"><span>STREAM_ID: {db_id}</span><span>STATUS: 1 [CLEAN]</span></div>
<div style="color: #a1a1aa;">{cleaned_text}</div>
</div>""", unsafe_allow_html=True)

# --- Tab 3: Semantische Analyse ---
with tab3:
    st.markdown('<div class="sec-label" style="margin-top:0;">Vector Space Mapping & Structuring</div>', unsafe_allow_html=True)
    analyzed_records = get_db_records(2, 5)
    if not analyzed_records:
        st.info("Keine analysierten Daten (Status 2) vorhanden. Bitte Agent 3 ausführen.")
    else:
        for db_id, _, cleaned_text, json_str in analyzed_records:
            st.markdown(f"""<div class="console-box" style="border-left: 2px solid #6366f1;">
<div class="console-header"><span>TARGET_ID: {db_id}</span><span>STATUS: 2 [MAPPED]</span></div>
<div style="margin-bottom: 12px; color: #d4d4d8;">{cleaned_text}</div>
<div style="background: #000; padding: 10px; border-radius: 4px; color: #38bdf8;">{json_str}</div>
</div>""", unsafe_allow_html=True)

# --- Tab 4: Dynamisches Innovator Dashboard ---
with tab4:
    # Dynamische Berechnung der Anomalien aus Agent 3
    all_analyzed = get_db_records(2, 500)
    signal_count = len(all_analyzed) if all_analyzed else 0

    # Holt den aktuellsten generierten Bericht von Agent 4 aus der Datenbank
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT report_json FROM system_reports ORDER BY id DESC LIMIT 1")
        report_row = cursor.fetchone()
        conn.close()
    except sqlite3.OperationalError:
        report_row = None

    if not report_row:
        st.warning("Noch kein LLM-Innovationsbericht generiert. Bitte Agent 4 ausführen.")
    else:
        try:
            # Parsen der LLM JSON-Antwort von Agent 4
            ai_insight = json.loads(report_row[0])
            
            col1, col2 = st.columns([1, 2.5], gap="large")

            with col1:
                st.markdown(f"""<div class="bento-card">
<div class="metric-value">{signal_count}</div>
<div class="metric-label">Anomalies Detected</div>
<div class="sec-label">Data Origin</div>
<div class="main-text" style="font-size: 13px; font-family: 'JetBrains Mono', monospace;">Live aus SQLite Datenbank<br>Status: 2 (Verifiziert)</div>
</div>""", unsafe_allow_html=True)

            with col2:
                st.markdown(f"""<div class="bento-card bento-card-glow">
<div class="sec-label" style="margin-top: 0;">Emergent Vector Cluster (KI-Analysiert)</div>
<div class="highlight">{ai_insight.get('cluster', 'N/A')}</div>

<div class="sec-label">Synthesized Service Opportunity (LLM-Generiert)</div>
<div class="highlight" style="color: #ffffff; font-size: 24px;">{ai_insight.get('opportunity', 'N/A')}</div>

<div class="sec-label">Architecture / Concept</div>
<div class="main-text">{ai_insight.get('solution', 'N/A')}</div>

<div style="display: flex; gap: 60px; margin-top: 30px; border-top: 1px solid #27272a; padding-top: 20px;">
    <div>
        <div class="sec-label" style="margin-top: 0;">Target Group</div>
        <div class="main-text" style="font-size: 14px;">{ai_insight.get('target', 'N/A')}</div>
    </div>
    <div>
        <div class="sec-label" style="margin-top: 0;">System Owner / Stakeholder</div>
        <div class="main-text" style="font-size: 14px;">{ai_insight.get('stakeholder', 'N/A')}</div>
    </div>
</div>
</div>""", unsafe_allow_html=True)
        except json.JSONDecodeError:
            st.error("Fehler beim Parsen der LLM-Antwort. Ungültiges JSON-Format.")