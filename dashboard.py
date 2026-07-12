import html
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from textwrap import dedent
import re
from agent4_innovator import Agent4Innovator

import streamlit as st


st.set_page_config(
    page_title="Service Sonar | Social Intelligence Platform",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DB_FILE = Path(__file__).with_name("service_sonar.db")


def sync_streamlit_secrets_to_env():
    """Expose Streamlit Cloud secrets as env vars for the agent modules."""
    secret_specs = {
        "GROQ_API_KEY": ("groq", "api_key"),
        "GROQ_BASE_URL": ("groq", "base_url"),
        "GROQ_MODEL": ("groq", "model"),
        "OPENAI_API_KEY": ("openai", "api_key"),
        "OPENAI_BASE_URL": ("openai", "base_url"),
        "OPENAI_MODEL": ("openai", "model"),
        "OPENROUTER_API_KEY": ("openrouter", "api_key"),
        "OPENROUTER_BASE_URL": ("openrouter", "base_url"),
        "OPENROUTER_MODEL": ("openrouter", "model"),
        "DEEPSEEK_API_KEY": ("deepseek", "api_key"),
        "DEEPSEEK_BASE_URL": ("deepseek", "base_url"),
        "DEEPSEEK_MODEL": ("deepseek", "model"),
        "OLLAMA_ENABLED": ("ollama", "enabled"),
        "OLLAMA_API_KEY": ("ollama", "api_key"),
        "OLLAMA_BASE_URL": ("ollama", "base_url"),
        "OLLAMA_MODEL": ("ollama", "model"),
        "AGENT4_PROVIDER_ORDER": ("agent4", "provider_order"),
        "AGENT4_MAX_RETRIES": ("agent4", "max_retries"),
        "AGENT4_RETRY_BASE_SECONDS": ("agent4", "retry_base_seconds"),
        "AGENT4_MAX_RETRY_SLEEP": ("agent4", "max_retry_sleep"),
        "AGENT4_TEMPERATURE": ("agent4", "temperature"),
    }

    def read_secret(mapping, names):
        if not hasattr(mapping, "get"):
            return None

        for name in names:
            try:
                value = mapping.get(name)
            except Exception:
                value = None

            if value:
                return value

        return None

    local_secret_paths = [
        Path.home() / ".streamlit" / "secrets.toml",
        Path(__file__).with_name(".streamlit") / "secrets.toml",
    ]

    if not any(path.exists() for path in local_secret_paths):
        return

    try:
        secrets = dict(st.secrets)
    except Exception:
        return

    for env_key, (section_name, short_name) in secret_specs.items():
        if os.getenv(env_key):
            continue

        root_names = (
            env_key,
            env_key.lower(),
            env_key.lower().replace("_", "-"),
        )
        value = read_secret(secrets, root_names)

        if not value:
            section_names = (
                section_name,
                section_name.upper(),
                section_name.capitalize(),
                "general",
                "llm",
                "agent4",
            )

            for candidate_section in section_names:
                try:
                    section = secrets.get(candidate_section)
                except Exception:
                    section = None

                if not section:
                    continue

                section_value_names = (
                    env_key,
                    env_key.lower(),
                    short_name,
                    short_name.upper(),
                )
                value = read_secret(section, section_value_names)
                if value:
                    break

        if value:
            os.environ[env_key] = str(value)


try:
    sync_streamlit_secrets_to_env()
except Exception:
    pass


STATUS_META = {
    -1: {
        "label": "Filtered out",
        "accent": "#E24B4A",
        "copy": "Noise, ads or irrelevant posts",
    },
    0: {
        "label": "Raw intake",
        "accent": "#534AB7",
        "copy": "Fresh forum posts from Agent 1",
    },
    1: {
        "label": "Cleaned queue",
        "accent": "#0F6E56",
        "copy": "Anonymized and ready for LLM analysis",
    },
    2: {
        "label": "Analyzed signals",
        "accent": "#EF9F27",
        "copy": "Structured by Agent 3",
    },
    3: {
        "label": "Human review",
        "accent": "#993556",
        "copy": "Sensitive cases waiting for review",
    },
}

CLUSTER_META = {
    "Finanzen": {
        "display": "Finanzstress & BAf&ouml;G",
        "short": "Finanzstress",
        "keywords": ["BAf&ouml;G", "Miete", "Nebenjob", "Schulden"],
        "diagnosis": "Financial pressure is not only a money problem. The signal points to paperwork friction, delayed aid, rent pressure and unclear fallback options.",
        "overlap": "Often reinforced by housing stress and study pressure.",
    },
    "Mentale Gesundheit": {
        "display": "Psychische Belastung",
        "short": "Psyche",
        "keywords": ["Burnout", "Isolation", "Angst", "Beratung"],
        "diagnosis": "The pattern suggests a preventive service gap: students ask for help when stress is already acute, while early low-threshold support is hard to find.",
        "overlap": "Often reinforced by exams, loneliness and financial insecurity.",
    },
    "Studium": {
        "display": "Studien- und Pr&uuml;fungsdruck",
        "short": "Studium",
        "keywords": ["Pr&uuml;fung", "Module", "Semester", "Orientierung"],
        "diagnosis": "Study-related signals cluster around uncertainty, decision pressure and late discovery of support options.",
        "overlap": "Often reinforced by psychological load and financial pressure.",
    },
    "Wohnen": {
        "display": "Wohnungsstress",
        "short": "Wohnen",
        "keywords": ["WG", "Wohnheim", "Miete", "Kaution"],
        "diagnosis": "Housing signals indicate a structural access problem: students need trust, speed and local knowledge at the exact moment they have the least of it.",
        "overlap": "Often reinforced by international access barriers and financial stress.",
    },
    "Sonstiges": {
        "display": "Weitere Signale",
        "short": "Sonstiges",
        "keywords": ["Orientierung", "Service", "Support"],
        "diagnosis": "The remaining signals are weaker individually, but useful as early probes for new service needs.",
        "overlap": "Potential overlaps should be reviewed once more data is analyzed.",
    },
}

URGENCY_RANK = {"Hoch": 3, "Mittel": 2, "Niedrig": 1}


CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,400;0,500;0,700;1,400&family=DM+Serif+Display:ital@0;1&display=swap');
@import url('https://cdn.jsdelivr.net/npm/@tabler/icons-webfont@3.10.0/dist/tabler-icons.min.css');

*, *::before, *::after { box-sizing: border-box; }
html{scroll-behavior:smooth;}
[data-testid="stAppViewContainer"]{scroll-behavior:smooth!important;}
[data-testid="stMain"]{scroll-behavior:smooth!important;}
.main{scroll-behavior:smooth!important;}
#pipeline,#dashboard,#cluster,#stakeholder,#innovation{scroll-margin-top:82px;}

:root {
  --p50:#EEEDFE; --p100:#CECBF6; --p200:#AFA9EC; --p600:#534AB7; --p800:#3C3489;
  --blue50:#E6F1FB; --blue600:#185FA5;
  --amb50:#FAEEDA; --amb400:#EF9F27; --amb600:#854F0B;
  --red50:#FCEBEB; --red400:#E24B4A; --red600:#A32D2D;
  --coral50:#FAECE7; --coral600:#993C1D;
  --pink50:#FBEAF0; --pink600:#993556;
  --grn50:#EAF3DE; --grn400:#639922; --grn600:#3B6D11;
  --teal50:#E1F5EE; --teal600:#0F6E56;
  --dark:#12112a; --dmid:#1e1c3a; --dcard:#2a2848; --dtag:#3a3860;
  --text:#1a1830; --muted:#5a5878; --light:#9896b8;
  --border:rgba(83,74,183,0.12); --bg:#f7f6ff;
  --rmd:10px; --rlg:18px; --rxl:28px; --max:1080px;
}

[data-testid="stHeader"] { display:none !important; }
footer { display:none !important; }
.stApp, [data-testid="stAppViewContainer"] {
  background:
    radial-gradient(circle at 8% 0%, rgba(175,169,236,.28), transparent 30%),
    radial-gradient(circle at 94% 12%, rgba(24,95,165,.12), transparent 26%),
    var(--bg) !important;
  color:var(--text);
}

.block-container {
  max-width:none !important;
  width:100% !important;
  padding:0 24px 0 !important;
  font-family:'DM Sans', -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
.block-container > div[data-testid="stVerticalBlock"]{gap:0!important;}
#MainMenu { visibility:hidden; }

.ss-shell { max-width:var(--max); margin:0 auto; }
.ss-nav {
  position:sticky; top:0; z-index:20; height:58px; margin:0 -24px;
  background:rgba(247,246,255,0.92); backdrop-filter:blur(16px);
  border-bottom:0.5px solid var(--border);
}
.ss-nav-inner {
  max-width:var(--max); height:100%; margin:0 auto; padding:0 36px;
  display:flex; align-items:center; justify-content:space-between; gap:20px;
}
.brand { display:flex; align-items:center; gap:10px; text-decoration:none; }
.brand-mark {
  width:30px; height:30px; background:var(--p600); border-radius:8px;
  display:grid; place-items:center; position:relative; overflow:hidden;
}
.brand-mark::before {
  content:''; position:absolute; width:18px; height:18px; border-radius:50%;
  border:2px solid rgba(255,255,255,0.9); animation:sonar 2.4s ease-out infinite;
}
.brand-mark::after { content:''; width:6px; height:6px; background:white; border-radius:50%; z-index:1; }
@keyframes sonar { 0%{transform:scale(.3);opacity:1} 100%{transform:scale(1.6);opacity:0} }
.brand-name { font-size:15px; font-weight:500; color:var(--text); }
.brand-name span { color:var(--p600); }
.nav-links { display:flex; gap:22px; align-items:center; }
.nav-links a { font-size:13px; color:var(--muted); text-decoration:none; transition:color .2s; }
.nav-links a:hover { color:var(--p600); }
.nav-btn {
  background:var(--p600); color:white !important; padding:8px 18px; border-radius:40px;
  font-size:13px; font-weight:500; text-decoration:none; transition:background .2s, transform .1s;
}
.nav-btn:hover { background:var(--p800); transform:translateY(-1px); }

.hero {
  margin:0 -24px; width:calc(100% + 48px); padding:80px 36px 68px;
  background:linear-gradient(150deg,#eceaff 0%,#ede8ff 35%,#e5eeff 70%,#eaf4ff 100%);
  border-bottom:0.5px solid var(--border);
}
.hero-inner { max-width:var(--max); margin:0 auto; }
.pill {
  display:inline-flex; align-items:center; gap:7px; font-size:12px; font-weight:500;
  letter-spacing:.06em; text-transform:uppercase; color:var(--p600);
  background:rgba(255,255,255,.55); border:0.5px solid rgba(83,74,183,.16);
  padding:6px 14px; border-radius:40px; margin-bottom:22px;
}
.hero h1 {
  font-family:'DM Serif Display', Georgia, serif; font-size:56px; line-height:1.05;
  font-weight:400; color:var(--text); max-width:690px; margin:0 0 20px;
  letter-spacing:0;
}
.hero h1 em { font-style:italic; color:var(--p600); }
.hero-sub { font-size:17px; color:var(--muted); max-width:610px; line-height:1.75; margin:0 0 36px; }
.hero-btns { display:flex; gap:12px; flex-wrap:wrap; margin-bottom:52px; }
.btn-p, .btn-s {
  border-radius:40px; padding:14px 26px; font-size:15px; font-weight:500;
  text-decoration:none; display:inline-flex; align-items:center; gap:8px; transition:transform .15s, background .2s;
}
.btn-p { background:var(--p600); color:white !important; }
.btn-p:hover { background:var(--p800); transform:translateY(-2px); }
.btn-s { background:white; color:var(--text) !important; border:0.5px solid var(--border); }
.btn-s:hover { background:#f0efff; transform:translateY(-2px); }
.hero-stats {
  display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:30px;
  padding-top:30px; border-top:0.5px solid rgba(83,74,183,0.18);
}
.stat-n { font-family:'DM Serif Display', Georgia, serif; font-size:32px; color:var(--p600); line-height:1.1; }
.stat-l { font-size:13px; color:var(--muted); margin-top:3px; }

.section { padding:70px 0; }
.sec-wrap { max-width:var(--max); margin:0 auto; }
.sec-label {
  font-size:12px; font-weight:500; letter-spacing:.07em; text-transform:uppercase;
  color:var(--p600); margin-bottom:10px;
}
.sec-title {
  font-family:'DM Serif Display', Georgia, serif; font-size:38px; line-height:1.14;
  font-weight:400; margin:0 0 14px; color:var(--text);
}
.sec-body { font-size:15px; color:var(--muted); line-height:1.75; max-width:620px; margin:0 0 34px; }

.pipeline-steps { background:rgba(255,255,255,.45); border:0.5px solid var(--border); border-radius:var(--rxl); padding:16px 32px; }
.pipe-step { display:grid; grid-template-columns:48px 1fr; gap:0 24px; align-items:start; padding:28px 0; border-bottom:0.5px solid var(--border); }
.pipe-step:last-child { border-bottom:none; }
.pipe-num-col { display:flex; flex-direction:column; align-items:center; }
.pipe-num { width:40px; height:40px; border-radius:50%; display:grid; place-items:center; font-size:15px; font-weight:500; flex-shrink:0; }
.num-1 { background:var(--p50); color:var(--p600); } .num-2 { background:var(--teal50); color:var(--teal600); } .num-3 { background:var(--amb50); color:var(--amb600); }
.pipe-line { width:1px; flex:1; background:var(--border); margin-top:8px; min-height:40px; }
.pipe-step:last-child .pipe-line { display:none; }
.pipe-tag { display:inline-block; font-size:11px; font-weight:500; letter-spacing:.05em; text-transform:uppercase; padding:3px 10px; border-radius:20px; margin-bottom:8px; }
.tag-p { background:var(--p50); color:var(--p600); } .tag-t { background:var(--teal50); color:var(--teal600); } .tag-a { background:var(--amb50); color:var(--amb600); }
.pipe-title { font-size:19px; font-weight:500; margin-bottom:6px; font-family:'DM Serif Display', Georgia, serif; color:var(--text); }
.pipe-desc { font-size:14px; color:var(--muted); line-height:1.7; margin:0 0 12px; }
.pipe-tags { display:flex; flex-wrap:wrap; gap:6px; }
.ex-tag { font-size:12px; padding:4px 12px; border-radius:20px; background:white; border:0.5px solid var(--border); color:var(--muted); }

.dashboard-section { padding:76px 0 76px; }
.dash-outer { background:var(--dark); border-radius:var(--rxl); padding:46px; box-shadow:0 24px 80px rgba(18,17,42,.18); }
.dash-source-row { display:flex; align-items:center; justify-content:space-between; gap:16px; margin-bottom:28px; flex-wrap:wrap; }
.source-badge, .live-badge {
  display:inline-flex; align-items:center; gap:8px; background:rgba(255,255,255,0.055);
  border:0.5px solid rgba(255,255,255,0.1); border-radius:40px; padding:8px 16px;
  font-size:13px; color:#bbb;
}
.source-badge strong { color:white; font-weight:500; }
.live-dot { width:7px; height:7px; border-radius:50%; background:var(--grn400); animation:blink 1.4s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.28} }
.dash-title-block .sec-label { color:var(--p200); }
.dash-title-block .sec-title { color:white; margin-bottom:4px; }
.dash-sub { font-size:13px; color:#77729a; margin-bottom:28px; }
.prob-grid { display:grid; grid-template-columns:repeat(4, minmax(0,1fr)); gap:14px; }
.prob-card {
  background:#2e2c50; border-radius:var(--rlg); padding:20px;
  border:0.5px solid rgba(255,255,255,0.07); transition:background .2s, transform .15s;
  min-height:224px;
}
.prob-card:hover { background:#353270; transform:translateY(-2px); }
.pc-top { display:flex; align-items:flex-start; justify-content:space-between; gap:8px; margin-bottom:12px; }
.pc-name { font-size:14px; font-weight:500; color:#e8e6ff; line-height:1.35; }
.pc-status { font-size:10px; font-weight:500; padding:3px 9px; border-radius:20px; white-space:nowrap; }
.st-crit { background:rgba(226,75,74,.25); color:#ff9898; }
.st-high { background:rgba(239,159,39,.25); color:#ffd080; }
.st-mid { background:rgba(99,153,34,.25); color:#a8e05f; }
.st-new { background:rgba(175,169,236,.2); color:#c8c3f8; }
.pc-pct { font-size:30px; font-weight:400; color:white; font-family:'DM Serif Display', Georgia, serif; margin-bottom:2px; }
.pc-delta { font-size:11px; margin-bottom:14px; color:#a8a6c8; line-height:1.5; }
.signal-meter { height:42px; display:flex; align-items:flex-end; gap:4px; margin-bottom:14px; }
.signal-meter span { flex:1; border-radius:5px 5px 2px 2px; background:linear-gradient(180deg, #AFA9EC, #534AB7); opacity:.95; min-height:6px; }
.pc-keywords { display:flex; flex-wrap:wrap; gap:4px; }
.kw { font-size:10px; background:rgba(255,255,255,0.06); color:#bbb8dc; padding:2px 8px; border-radius:20px; }

.cluster-panel {
  background:white; border-radius:var(--rxl); padding:56px 48px;
  border:0.5px solid var(--border); box-shadow:0 16px 60px rgba(83,74,183,.08);
}
.cl-flow-row {
  display:flex; align-items:center; gap:0; margin:28px 0 34px; background:var(--p50);
  border-radius:var(--rlg); padding:18px 24px; border:0.5px solid var(--border);
}
.cl-flow-step { text-align:center; flex:1; }
.cl-flow-icon { font-size:20px; color:var(--p600); margin-bottom:6px; }
.cl-flow-label { font-size:12px; font-weight:500; color:var(--text); margin-bottom:2px; }
.cl-flow-sub { font-size:11px; color:var(--light); line-height:1.4; }
.cl-flow-arrow { color:var(--p100); font-size:22px; flex-shrink:0; padding:0 8px; }
.legend-row {
  display:flex; flex-wrap:wrap; gap:10px; margin-bottom:20px; padding:14px 18px;
  background:#faf9ff; border-radius:var(--rmd); border:0.5px solid var(--border); align-items:center;
}
.legend-label { font-size:11px; font-weight:500; text-transform:uppercase; letter-spacing:.06em; color:var(--light); margin-right:4px; }
.legend-item { display:flex; align-items:center; gap:5px; font-size:12px; color:var(--muted); }
.cluster-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px; }
.cl-card { background:white; border-radius:var(--rlg); border:1px solid #e8e6ff; overflow:hidden; transition:box-shadow .2s, transform .15s; }
.cl-card:hover { box-shadow:0 8px 32px rgba(83,74,183,.12); transform:translateY(-2px); }
.cl-stripe { height:4px; width:100%; }
.stripe-crit { background:linear-gradient(90deg,#E24B4A,#f09090); }
.stripe-high { background:linear-gradient(90deg,#EF9F27,#f7cc80); }
.stripe-mid { background:linear-gradient(90deg,#639922,#a0cc60); }
.stripe-emg { background:linear-gradient(90deg,var(--p600),var(--p200)); }
.cl-card-inner { padding:22px; }
.cl-top { display:flex; align-items:flex-start; justify-content:space-between; gap:10px; margin-bottom:4px; }
.cl-name { font-size:15px; font-weight:500; color:var(--text); }
.cl-count { font-size:12px; color:var(--light); margin-bottom:16px; }
.cl-signal-badge { font-size:10px; font-weight:500; padding:3px 10px; border-radius:20px; flex-shrink:0; }
.sig-crit { background:var(--red50); color:var(--red600); }
.sig-high { background:var(--amb50); color:var(--amb600); }
.sig-mid { background:var(--grn50); color:var(--grn600); }
.sig-emg { background:var(--p50); color:var(--p600); }
.cl-sources-label { font-size:10px; font-weight:500; text-transform:uppercase; letter-spacing:.06em; color:var(--light); margin-bottom:7px; }
.cl-sources { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:16px; }
.cl-src-tag { font-size:11px; background:#f4f3ff; color:var(--p600); padding:3px 11px; border-radius:20px; border:0.5px solid #d8d4f8; font-weight:500; }
.cl-diagnosis { background:var(--text); border-radius:var(--rmd); padding:16px 18px; margin-bottom:14px; }
.cl-diag-label { font-size:10px; font-weight:500; text-transform:uppercase; letter-spacing:.07em; color:var(--p200); margin-bottom:8px; display:flex; align-items:center; gap:4px; }
.cl-diag-text { font-size:13px; color:#e0defc; line-height:1.65; }
.cl-overlap { font-size:11px; color:var(--light); display:flex; align-items:center; gap:5px; line-height:1.45; }

.st-key-stakeholder_dashboard_shell {
  max-width:var(--max);
  margin:24px auto 0;
  padding:56px 48px;
  background:#f4f3ff;
  border-radius:var(--rxl);
}

.st-key-stakeholder_dashboard_shell > div[data-testid="stVerticalBlock"] {
  gap:0!important;
}

.stakeholder-section {
  background:transparent;
  border-radius:0;
  padding:0;
  margin:0 0 28px;
}
.sh-overview-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:28px; }
.sh-ov-card { background:white; border:0.5px solid var(--border); border-radius:var(--rlg); padding:18px; border-top:3px solid transparent; transition:box-shadow .2s, transform .15s; }
.sh-ov-card:hover { box-shadow:0 4px 20px rgba(83,74,183,.1); transform:translateY(-1px); }
.sh-ov-card.active { border-top-color:var(--p600); box-shadow:0 4px 20px rgba(83,74,183,.15); }
div[class*="st-key-stakeholder_card_wrap_"]{
  position:relative!important;
  height:218px!important;
  min-height:218px!important;
  margin:0!important;
  padding:0!important;
}

div[class*="st-key-stakeholder_card_wrap_"] div[data-testid="stVerticalBlock"]{
  position:relative!important;
  height:218px!important;
  min-height:218px!important;
  gap:0!important;
  margin:0!important;
  padding:0!important;
}

div[class*="st-key-stakeholder_card_wrap_"] div[data-testid="stElementContainer"]:has(.sh-ov-card){
  position:absolute!important;
  inset:0!important;
  z-index:1!important;
  width:100%!important;
  height:218px!important;
  margin:0!important;
  padding:0!important;
}

div[class*="st-key-stakeholder_card_wrap_"] div[data-testid="stButton"]{
  position:absolute!important;
  inset:0!important;
  z-index:2!important;
  width:100%!important;
  height:218px!important;
  margin:0!important;
  padding:0!important;
  pointer-events:auto!important;
}

div[class*="st-key-stakeholder_card_wrap_"] div[data-testid="stButton"] button{
  position:absolute!important;
  inset:0!important;
  width:100%!important;
  height:218px!important;
  min-height:218px!important;
  margin:0!important;
  padding:0!important;
  border:0!important;
  background:transparent!important;
  color:transparent!important;
  font-size:0!important;
  box-shadow:none!important;
  cursor:pointer!important;
  pointer-events:auto!important;
}

div[class*="st-key-stakeholder_card_wrap_"] .sh-ov-card{
  width:100%!important;
  height:218px!important;
  margin:0!important;
  pointer-events:none!important;
}

div[class*="st-key-stakeholder_card_wrap_"] .sh-ov-card *{
  pointer-events:none!important;
}
.sh-ov-icon { font-size:20px; color:var(--p600); margin-bottom:8px; }
.sh-ov-name { font-size:14px; font-weight:500; margin-bottom:4px; color:var(--text); }
.sh-ov-role { font-size:12px; color:var(--muted); margin-bottom:10px; line-height:1.45; min-height:52px; }
.sh-ov-badges { display:flex; flex-wrap:wrap; gap:4px; }
.badge { font-size:11px; padding:3px 10px; border-radius:20px; font-weight:500; }
.b-h { background:var(--blue50); color:var(--blue600); }
.b-s { background:var(--coral50); color:var(--coral600); }
.b-f { background:var(--amb50); color:var(--amb600); }
.b-l { background:var(--p50); color:var(--p600); }
.b-i { background:var(--pink50); color:var(--pink600); }
.b-g { background:var(--grn50); color:var(--grn600); }
.sh-occ { display:flex; align-items:center; gap:5px; font-size:11px; margin-top:10px; color:var(--muted); }
.occ-dot { width:6px; height:6px; border-radius:50%; background:var(--amb400); }
.occ-open { background:var(--grn400); }

/* STAKEHOLDER DETAILS */

.sh-detail-panel {
  background:white;
  border:0.5px solid var(--border);
  border-radius:var(--rxl);
  padding:28px;
}

.sh-detail-head {
  display:flex;
  align-items:flex-start;
  justify-content:space-between;
  gap:18px;
  margin-bottom:24px;
}

.sh-detail-identity {
  display:flex;
  align-items:center;
  gap:14px;
}

.sh-detail-icon {
  width:44px;
  height:44px;
  border-radius:14px;
  background:var(--p50);
  color:var(--p600);
  display:grid;
  place-items:center;
  font-size:22px;
  flex-shrink:0;
}

.sh-detail-name {
  font-size:19px;
  font-weight:500;
  color:var(--text);
  margin-bottom:3px;
}

.sh-detail-subtitle {
  font-size:12px;
  color:var(--muted);
}

.sh-detail-status {
  display:flex;
  align-items:center;
  gap:6px;
  font-size:12px;
  color:var(--amb600);
  margin-top:12px;
}

.sh-detail-status-dot {
  width:7px;
  height:7px;
  border-radius:50%;
  background:var(--amb400);
}

.sh-detail-grid {
  display:grid;
  grid-template-columns:1.15fr 1fr;
  gap:30px;
}

.sh-detail-column + .sh-detail-column {
  border-left:0.5px solid var(--border);
  padding-left:30px;
}

.sh-detail-label {
  font-size:10px;
  font-weight:500;
  text-transform:uppercase;
  letter-spacing:.07em;
  color:var(--light);
  margin-bottom:14px;
}

.sh-problem-item {
  padding:0 0 15px;
  margin-bottom:15px;
  border-bottom:0.5px solid var(--border);
}

.sh-problem-title {
  display:flex;
  align-items:center;
  gap:8px;
  color:var(--text);
  font-size:13px;
  font-weight:500;
  margin-bottom:7px;
}

.sh-problem-dot {
  width:7px;
  height:7px;
  border-radius:50%;
  flex-shrink:0;
}

.sh-dot-red {
  background:var(--red400);
}

.sh-dot-green {
  background:var(--grn400);
}

.sh-dot-orange {
  background:var(--amb400);
}

.sh-problem-badge {
  font-size:10px;
  padding:2px 8px;
  border-radius:20px;
  font-weight:500;
}

.sh-badge-overloaded {
  color:var(--red600);
  background:var(--red50);
}


.sh-badge-open {
  color:var(--grn600);
  background:var(--grn50);
}

.sh-badge-active {
  color:var(--amb600);
  background:var(--amb50);
}

.sh-problem-copy {
  font-size:12px;
  color:var(--muted);
  margin:0 0 5px 15px;
  line-height:1.5;
}

.sh-problem-note {
  font-size:11px;
  color:var(--p600);
  font-style:italic;
  margin-left:15px;
  line-height:1.45;
}

.sh-potential-card {
  border-radius:var(--rmd);
  padding:15px 16px;
  margin-bottom:10px;
  border:0.5px solid var(--border);
}

.sh-potential-red {
  background:#fff7f7;
  border-color:#f7d7d7;
}

.sh-potential-green {
  background:var(--grn50);
  border-color:#d5e7bc;
}

.sh-potential-neutral {
  background:#fafafa;
}

.sh-potential-title {
  font-size:10px;
  font-weight:500;
  text-transform:uppercase;
  letter-spacing:.04em;
  margin-bottom:7px;
}

.sh-potential-red .sh-potential-title {
  color:var(--red600);
}

.sh-potential-green .sh-potential-title {
  color:var(--grn600);
}

.sh-potential-neutral .sh-potential-title {
  color:var(--muted);
}

.sh-potential-copy {
  font-size:12px;
  line-height:1.55;
  color:var(--text);
}

@media(max-width:700px) {
  .sh-detail-grid {
    grid-template-columns:1fr;
  }

  .sh-detail-column + .sh-detail-column {
    border-left:none;
    border-top:0.5px solid var(--border);
    padding-left:0;
    padding-top:24px;
  }
}

/* --- Service Gap Actions --- */

.st-key-service_gap_actions {
  margin-top:16px;
}

.st-key-service_gap_actions > div[data-testid="stVerticalBlock"] {
  gap:10px!important;
}

.st-key-service_gap_actions div[data-testid="stButton"] button {
  min-height:44px!important;
  border-radius:14px!important;
  border:1px solid #d5e7bc!important;
  background:var(--grn50)!important;
  color:var(--grn600)!important;
  font-size:12px!important;
  font-weight:500!important;
  padding:0 16px!important;
}

.st-key-service_gap_actions div[data-testid="stButton"] button:hover {
  border-color:var(--grn400)!important;
  background:#e2f0cf!important;
  color:var(--grn600)!important;
}

.st-key-reopen_signal_idea {
  width:100%;
  margin:18px 0 0;
}

.st-key-reopen_signal_idea div[data-testid="stButton"] button {
  min-height:48px!important;
  border-radius:14px!important;
  border:1px solid var(--p600)!important;
  background:var(--p600)!important;
  color:white!important;
  font-size:12px!important;
  font-weight:500!important;
  padding:0 16px!important;
}

.st-key-reopen_signal_idea div[data-testid="stButton"] button:hover {
  border-color:var(--p800)!important;
  background:var(--p800)!important;
  color:white!important;
}

.service-modal-card {
  padding:4px 2px 8px;
}

.service-modal-kicker {
  font-size:11px;
  font-weight:500;
  text-transform:uppercase;
  letter-spacing:.07em;
  color:var(--p600);
  margin-bottom:10px;
}

.service-modal-title {
  font-family:'DM Serif Display', Georgia, serif;
  font-size:34px;
  line-height:1.14;
  color:var(--text);
  margin-bottom:14px;
}

.service-modal-meta {
  display:flex;
  flex-wrap:wrap;
  gap:7px;
  margin-bottom:22px;
}

.service-modal-meta span {
  font-size:11px;
  color:var(--p600);
  background:var(--p50);
  border-radius:20px;
  padding:5px 11px;
}

.service-modal-section {
  margin-bottom:18px;
}

.service-modal-label {
  font-size:10px;
  font-weight:500;
  text-transform:uppercase;
  letter-spacing:.07em;
  color:var(--light);
  margin-bottom:8px;
}

.service-modal-copy {
  font-size:13px;
  line-height:1.7;
  color:var(--muted);
}

.service-modal-grid {
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:16px;
  margin-bottom:16px;
}

.service-modal-box {
  background:#faf9ff;
  border:0.5px solid var(--border);
  border-radius:14px;
  padding:16px;
}

.service-modal-steps {
  margin:0;
  padding-left:18px;
  color:var(--muted);
  font-size:12px;
  line-height:1.7;
}

.service-modal-risk {
  background:#fff7f7;
  border:0.5px solid #f7d7d7;
  border-radius:14px;
  padding:16px;
}

.service-modal-risk .service-modal-label {
  color:var(--red600);
}

@media(max-width:700px) {
  .service-modal-grid {
    grid-template-columns:1fr;
  }
}

/* SERVICE GENERATION OUTPUT */
.ai-section{padding:76px 0 28px;}
.ai-inner{max-width:var(--max);margin:0 auto;}
.st-key-innovation_form{max-width:var(--max);margin:0 auto 36px;padding:34px 36px 30px;background:var(--p50);border:0.5px solid var(--border);border-radius:var(--rxl);}
.st-key-innovation_form .ai-box-label{font-size:13px;font-weight:500;color:var(--p600);margin:0 0 16px;}
.st-key-innovation_form div[data-testid="stHorizontalBlock"]{max-width:none;margin:0;gap:10px;align-items:center;}
.st-key-innovation_form div[data-testid="stHorizontalBlock"]+div[data-testid="stHorizontalBlock"]{margin-top:12px;justify-content:flex-start;}
.st-key-innovation_form div[data-testid="stHorizontalBlock"]+div[data-testid="stHorizontalBlock"]>div[data-testid="column"]{flex:0 0 auto!important;width:auto!important;min-width:0!important;}

.st-key-innovation_form div[data-testid="stTextInput"]{
  margin:0!important;
  padding:0!important;
  background:transparent!important;
  border:0!important;
  box-shadow:none!important;
  overflow:visible!important;
}

.st-key-innovation_form div[data-testid="stTextInput"] > div{
  height:52px!important;
  min-height:52px!important;
  margin:0!important;
  padding:0!important;
  background:transparent!important;
  border:0!important;
  box-shadow:none!important;
}

.st-key-innovation_form div[data-testid="stTextInput"] div[data-baseweb="input"]{
  height:52px!important;
  min-height:52px!important;
  width:100%!important;
  margin:0!important;
  padding:0!important;
  border-radius:999px!important;
  background:white!important;
  border:1px solid #d8d4f8!important;
  box-shadow:none!important;
  overflow:hidden!important;
}

.st-key-innovation_form div[data-testid="stTextInput"] div[data-baseweb="input"]::before,
.st-key-innovation_form div[data-testid="stTextInput"] div[data-baseweb="input"]::after{
  display:none!important;
  content:none!important;
}

.st-key-innovation_form div[data-testid="stTextInput"] div[data-baseweb="base-input"]{
  height:52px!important;
  min-height:52px!important;
  width:100%!important;
  margin:0!important;
  padding:0!important;
  background:transparent!important;
  border:0!important;
  box-shadow:none!important;
}

.st-key-innovation_form div[data-testid="stTextInput"] input{
  height:52px!important;
  min-height:52px!important;
  width:100%!important;
  margin:0!important;
  padding:0 20px!important;
  border:0!important;
  border-radius:999px!important;
  background:transparent!important;
  box-shadow:none!important;
  outline:none!important;
  appearance:none!important;
  line-height:normal!important;
  font-size:14px!important;
  box-sizing:border-box!important;
}

.st-key-innovation_form div[data-testid="stTextInput"]:focus-within div[data-baseweb="input"]{
  border-color:var(--p600)!important;
  box-shadow:0 0 0 2px rgba(83,74,183,.12)!important;
}

.st-key-innovation_form div[data-testid="stTextInput"] [aria-invalid="true"]{
  border:0!important;
  box-shadow:none!important;
  outline:none!important;
}

.st-key-innovation_form [data-testid="InputInstructions"],
.st-key-innovation_form [data-testid="stTextInput"] small,
.st-key-innovation_form [data-testid="stTextInput"] [aria-live="polite"]{
  display:none!important;
}

.st-key-innovation_form div[data-testid="stButton"]{margin:0!important;}
.st-key-innovation_form div[data-testid="stButton"] button{min-height:40px;border-radius:999px;padding:0 16px;border:1px solid #d8d4f8;background:white;color:var(--p600);font-size:12px;font-weight:400;white-space:nowrap;}
.st-key-innovation_form div[data-testid="stButton"] button:hover{border-color:var(--p600);background:#f8f7ff;color:var(--p800);}
.st-key-analyze_signal button{height:52px!important;min-height:52px!important;padding:0 22px!important;background:var(--p600)!important;color:white!important;border:1px solid var(--p600)!important;font-size:14px!important;font-weight:500!important;}
.st-key-analyze_signal button:hover{background:var(--p800)!important;color:white!important;border:1px solid var(--p800)!important;}
.ai-result-box{max-width:var(--max);margin:18px auto 0;background:white;border:0.5px solid var(--border);border-radius:var(--rlg);padding:22px;}

.ai-box { background:var(--p50); border-radius:var(--rxl); padding:36px; border:0.5px solid var(--border); }
.ai-result { background:white; border:0.5px solid #ddd; border-radius:var(--rlg); padding:24px; font-size:14px; line-height:1.7; color:#333; }
.ai-kicker { font-size:11px; font-weight:500; text-transform:uppercase; letter-spacing:.06em; color:var(--p600); margin-bottom:6px; }
.ai-name { font-family:'DM Serif Display', Georgia, serif; font-size:28px; line-height:1.15; color:var(--text); margin-bottom:12px; }
.ai-meta { display:flex; flex-wrap:wrap; gap:6px; margin:10px 0 18px; }
.ai-meta span { font-size:11px; background:#f4f3ff; color:var(--p600); border:0.5px solid #d8d4f8; border-radius:20px; padding:3px 10px; }
.ai-steps { margin:8px 0 0; padding-left:18px; }
.ai-steps li { margin-bottom:5px; }
.ai-summary { background:white; border:0.5px solid #ddd; border-radius:var(--rlg); padding:20px 22px; color:var(--muted); font-size:14px; line-height:1.7; margin-bottom:14px; }
.innovation-grid { display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:14px; }
.innovation-card { background:white; border:0.5px solid #ddd; border-radius:var(--rlg); padding:22px; font-size:14px; line-height:1.65; color:#333; }
.innovation-card .ai-name { font-size:24px; }
.innovation-card p { margin:0 0 10px; }
.empty-state { background:white; border:0.5px dashed #c9c4ef; border-radius:var(--rlg); padding:22px; color:var(--muted); font-size:14px; line-height:1.65; }

.data-lab {
  background:white; border:0.5px solid var(--border); border-radius:var(--rxl); padding:26px;
  margin:100px 0; box-shadow:0 8px 36px rgba(83,74,183,.06);
}
.status-grid { display:grid; grid-template-columns:repeat(5, minmax(0,1fr)); gap:10px; margin:16px 0 24px; }
.status-card { background:#faf9ff; border:0.5px solid var(--border); border-radius:var(--rmd); padding:14px; }
.status-top { display:flex; align-items:center; justify-content:space-between; gap:8px; margin-bottom:8px; }
.status-dot { width:8px; height:8px; border-radius:50%; display:inline-block; }
.status-num { font-family:'DM Serif Display', Georgia, serif; font-size:28px; color:var(--text); line-height:1; }
.status-label { font-size:12px; font-weight:500; color:var(--text); margin-bottom:2px; }
.status-copy { font-size:11px; color:var(--muted); line-height:1.35; }
.record-card { border-bottom:0.5px solid var(--border); padding:16px 0; }
.record-card:last-child { border-bottom:none; }
.record-meta { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px; }
.record-pill { font-size:11px; padding:3px 9px; border-radius:20px; background:var(--p50); color:var(--p600); font-weight:500; }
.record-title { font-size:14px; color:var(--text); line-height:1.5; margin-bottom:8px; }
.record-json { background:#12112a; color:#d8d4f8; border-radius:var(--rmd); padding:12px 14px; font-size:12px; line-height:1.6; overflow:auto; }

.ss-footer { background:var(--dark); border-radius:var(--rxl) var(--rxl) 0 0; margin:24px -24px 0; padding:36px 44px; display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:16px; }
.footer-brand { color:white; font-size:15px; font-weight:500; }
.footer-txt { font-size:13px; color:#77729a; }

.stTabs [data-baseweb="tab-list"] { gap:18px; border-bottom:0.5px solid var(--border); }
.stTabs [data-baseweb="tab"] { color:var(--muted); font-size:13px; }
.stTabs [aria-selected="true"] { color:var(--p600) !important; }
.stAlert { border-radius:var(--rmd); }
.st-key-innovation_form .stAlert,
.st-key-innovation_form div[data-baseweb="notification"] {
  margin-top:18px!important;
  border:0!important;
  background:rgba(226,75,74,.14)!important;
  color:var(--red600)!important;
  border-radius:14px!important;
  box-shadow:none!important;
}

.st-key-innovation_form .stAlert p,
.st-key-innovation_form div[data-baseweb="notification"] p,
.st-key-innovation_form div[data-baseweb="notification"] div {
  color:var(--red600)!important;
  font-weight:500!important;
}

@media(max-width:900px) {
  .nav-links { display:none; }
  .hero h1 { font-size:40px; }
  .hero-stats, .prob-grid, .cluster-grid, .sh-overview-grid, .status-grid, .innovation-grid { grid-template-columns:1fr 1fr; }
  .dash-outer, .cluster-panel, .stakeholder-section { padding:32px 22px; }
}
@media(max-width:620px) {
  .block-container { padding-left:14px !important; padding-right:14px !important; }
  .ss-nav, .hero { margin-left:-14px; margin-right:-14px; }
  .ss-nav-inner { padding:0 18px; }
  .hero { padding:58px 24px 44px; }
  .hero h1 { font-size:34px; }
  .hero-stats, .prob-grid, .cluster-grid, .sh-overview-grid, .status-grid, .innovation-grid { grid-template-columns:1fr; }
  .pipeline-steps { padding:8px 18px; }
  .pipe-step { grid-template-columns:38px 1fr; gap:0 16px; }
  .cl-flow-row { display:grid; grid-template-columns:1fr; gap:10px; }
  .cl-flow-arrow { display:none; }
}
.health-grid {
  display:grid;
  grid-template-columns:repeat(4, minmax(0, 1fr));
  gap:14px;
  margin-top:24px;
}

.health-card {
  background:white;
  border:0.5px solid var(--border);
  border-radius:var(--rlg);
  padding:18px;
}

.health-value {
  font-family:'DM Serif Display', Georgia, serif;
  font-size:24px;
  color:var(--p600);
  line-height:1.2;
  word-break:break-word;
}

.health-label {
  font-size:12px;
  color:var(--muted);
  margin-top:6px;
}

.health-status-row {
  display:flex;
  flex-wrap:wrap;
  gap:10px;
  margin-top:14px;
}

.health-status-row span {
  background:white;
  border:0.5px solid var(--border);
  border-radius:40px;
  padding:7px 13px;
  font-size:12px;
  color:var(--muted);
}

.health-warning {
  margin-top:16px;
  background:var(--amb50);
  color:var(--amb600);
  border-radius:var(--rmd);
  padding:12px 16px;
  font-size:13px;
}
</style>
"""


def esc(value) -> str:
    return html.escape(str(value or ""), quote=True)


def render_html(markup: str) -> None:
    markup = dedent(str(markup)).strip()
    if hasattr(st, "html"):
        st.html(markup)
    else:
        st.markdown(markup, unsafe_allow_html=True)


def one_line(value, limit=220) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def parse_json(value) -> dict:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def status_as_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

def get_pipeline_health(reports):
    """
    Creates a compact health snapshot for the dashboard.
    This does not run the pipeline. It only shows the current database state.
    """
    db_exists = DB_FILE.exists()

    health = {
        "db_exists": db_exists,
        "db_last_modified": None,
        "total_posts": 0,
        "status_counts": {-1: 0, 0: 0, 1: 0, 2: 0, 3: 0},
        "latest_report_created_at": None,
    }

    if reports:
        health["latest_report_created_at"] = reports[0].get("created_at")

    if not db_exists:
        return health

    try:
        health["db_last_modified"] = datetime.fromtimestamp(
            DB_FILE.stat().st_mtime
        ).strftime("%Y-%m-%d %H:%M")
    except OSError:
        health["db_last_modified"] = "Could not read file timestamp"

    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()

        cursor.execute("SELECT status, COUNT(*) FROM forum_posts GROUP BY status")
        for status, count in cursor.fetchall():
            health["status_counts"][status_as_int(status)] = count

        health["total_posts"] = sum(health["status_counts"].values())
        conn.close()

    except sqlite3.Error as error:
        health["error"] = str(error)

    return health


def render_pipeline_health(health):
    counts = health["status_counts"]
    total_posts = health["total_posts"]
    analyzed_count = counts.get(2, 0)
    pending_agent3 = counts.get(1, 0)
    human_review = counts.get(3, 0)

    completion_rate = round((analyzed_count / total_posts) * 100) if total_posts else 0

    db_status = "Connected" if health["db_exists"] else "Missing"
    db_modified = health["db_last_modified"] or "N/A"
    latest_report = health["latest_report_created_at"] or "No report timestamp found"

    warning_html = ""
    if pending_agent3 > 0 or human_review > 0:
        warning_html = f"""
        <div class="health-warning">
          {pending_agent3} cleaned posts are still waiting for Agent 3; {human_review} cases are waiting for Human Review.
        </div>
        """

    render_html(
        f"""
<section class="section" id="health">
  <div class="sec-wrap">
    <div class="sec-label">Pipeline Health</div>
    <h2 class="sec-title">Data freshness and processing state</h2>
    <p class="sec-body">
      This panel shows whether the dashboard reflects a recently processed database state
      or whether records are still waiting in earlier pipeline stages.
    </p>

    <div class="health-grid">
      <div class="health-card">
        <div class="health-value">{esc(db_status)}</div>
        <div class="health-label">SQLite database</div>
      </div>
      <div class="health-card">
        <div class="health-value">{esc(db_modified)}</div>
        <div class="health-label">Last database update</div>
      </div>
      <div class="health-card">
        <div class="health-value">{completion_rate}%</div>
        <div class="health-label">Analyzed share</div>
      </div>
      <div class="health-card">
        <div class="health-value">{esc(latest_report)}</div>
        <div class="health-label">Latest Agent 4 report</div>
      </div>
    </div>

    <div class="health-status-row">
      <span>Status -1 filtered: <strong>{counts.get(-1, 0)}</strong></span>
      <span>Status 0 raw: <strong>{counts.get(0, 0)}</strong></span>
      <span>Status 1 cleaned: <strong>{counts.get(1, 0)}</strong></span>
      <span>Status 2 analyzed: <strong>{counts.get(2, 0)}</strong></span>
      <span>Status 3 review: <strong>{counts.get(3, 0)}</strong></span>
    </div>

    {warning_html}
  </div>
</section>
"""
    )

def normalize_cluster(raw_cluster, cleaned_content="") -> str:
    raw = str(raw_cluster or "").strip()
    if raw in CLUSTER_META:
        return raw
    haystack = f"{raw} {cleaned_content or ''}".lower()
    if any(token in haystack for token in ["finanz", "baf", "geld", "miete zahlen"]):
        return "Finanzen"
    if any(token in haystack for token in ["mental", "psy", "depression", "angst", "stress"]):
        return "Mentale Gesundheit"
    if any(token in haystack for token in ["studium", "pruf", "pruef", "modul", "semester", "uni"]):
        return "Studium"
    if any(token in haystack for token in ["wohn", "wg", "zimmer", "kaution"]):
        return "Wohnen"
    return raw or "Sonstiges"


def urgency_label(urgency_counts: Counter, total: int) -> tuple[str, str, str]:
    high = urgency_counts.get("Hoch", 0)
    mid = urgency_counts.get("Mittel", 0)
    if total == 0:
        return "Emerging", "st-new", "stripe-emg"
    if high / total >= 0.28 or high >= 8:
        return "Kritisch", "st-crit", "stripe-crit"
    if high or mid / total >= 0.55:
        return "Hoch", "st-high", "stripe-high"
    if mid:
        return "Mittel", "st-mid", "stripe-mid"
    return "Emerging", "st-new", "stripe-emg"


def signal_bars(percent: int, index: int) -> str:
    base = max(12, min(percent, 96))
    pattern = [
        max(8, base - 22 + index * 2),
        max(10, base - 16),
        max(12, base - 7 + (index % 3) * 3),
        max(14, base - 2),
        max(16, base + 5),
        max(18, base + 12),
    ]
    return "".join(f'<span style="height:{min(96, value)}%"></span>' for value in pattern)


def stakeholder_role(name: str) -> str:
    lowered = name.lower()
    if "baf" in lowered:
        return "Owns financial aid processes and the paperwork experience around student funding."
    if "studierendenwerk" in lowered or "studentenwerk" in lowered:
        return "Connects housing, social counselling and financial support in the student service layer."
    if "psych" in lowered or "beratung" in lowered:
        return "Handles psychosocial counselling and low-threshold support for vulnerable students."
    if "hochschule" in lowered or "universit" in lowered:
        return "Coordinates campus services, onboarding, study advice and institutional escalation paths."
    if "krankenkasse" in lowered:
        return "Can connect health insurance processes with mental health and hardship support."
    if "ministerium" in lowered or "regierung" in lowered or "amt" in lowered:
        return "Shapes structural rules, resources and administrative access conditions."
    return "Appears repeatedly in analyzed posts and should be considered in service design workshops."


def stakeholder_badge_class(name: str) -> str:
    lowered = name.lower()
    if "baf" in lowered or "finanz" in lowered:
        return "b-f"
    if "psych" in lowered or "beratung" in lowered:
        return "b-s"
    if "werk" in lowered or "wohn" in lowered:
        return "b-h"
    if "univers" in lowered or "hochschule" in lowered:
        return "b-g"
    if "amt" in lowered or "regierung" in lowered:
        return "b-l"
    return "b-i"


def normalize_stakeholder_name(name: str) -> str:
    normalized = str(name or "").strip().lower()
    normalized = normalized.replace("ö", "oe")
    normalized = normalized.replace("ä", "ae")
    normalized = normalized.replace("ü", "ue")
    normalized = normalized.replace("ß", "ss")

    return "".join(
        character
        for character in normalized
        if character.isalnum()
    )

def select_stakeholder(name: str) -> None:
    st.session_state.selected_stakeholder = name

def _service_idea_tokens(*values) -> set[str]:
    text = " ".join(str(value or "") for value in values).lower()

    return {
        token
        for token in re.findall(
            r"[a-zA-ZäöüÄÖÜß0-9]+",
            text,
        )
        if len(token) >= 4
    }


def _match_service_innovation(
    service_gap: dict,
    stakeholder_name: str,
    innovations: list,
) -> dict | None:
    gap_tokens = _service_idea_tokens(
        service_gap.get("title"),
        service_gap.get("evidence"),
        service_gap.get("recommendation"),
        stakeholder_name,
    )

    best_match = None
    best_score = -1

    for innovation in innovations:
        if not isinstance(innovation, dict):
            continue

        innovation_tokens = _service_idea_tokens(
            innovation.get("cluster"),
            innovation.get("opportunity"),
            innovation.get("solution"),
            innovation.get("target"),
            innovation.get("stakeholder"),
            innovation.get("evidence"),
        )

        score = len(gap_tokens & innovation_tokens)

        if score > best_score:
            best_score = score
            best_match = innovation

    return best_match


@st.dialog("Service Innovation", width="large")
def show_service_innovation_dialog(
    service_gap: dict,
    stakeholder_name: str,
    innovation: dict | None,
) -> None:
    title = str(
        service_gap.get("title")
        or "Neue Serviceidee"
    )

    recommendation = str(
        service_gap.get("recommendation")
        or ""
    )

    evidence = str(
        service_gap.get("evidence")
        or ""
    )

    if innovation:
        opportunity = (
            innovation.get("opportunity")
            or title
        )

        cluster = (
            innovation.get("cluster")
            or title
        )

        solution = (
            innovation.get("solution")
            or recommendation
        )

        target = (
            innovation.get("target")
            or "Studierende"
        )

        stakeholder = (
            innovation.get("stakeholder")
            or stakeholder_name
        )

        innovation_evidence = (
            innovation.get("evidence")
            or evidence
        )

        risk = (
            innovation.get("risk")
            or "Keine Risikobeschreibung verfügbar."
        )

        implementation_steps = innovation.get(
            "implementation_steps",
            [],
        )

    else:
        opportunity = title
        cluster = title
        solution = recommendation
        target = "Studierende"
        stakeholder = stakeholder_name
        innovation_evidence = evidence

        risk = (
            "Im aktuellen Agent-4-Report ist noch keine "
            "Risikobeschreibung vorhanden."
        )

        implementation_steps = []

    if not isinstance(implementation_steps, list):
        implementation_steps = [
            str(implementation_steps)
        ]

    steps_html = "".join(
        f"<li>{esc(step)}</li>"
        for step in implementation_steps
        if str(step).strip()
    )

    if not steps_html:
        steps_html = (
            "<li>Noch keine Umsetzungsschritte verfügbar.</li>"
        )

    render_html(
        f"""
<div class="service-modal-card">
  <div class="service-modal-kicker">
    Agent-4 Service Innovation
  </div>

  <div class="service-modal-title">
    {esc(opportunity)}
  </div>

  <div class="service-modal-meta">
    <span>Cluster: {esc(cluster)}</span>
    <span>Zielgruppe: {esc(target)}</span>
    <span>Stakeholder: {esc(stakeholder)}</span>
  </div>

  <div class="service-modal-section">
    <div class="service-modal-label">
      Konzept
    </div>

    <div class="service-modal-copy">
      {esc(solution)}
    </div>
  </div>

  <div class="service-modal-grid">
    <div class="service-modal-box">
      <div class="service-modal-label">
        Datengrundlage
      </div>

      <div class="service-modal-copy">
        {esc(innovation_evidence)}
      </div>
    </div>

    <div class="service-modal-box">
      <div class="service-modal-label">
        Umsetzungsschritte
      </div>

      <ol class="service-modal-steps">
        {steps_html}
      </ol>
    </div>
  </div>

  <div class="service-modal-risk">
    <div class="service-modal-label">
      Risiko / ethische Grenze
    </div>

    <div class="service-modal-copy">
      {esc(risk)}
    </div>
  </div>
</div>
"""
    )
  
  # === DSR Stakeholder-Feedback ==========================================
    from feedback_store import DECISIONS, make_key, set_feedback, get_feedback_map

    fb_key = make_key(opportunity)
    fb_current = get_feedback_map().get(fb_key, {})

    st.divider()
    st.markdown("**Stakeholder-Entscheidung zu dieser Idee**")

    fb_decision = st.segmented_control(
        "Entscheidung",
        options=DECISIONS,
        default=fb_current.get("decision"),
        key=f"decision_{fb_key}",
        label_visibility="collapsed",
    )
    fb_note = st.text_input(
        "Notiz",
        value=fb_current.get("note", ""),
        key=f"note_{fb_key}",
        placeholder="optionale Notiz…",
        label_visibility="collapsed",
    )
    if st.button("Entscheidung speichern", key=f"save_{fb_key}"):
        if fb_decision:
            set_feedback(fb_key, opportunity, fb_decision, fb_note or "")
            st.success(f"Gespeichert: {fb_decision}")
        else:
            st.warning("Bitte zuerst eine Entscheidung wählen.")
    if fb_current.get("updated_at"):
        st.caption(
            f"Zuletzt: {fb_current.get('decision')} · {fb_current.get('updated_at')}"
        )

    # --- Phase 2 (reactive): idea missed -> Agent 4 proposes an alternative ---
    if fb_decision == "Andere Lösung nötig":
        st.info(
            "Der Bedarf bleibt bestehen – Service Sonar kann eine alternative "
            "Idee für dasselbe Problem vorschlagen."
        )
        if st.button("↻ Neue Lösung vorschlagen", key=f"regen_{fb_key}"):
            try:
                with st.spinner("Alternative Serviceidee wird entwickelt..."):
                    from agent4_innovator import Agent4Innovator
                    regen_prompt = (
                        f"Die bisherige Idee '{opportunity}' fuer den Bedarf im "
                        f"Cluster '{cluster}' wurde vom Stakeholder als unpassend "
                        f"markiert. Schlage einen ANDEREN Loesungsansatz fuer "
                        f"denselben Bedarf vor. Datengrundlage: {innovation_evidence}"
                    )
                    alt = Agent4Innovator().generate_from_signal(regen_prompt)
                st.session_state[f"alt_{fb_key}"] = alt
            except Exception as exc:
                st.error(f"Alternative konnte nicht generiert werden: {exc}")

    alt_idea = st.session_state.get(f"alt_{fb_key}")
    if isinstance(alt_idea, dict):
        st.markdown("**Alternativer Vorschlag von Agent 4:**")
        st.markdown(f"**{alt_idea.get('opportunity', 'Neue Serviceidee')}**")
        st.write(alt_idea.get("solution", ""))
    # =======================================================================
    


def set_signal_suggestion(text: str) -> None:
    st.session_state.signal_input = text


@st.dialog("Neue Serviceidee", width="large")
def show_generated_signal_dialog(innovation: dict) -> None:
    steps = innovation.get("implementation_steps", [])

    if not isinstance(steps, list):
        steps = [str(steps)]

    steps_html = "".join(
        f"<li>{esc(step)}</li>"
        for step in steps
        if str(step).strip()
    )

    render_html(
        f"""
<div class="service-modal-card">
  <div class="service-modal-kicker">
    Interaktive Service Innovation
  </div>

  <div class="service-modal-title">
    {esc(innovation.get("opportunity", "Neue Serviceidee"))}
  </div>

  <div class="service-modal-meta">
    <span>Cluster: {esc(innovation.get("cluster", "—"))}</span>
    <span>Zielgruppe: {esc(innovation.get("target", "—"))}</span>
    <span>Stakeholder: {esc(innovation.get("stakeholder", "—"))}</span>
  </div>

  <div class="service-modal-section">
    <div class="service-modal-label">Erkannte Lücke</div>
    <div class="service-modal-copy">
      {esc(innovation.get("gap_summary", ""))}
    </div>
  </div>

  <div class="service-modal-section">
    <div class="service-modal-label">Konzept</div>
    <div class="service-modal-copy">
      {esc(innovation.get("solution", ""))}
    </div>
  </div>

  <div class="service-modal-grid">
    <div class="service-modal-box">
      <div class="service-modal-label">Warum diese Idee?</div>
      <div class="service-modal-copy">
        {esc(innovation.get("evidence", ""))}
      </div>
    </div>

    <div class="service-modal-box">
      <div class="service-modal-label">Umsetzungsschritte</div>
      <ol class="service-modal-steps">
        {steps_html}
      </ol>
    </div>
  </div>

  <div class="service-modal-risk">
    <div class="service-modal-label">
      Risiko / ethische Grenze
    </div>

    <div class="service-modal-copy">
      {esc(innovation.get("risk", ""))}
    </div>
  </div>
</div>
"""
    )

@st.cache_data(ttl=20, show_spinner=False)
def load_data():
    if not DB_FILE.exists():
        return [], []
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        records = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, url, raw_content, cleaned_content, analysis_json, status
                FROM forum_posts
                ORDER BY id DESC
                """
            ).fetchall()
        ]
        reports = [
            dict(row)
            for row in conn.execute(
                """
                SELECT id, created_at, report_json
                FROM system_reports
                ORDER BY id DESC
                """
            ).fetchall()
        ]
        conn.close()
        return records, reports
    except sqlite3.Error:
        return [], []


def build_analytics(records):
    analyses = []
    for row in records:
        if status_as_int(row.get("status")) != 2:
            continue
        data = parse_json(row.get("analysis_json"))
        cluster = normalize_cluster(data.get("problem_cluster"), row.get("cleaned_content"))
        urgency = str(data.get("urgency") or "Niedrig")
        tone = str(data.get("emotional_tone") or "Neutral")
        stakeholders = data.get("stakeholders") if isinstance(data.get("stakeholders"), list) else []
        analyses.append(
            {
                "row": row,
                "data": data,
                "cluster": cluster,
                "urgency": urgency,
                "tone": tone,
                "stakeholders": [str(item) for item in stakeholders if item],
            }
        )

    groups = defaultdict(list)
    stakeholder_counts = Counter()
    urgency_counts = Counter()
    tone_counts = Counter()

    for item in analyses:
        groups[item["cluster"]].append(item)
        urgency_counts[item["urgency"]] += 1
        tone_counts[item["tone"]] += 1
        stakeholder_counts.update(item["stakeholders"])

    return analyses, groups, stakeholder_counts, urgency_counts, tone_counts


def render_nav():
    render_html(
        """
<div class="ss-nav">
  <div class="ss-nav-inner">
    <a class="brand" href="#">
      <div class="brand-mark"></div>
      <span class="brand-name">Service <span>Sonar</span></span>
    </a>
    <div class="nav-links">
      <a href="#pipeline">Pipeline</a>
      <a href="#dashboard">Signale</a>
      <a href="#cluster">Clustering</a>
      <a href="#stakeholder">Stakeholder</a>
      <a class="nav-btn" href="#innovation">Innovation</a>
    </div>
  </div>
</div>
"""
    )


def render_hero(total_records, analyzed_count, cluster_count, urgent_count):
    render_html(
        f"""
<div class="hero">
  <div class="hero-inner">
    <div class="pill"><i class="ti ti-radar"></i> Social Intelligence Platform</div>
    <h1>Versteckte soziale Bed&uuml;rfnisse <em>sichtbar</em> machen</h1>
    <p class="hero-sub">Service Sonar erkennt schwache Signale aus studentischen Quellen, strukturiert sie mit KI und macht daraus eine Entscheidungsgrundlage f&uuml;r bessere Services.</p>
    <div class="hero-btns">
      <a class="btn-p" href="#dashboard"><i class="ti ti-layout-dashboard"></i> Dashboard &ouml;ffnen</a>
      <a class="btn-s" href="#pipeline"><i class="ti ti-route"></i> Pipeline ansehen</a>
    </div>
    <div class="hero-stats">
      <div><div class="stat-n">{total_records}</div><div class="stat-l">Quellen in SQLite</div></div>
      <div><div class="stat-n">{analyzed_count}</div><div class="stat-l">LLM-analysierte Texte</div></div>
      <div><div class="stat-n">{cluster_count}</div><div class="stat-l">Aktive Problemcluster</div></div>
      <div><div class="stat-n">{urgent_count}</div><div class="stat-l">High-urgency Signale</div></div>
    </div>
  </div>
</div>
"""
    )


def render_pipeline(status_counts):
    raw_count = status_counts.get(0, 0)
    clean_count = status_counts.get(1, 0)
    analyzed_count = status_counts.get(2, 0)
    review_count = status_counts.get(3, 0)
    render_html(
        f"""
<section class="section">
  <div class="sec-wrap" id="pipeline">
    <div class="sec-label">Was Service Sonar leistet</div>
    <h2 class="sec-title">Drei Schritte von Daten zur Innovation</h2>
    <p class="sec-body">Die Streamlit-Version folgt dem Look des HTML-Prototyps, liest aber live aus der lokalen SQLite-Datenbank.</p>
    <div class="pipeline-steps">
      <div class="pipe-step">
        <div class="pipe-num-col"><div class="pipe-num num-1">1</div><div class="pipe-line"></div></div>
        <div>
          <span class="pipe-tag tag-p">Weak Signal Detection</span>
          <div class="pipe-title">Crawler extracts recurring pain patterns</div>
          <p class="pipe-desc">Agent 1 sammelt Forumtexte und legt sie als Rohsignale ab. Aktuell warten <strong>{raw_count}</strong> neue Rohposts im Intake.</p>
          <div class="pipe-tags"><span class="ex-tag">Forum-Crawler</span><span class="ex-tag">SQLite Intake</span><span class="ex-tag">Source Deduplication</span></div>
        </div>
      </div>
      <div class="pipe-step">
        <div class="pipe-num-col"><div class="pipe-num num-2">2</div><div class="pipe-line"></div></div>
        <div>
          <span class="pipe-tag tag-t">Privacy & Clustering</span>
          <div class="pipe-title">Cleaner prepares posts for semantic analysis</div>
          <p class="pipe-desc">Agent 2 anonymisiert, filtert irrelevante Inhalte und markiert sensible F&auml;lle. <strong>{clean_count}</strong> Beitr&auml;ge sind bereinigt, <strong>{review_count}</strong> warten auf Human Review.</p>
          <div class="pipe-tags"><span class="ex-tag">Anonymisierung</span><span class="ex-tag">Relevanzfilter</span><span class="ex-tag">Human-in-the-loop</span></div>
        </div>
      </div>
      <div class="pipe-step">
        <div class="pipe-num-col"><div class="pipe-num num-3">3</div><div class="pipe-line"></div></div>
        <div>
          <span class="pipe-tag tag-a">Service Innovation Output</span>
          <div class="pipe-title">LLM maps signals to stakeholders and opportunities</div>
          <p class="pipe-desc">Agent 3 hat <strong>{analyzed_count}</strong> Beitr&auml;ge strukturiert. Agent 4 kann daraus einen verdichteten Service-Innovationsbericht erzeugen.</p>
          <div class="pipe-tags"><span class="ex-tag">LLM JSON</span><span class="ex-tag">Stakeholder Mapping</span><span class="ex-tag">Decision Support</span></div>
        </div>
      </div>
    </div>
  </div>
</section>
"""
    )


def render_problem_dashboard(groups, analyzed_count):
    cards = []
    sorted_groups = sorted(groups.items(), key=lambda item: len(item[1]), reverse=True)
    for index, (cluster, items) in enumerate(sorted_groups[:8]):
        meta = CLUSTER_META.get(cluster, CLUSTER_META["Sonstiges"])
        count = len(items)
        percent = round((count / analyzed_count) * 100) if analyzed_count else 0
        urgency_counts = Counter(item["urgency"] for item in items)
        label, status_class, _ = urgency_label(urgency_counts, count)
        keywords = meta["keywords"][:]
        stakeholder_counts = Counter()
        for item in items:
            stakeholder_counts.update(item["stakeholders"])
        for stakeholder, _ in stakeholder_counts.most_common(2):
            clean = esc(stakeholder)
            if clean not in keywords:
                keywords.append(clean)
        keyword_html = "".join(f'<span class="kw">{kw}</span>' for kw in keywords[:5])
        bars = signal_bars(percent, index)
        cards.append(
            f"""
      <div class="prob-card">
        <div class="pc-top"><span class="pc-name">{meta["display"]}</span><span class="pc-status {status_class}">{label}</span></div>
        <div class="pc-pct">{percent}%</div>
        <div class="pc-delta">{count} LLM-analysierte Beitr&auml;ge in diesem Cluster</div>
        <div class="signal-meter">{bars}</div>
        <div class="pc-keywords">{keyword_html}</div>
      </div>
"""
        )

    if not cards:
        cards.append(
            """
      <div class="prob-card">
        <div class="pc-top"><span class="pc-name">Noch keine analysierten Signale</span><span class="pc-status st-new">Pending</span></div>
        <div class="pc-pct">0%</div>
        <div class="pc-delta">Agent 3 hat noch keine Beitr&auml;ge strukturiert.</div>
        <div class="signal-meter"><span style="height:8%"></span><span style="height:8%"></span><span style="height:8%"></span><span style="height:8%"></span></div>
        <div class="pc-keywords"><span class="kw">Waiting for analysis</span></div>
      </div>
"""
        )

    render_html(
        f"""
<section class="dashboard-section">
  <div class="dash-outer" id="dashboard">
    <div class="dash-source-row">
      <div class="source-badge"><i class="ti ti-database" style="font-size:14px;color:var(--p200)"></i><strong>{analyzed_count} Quellen analysiert</strong></div>
      <div class="live-badge"><div class="live-dot"></div>Live SQLite Monitoring</div>
    </div>
    <div class="dash-title-block">
      <div class="sec-label">Aktuelles Problem-Dashboard</div>
      <h2 class="sec-title">Top-Signale aus Service Sonar</h2>
      <div class="dash-sub">Cluster werden aus Agent-3-Analysen aggregiert und nach Signalvolumen sortiert</div>
    </div>
    <div class="prob-grid">
      {''.join(cards)}
    </div>
  </div>
</section>
"""
    )


def render_cluster_section(groups, analyzed_count):
    cluster_cards = []
    for cluster, items in sorted(groups.items(), key=lambda item: len(item[1]), reverse=True):
        meta = CLUSTER_META.get(cluster, CLUSTER_META["Sonstiges"])
        count = len(items)
        urgency_counts = Counter(item["urgency"] for item in items)
        label, _, stripe_class = urgency_label(urgency_counts, count)
        badge_class = {
            "Kritisch": "sig-crit",
            "Hoch": "sig-high",
            "Mittel": "sig-mid",
            "Emerging": "sig-emg",
        }.get(label, "sig-emg")
        keywords = "".join(f'<span class="cl-src-tag">{kw}</span>' for kw in meta["keywords"])
        cluster_cards.append(
            f"""
      <div class="cl-card">
        <div class="cl-stripe {stripe_class}"></div>
        <div class="cl-card-inner">
          <div class="cl-top">
            <div><div class="cl-name">{meta["display"]}</div><div class="cl-count">{count} Erw&auml;hnungen aus {analyzed_count} Analysen</div></div>
            <span class="cl-signal-badge {badge_class}">{label}</span>
          </div>
          <div class="cl-sources-label">Zusammengesetzte Signale</div>
          <div class="cl-sources">{keywords}</div>
          <div class="cl-diagnosis">
            <div class="cl-diag-label"><i class="ti ti-alert-circle"></i>Systemischer Befund</div>
            <div class="cl-diag-text">{meta["diagnosis"]}</div>
          </div>
          <div class="cl-overlap"><i class="ti ti-git-branch"></i>{meta["overlap"]}</div>
        </div>
      </div>
"""
        )

    if not cluster_cards:
        cluster_cards.append(
            """
      <div class="cl-card">
        <div class="cl-stripe stripe-emg"></div>
        <div class="cl-card-inner">
          <div class="cl-top"><div><div class="cl-name">No cluster data yet</div><div class="cl-count">0 analyzed records</div></div><span class="cl-signal-badge sig-emg">Pending</span></div>
          <div class="cl-diagnosis"><div class="cl-diag-label">Systemischer Befund</div><div class="cl-diag-text">Run Agent 3 to turn cleaned posts into structured problem clusters.</div></div>
        </div>
      </div>
"""
        )

    render_html(
        f"""
<section class="section">
  <div class="cluster-panel" id="cluster">
    <div class="sec-label">Dynamic Problem Clustering</div>
    <h2 class="sec-title">Von Symptomen zu systemischen L&uuml;cken</h2>
    <p class="sec-body">Einzelne Posts zeigen Symptome. Erst die Verdichtung nach Cluster, Dringlichkeit und Stakeholdern macht sichtbar, wo ein neuer Service ansetzen kann.</p>

    <div class="cl-flow-row">
      <div class="cl-flow-step"><div class="cl-flow-icon"><i class="ti ti-antenna-bars-3"></i></div><div class="cl-flow-label">Einzelsignale</div><div class="cl-flow-sub">Forum posts</div></div>
      <div class="cl-flow-arrow">-&gt;</div>
      <div class="cl-flow-step"><div class="cl-flow-icon"><i class="ti ti-circles-relation"></i></div><div class="cl-flow-label">Clustering</div><div class="cl-flow-sub">LLM JSON</div></div>
      <div class="cl-flow-arrow">-&gt;</div>
      <div class="cl-flow-step"><div class="cl-flow-icon"><i class="ti ti-alert-circle"></i></div><div class="cl-flow-label">Systemischer Riss</div><div class="cl-flow-sub">Patterns</div></div>
      <div class="cl-flow-arrow">-&gt;</div>
      <div class="cl-flow-step"><div class="cl-flow-icon"><i class="ti ti-bulb"></i></div><div class="cl-flow-label">Service Opportunity</div><div class="cl-flow-sub">Agent 4</div></div>
    </div>

    <div class="legend-row">
      <span class="legend-label">Signalstatus:</span>
      <span class="legend-item"><span class="cl-signal-badge sig-crit">Kritisch</span> hohe Eskalation</span>
      <span class="legend-item"><span class="cl-signal-badge sig-high">Hoch</span> Intervention empfohlen</span>
      <span class="legend-item"><span class="cl-signal-badge sig-mid">Mittel</span> sichtbar</span>
      <span class="legend-item"><span class="cl-signal-badge sig-emg">Emerging</span> neu oder schwach</span>
    </div>

    <div class="cluster-grid">
      {''.join(cluster_cards)}
    </div>
  </div>
</section>
"""
    )

def render_stakeholder_detail(name: str, count: int) -> str:
    """
    Erstellt die Detailansicht für einen Stakeholder.

    Aktuell werden stakeholder-spezifische Texte über einfache
    Namensregeln ausgewählt. Später können diese Inhalte aus
    Agent-3- oder Agent-4-Daten erzeugt werden.
    """

    lowered = name.lower()

    if "hochschule" in lowered or "universit" in lowered:
        subtitle = "Strukturelle Früherkennung & Maßnahmen"

        problems = [
            {
                "title": "Psychische Belastung",
                "status": "überlastet",
                "dot_class": "sh-dot-red",
                "badge_class": "sh-badge-overloaded",
                "solution": "Psychologische Beratungsstelle ausgebaut",
                "note": (
                    "Direkter Zugang zu Studierenden – aber stark "
                    "überlastet, Wartezeiten bis 6 Wochen"
                ),
            },
            {
                "title": "Soziale Isolation",
                "status": "offen",
                "dot_class": "sh-dot-green",
                "badge_class": "sh-badge-open",
                "solution": "Onboarding-Programme für Erstsemester",
                "note": (
                    "Struktureller Zugang zu allen Erstsemestern – "
                    "aber Programm endet nach Woche 1"
                ),
            },
        ]

        potentials = [
            {
                "style": "sh-potential-red",
                "title": "Optimierungspotenzial · Psychische Belastung",
                "copy": (
                    "KI-gestütztes Ersttriage-Tool könnte Wartezeiten "
                    "reduzieren: schnelle Einschätzung, ob Sofortberatung "
                    "oder Gruppenangebot passender ist."
                ),
            },
            {
                "style": "sh-potential-green",
                "title": "Schließungspotenzial · Soziale Isolation",
                "copy": (
                    "Kontinuierliches Peer-Netzwerk nach der Einführungswoche "
                    "fehlt – strukturierte Begleitung über das erste Semester "
                    "wäre möglich."
                ),
            },
            {
                "style": "sh-potential-neutral",
                "title": "Neuer Service möglich",
                "copy": (
                    "Behörden-Überforderung ist noch nicht ausreichend "
                    "abgedeckt – eine strukturierte Orientierungshilfe für "
                    "Formulare und Fristen wäre denkbar."
                ),
            },
        ]

    elif "studierendenwerk" in lowered or "studentenwerk" in lowered:
        subtitle = "Soziale, finanzielle und wohnbezogene Unterstützung"

        problems = [
            {
                "title": "Finanzielle Belastung",
                "status": "überlastet",
                "dot_class": "sh-dot-red",
                "badge_class": "sh-badge-overloaded",
                "solution": "Sozialberatung und BAföG-Unterstützung vorhanden",
                "note": (
                    "Viele parallele Anfragen und schwer verständliche "
                    "administrative Abläufe"
                ),
            },
            {
                "title": "Wohnungsstress",
                "status": "offen",
                "dot_class": "sh-dot-green",
                "badge_class": "sh-badge-open",
                "solution": "Wohnheime und allgemeine Wohnberatung",
                "note": (
                    "Angebote bestehen, decken kurzfristige Engpässe "
                    "jedoch nicht vollständig ab"
                ),
            },
        ]

        potentials = [
            {
                "style": "sh-potential-red",
                "title": "Optimierungspotenzial · Beratung",
                "copy": (
                    "Ein digitales Vorprüfungs- und Routing-System könnte "
                    "Anfragen nach Dringlichkeit und Zuständigkeit sortieren."
                ),
            },
            {
                "style": "sh-potential-green",
                "title": "Schließungspotenzial · Wohnen",
                "copy": (
                    "Eine verifizierte kurzfristige Wohnbörse könnte Studierende "
                    "bei akuten Wohnungsproblemen gezielter unterstützen."
                ),
            },
            {
                "style": "sh-potential-neutral",
                "title": "Neuer Service möglich",
                "copy": (
                    "Ein zentraler Härtefall-Navigator könnte finanzielle, "
                    "soziale und wohnbezogene Hilfen verbinden."
                ),
            },
        ]

    elif "baf" in lowered or "finanz" in lowered:
        subtitle = "Studienfinanzierung & administrative Zugänge"

        problems = [
            {
                "title": "Komplexe Anträge",
                "status": "überlastet",
                "dot_class": "sh-dot-red",
                "badge_class": "sh-badge-overloaded",
                "solution": "Persönliche Beratung und digitale Formulare",
                "note": (
                    "Rückfragen, Nachweise und unklare Bearbeitungsstände "
                    "verursachen zusätzliche Belastung"
                ),
            },
            {
                "title": "Informationslücken",
                "status": "offen",
                "dot_class": "sh-dot-green",
                "badge_class": "sh-badge-open",
                "solution": "Allgemeine Informationsseiten vorhanden",
                "note": (
                    "Individuelle Sonderfälle werden durch statische "
                    "Informationen nur teilweise abgedeckt"
                ),
            },
        ]

        potentials = [
            {
                "style": "sh-potential-red",
                "title": "Optimierungspotenzial · Antrag",
                "copy": (
                    "Ein interaktiver Dokumentencheck könnte fehlende Nachweise "
                    "vor der Abgabe erkennen."
                ),
            },
            {
                "style": "sh-potential-green",
                "title": "Schließungspotenzial · Transparenz",
                "copy": (
                    "Ein verständlicher Status-Tracker könnte Bearbeitungsphasen "
                    "und nächste notwendige Schritte erklären."
                ),
            },
            {
                "style": "sh-potential-neutral",
                "title": "Neuer Service möglich",
                "copy": (
                    "Eine persönliche Finanzierungsübersicht könnte BAföG, "
                    "Stipendien und Härtefallhilfen gemeinsam darstellen."
                ),
            },
        ]

    else:
        subtitle = stakeholder_role(name)

        problems = [
            {
                "title": "Wiederkehrende Bedarfssignale",
                "status": "offen",
                "dot_class": "sh-dot-green",
                "badge_class": "sh-badge-open",
                "solution": f"{count} Signale wurden diesem Stakeholder zugeordnet",
                "note": (
                    "Die genaue bestehende Zuständigkeit sollte in einem "
                    "Service-Design-Workshop geprüft werden."
                ),
            },
        ]

        potentials = [
            {
                "style": "sh-potential-neutral",
                "title": "Analysepotenzial",
                "copy": (
                    "Die vorhandenen Signale können genutzt werden, um "
                    "Zuständigkeiten, Überlastung und mögliche neue Services "
                    "systematisch zu prüfen."
                ),
            },
        ]

    problems_html = "".join(
        f"""
        <div class="sh-problem-item">
          <div class="sh-problem-title">
            <span class="sh-problem-dot {problem['dot_class']}"></span>
            <span>{esc(problem['title'])}</span>
            <span class="sh-problem-badge {problem['badge_class']}">
              {esc(problem['status'])}
            </span>
          </div>

          <div class="sh-problem-copy">
            {esc(problem['solution'])}
          </div>

          <div class="sh-problem-note">
            {esc(problem['note'])}
          </div>
        </div>
        """
        for problem in problems
    )

    potentials_html = "".join(
        f"""
        <div class="sh-potential-card {potential['style']}">
          <div class="sh-potential-title">
            {esc(potential['title'])}
          </div>

          <div class="sh-potential-copy">
            {esc(potential['copy'])}
          </div>
        </div>
        """
        for potential in potentials
    )

    return f"""
<div class="sh-detail-head">
  <div>
    <div class="sh-detail-identity">
      <div class="sh-detail-icon">
        <i class="ti ti-building-community"></i>
      </div>

      <div>
        <div class="sh-detail-name">{esc(name)}</div>
        <div class="sh-detail-subtitle">{esc(subtitle)}</div>
      </div>
    </div>

    <div class="sh-detail-status">
      <span class="sh-detail-status-dot"></span>
      Wird aktiv bearbeitet · {count} erkannte Signale
    </div>
  </div>
</div>

<div class="sh-detail-grid">
  <div class="sh-detail-column">
    <div class="sh-detail-label">
      Bearbeitete Probleme & Lösungen
    </div>

    {problems_html}
  </div>

  <div class="sh-detail-column">
    <div class="sh-detail-label">
      Innovationspotenzial
    </div>

    {potentials_html}
  </div>
</div>
"""


# Agent-4 style stakeholder detail rendering
def render_agent4_stakeholder_detail(name, count, profile, status_label, status_color):
    task_areas = profile.get("task_areas", []) if isinstance(profile, dict) else []

    if not task_areas:
        return render_stakeholder_detail(name, count)

    status_meta = {
        "active": {
            "label": "aktiv",
            "dot": "var(--amb400)",
            "badge": "sh-badge-active",
            "potential_style": "sh-potential-neutral",
            "potential_title": "Bestehende Zuständigkeit",
        },
        "overloaded": {
            "label": "überlastet",
            "dot": "var(--red400)",
            "badge": "sh-badge-overloaded",
            "potential_style": "sh-potential-red",
            "potential_title": "Optimierungspotenzial",
        },
        "service_gap": {
            "label": "offen",
            "dot": "var(--grn400)",
            "badge": "sh-badge-open",
            "potential_style": "sh-potential-green",
            "potential_title": "Neuer Service möglich",
        },
    }

    problems = []
    potentials = []

    for area in task_areas[:4]:
        if not isinstance(area, dict):
            continue

        status = str(area.get("status", "active")).strip().lower()
        meta = status_meta.get(status, status_meta["active"])
        title = str(area.get("title") or "Arbeitsfeld")
        evidence = str(
            area.get("evidence")
            or "Keine zusätzliche Evidenz verfügbar."
        )
        recommendation = str(
            area.get("recommendation")
            or "Bestehende Zuständigkeit weiter beobachten."
        )

        problems.append(
            f"""
            <div class="sh-problem-item">
              <div class="sh-problem-title">
                <span class="sh-problem-dot" style="background:{meta['dot']};"></span>
                <span>{esc(title)}</span>
                <span class="sh-problem-badge {meta['badge']}">{esc(meta['label'])}</span>
              </div>
              <div class="sh-problem-copy">{esc(recommendation)}</div>
              <div class="sh-problem-note">{esc(evidence)}</div>
            </div>
            """
        )

        if status in {"overloaded", "service_gap"}:
            potentials.append(
                f"""
                <div class="sh-potential-card {meta['potential_style']}">
                  <div class="sh-potential-title">{esc(meta['potential_title'])} · {esc(title)}</div>
                  <div class="sh-potential-copy">{esc(recommendation)}</div>
                </div>
                """
            )

    if not potentials:
        potentials.append(
            """
            <div class="sh-potential-card sh-potential-neutral">
              <div class="sh-potential-title">Bestehende Zuständigkeit</div>
              <div class="sh-potential-copy">Aktuell wurde keine deutliche strukturelle Lücke erkannt.</div>
            </div>
            """
        )

    description = profile.get("description") or stakeholder_role(name)

    return f"""
<div class="sh-detail-head">
  <div>
    <div class="sh-detail-identity">
      <div class="sh-detail-icon"><i class="ti ti-building-community"></i></div>
      <div>
        <div class="sh-detail-name">{esc(name)}</div>
        <div class="sh-detail-subtitle">{esc(description)}</div>
      </div>
    </div>
    <div class="sh-detail-status" style="color:{status_color};">
      <span class="sh-detail-status-dot" style="background:{status_color};"></span>
      {esc(status_label)} · {count} erkannte Signale
    </div>
  </div>
</div>

<div class="sh-detail-grid">
  <div class="sh-detail-column">
    <div class="sh-detail-label">Aufgabenfelder & Bewertung</div>
    {''.join(problems)}
  </div>
  <div class="sh-detail-column">
    <div class="sh-detail-label">Innovationspotenzial</div>
    {''.join(potentials)}
  </div>
</div>
"""


@st.fragment
def render_stakeholders(stakeholder_counts, reports):
    latest_report = {}
    report_cache_key = "no-report"

    if reports:
        latest_report_row = reports[0]
        latest_report = parse_json(latest_report_row.get("report_json"))
        report_cache_key = (
            f"{latest_report_row.get('id', '')}:"
            f"{latest_report_row.get('created_at', '')}"
        )

    innovations = latest_report.get("innovations", [])
    if not isinstance(innovations, list):
        innovations = []

    if st.session_state.get("stakeholder_report_cache_key") != report_cache_key:
        profiles = latest_report.get("stakeholder_profiles", [])
        profile_cache = {}

        if isinstance(profiles, list):
            for profile in profiles:
                if not isinstance(profile, dict) or not profile.get("name"):
                    continue

                profile_cache[
                    normalize_stakeholder_name(profile.get("name"))
                ] = profile

        st.session_state.stakeholder_profile_cache = profile_cache
        st.session_state.stakeholder_report_cache_key = report_cache_key
        st.session_state.pop("stakeholder_detail_cache", None)
        st.session_state.pop("stakeholder_detail_cache_key", None)

    stakeholder_profiles = st.session_state.get(
        "stakeholder_profile_cache",
        {},
    )

    def get_profile(name):
        return stakeholder_profiles.get(
            normalize_stakeholder_name(name),
            {},
        )

    def stakeholder_status(name):
        profile = get_profile(name)
        task_areas = profile.get("task_areas", [])
        statuses = [
            str(area.get("status", "active")).strip().lower()
            for area in task_areas
            if isinstance(area, dict)
        ]

        if not statuses:
            return "Aktiv bearbeitet", "var(--amb400)"

        counts = Counter(statuses)
        active_count = counts.get("active", 0)
        overloaded_count = counts.get("overloaded", 0)
        service_gap_count = counts.get("service_gap", 0)

        if overloaded_count > max(active_count, service_gap_count):
            return "Überlastet", "var(--red400)"

        if service_gap_count > active_count:
            return "Raum für neue Services", "var(--grn400)"

        return "Aktiv bearbeitet", "var(--amb400)"

    top_stakeholders = stakeholder_counts.most_common(6)
    if not top_stakeholders:
        top_stakeholders = [
            ("Studierendenwerk", 0),
            ("BAföG-Amt", 0),
            ("Hochschule", 0),
        ]

    available_names = [name for name, _ in top_stakeholders]

    if (
        "selected_stakeholder" not in st.session_state
        or st.session_state.selected_stakeholder not in available_names
    ):
        st.session_state.selected_stakeholder = available_names[0]

    detail_cache_key = (
        report_cache_key,
        tuple(top_stakeholders),
    )

    if st.session_state.get("stakeholder_detail_cache_key") != detail_cache_key:
        detail_cache = {}

        for name, count in top_stakeholders:
            profile = get_profile(name)
            status_label, status_color = stakeholder_status(name)
            detail_cache[name] = render_agent4_stakeholder_detail(
                name,
                count,
                profile,
                status_label,
                status_color,
            )

        st.session_state.stakeholder_detail_cache = detail_cache
        st.session_state.stakeholder_detail_cache_key = detail_cache_key

    with st.container():
        render_html(
            """
<section class="stakeholder-section" id="stakeholder">
  <div class="sec-label">Stakeholder Dashboard</div>
  <h2 class="sec-title">Wer macht was, und was bleibt offen?</h2>
  <p class="sec-body">Klicke auf eine Stakeholder-Karte. Nur der Stakeholder-Bereich wird aktualisiert; die Seite bleibt an derselben Position.</p>
</section>
"""
        )

        for row_start in range(0, len(top_stakeholders), 3):
            columns = st.columns(3)

            for column, (name, count) in zip(
                columns,
                top_stakeholders[row_start:row_start + 3],
            ):
                profile = get_profile(name)

                description = (
                    profile.get("description")
                    or stakeholder_role(name)
                )

                status_label, status_color = stakeholder_status(name)
                badge_class = stakeholder_badge_class(name)

                active_class = (
                    " active"
                    if name == st.session_state.selected_stakeholder
                    else ""
                )

                normalized_name = normalize_stakeholder_name(name)

                with column:
                    with st.container():
                        render_html(
                            f"""
<div class="sh-ov-card{active_class}">
  <div class="sh-ov-icon">
    <i class="ti ti-building-community"></i>
  </div>

  <div class="sh-ov-name">
    {esc(name)}
  </div>

  <div class="sh-ov-role">
    {esc(description)}
  </div>

  <div class="sh-ov-badges">
    <span class="badge {badge_class}">
      {count} Signale
    </span>
  </div>

  <div class="sh-occ">
    <div
      class="occ-dot"
      style="background:{status_color};"
    ></div>

    <span>
      {esc(status_label)}
    </span>
  </div>
</div>
"""
                        )

                        st.button(
                            f"Stakeholder {name} auswählen",
                            key=f"stakeholder_card_{normalized_name}",
                            use_container_width=True,
                            on_click=select_stakeholder,
                            args=(name,),
                        )

        selected_name = st.session_state.selected_stakeholder
        detail_cache = st.session_state.get("stakeholder_detail_cache", {})
        detail_html = detail_cache.get(selected_name)

        if not detail_html:
            selected_count = dict(top_stakeholders).get(selected_name, 0)
            selected_profile = get_profile(selected_name)
            selected_status, selected_color = stakeholder_status(selected_name)
            detail_html = render_agent4_stakeholder_detail(
                selected_name,
                selected_count,
                selected_profile,
                selected_status,
                selected_color,
            )

        render_html(
            f"""
<div style="width:100%;margin:18px 0 0;">
  <div style="display:flex;gap:20px;flex-wrap:wrap;padding:12px 0 24px;font-size:12px;color:var(--muted);border-bottom:0.5px solid var(--border);margin-bottom:24px;">
    <span style="display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:50%;background:var(--amb400);display:inline-block;"></span>Aktiv bearbeitet &mdash; bestehende Zuständigkeit</span>
    <span style="display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:50%;background:var(--grn400);display:inline-block;"></span>Raum für neue Services &mdash; strukturelle Lücke erkannt</span>
    <span style="display:flex;align-items:center;gap:6px"><span style="width:8px;height:8px;border-radius:50%;background:var(--red400);display:inline-block;"></span>Überlastet &mdash; optimierbar durch neuen Service</span>
  </div>

  <div class="sh-detail-panel" id="sh-detail">
    {detail_html}
  </div>
</div>
"""
        )

        selected_profile = get_profile(selected_name)
        selected_task_areas = selected_profile.get("task_areas", [])

        if not isinstance(selected_task_areas, list):
            selected_task_areas = []

        service_gaps = [
            area
            for area in selected_task_areas
            if isinstance(area, dict)
            and str(area.get("status", "")).strip().lower() == "service_gap"
        ]

        if service_gaps:
            with st.container():
                render_html(
                    '<div class="sh-detail-label" style="margin-top:18px;">'
                    'Mögliche Service Innovation'
                    '</div>'
                )

                gap_columns = st.columns(min(3, len(service_gaps)))

                for index, service_gap in enumerate(service_gaps):
                    gap_title = str(
                        service_gap.get("title")
                        or f"Serviceidee {index + 1}"
                    )

                    matched_innovation = _match_service_innovation(
                        service_gap,
                        selected_name,
                        innovations,
                    )

                    with gap_columns[index % len(gap_columns)]:
                        if st.button(
                            f"↗ {gap_title}",
                            key=(
                                "open_service_gap_"
                                f"{normalize_stakeholder_name(selected_name)}_"
                                f"{index}"
                            ),
                            use_container_width=True,
                        ):
                            show_service_innovation_dialog(
                                service_gap,
                                selected_name,
                                matched_innovation,
                            )


def render_innovation_new(reports, groups):
    if "signal_input" not in st.session_state:
        st.session_state.signal_input = ""

    render_html(
        """
<section class="ai-section">
  <div class="ai-inner" id="innovation">
    <div class="sec-label">Service Innovation Output</div>

    <h2 class="sec-title">
      Du siehst eine Lücke? Hier wird daraus eine Idee.
    </h2>

    <p class="sec-body" style="margin-bottom:28px;">
      Beschreib ein Problem, das du bei Studierenden beobachtest
      &mdash; oder eine Lücke, die noch niemand schließt.
      Service Sonar analysiert es, ordnet es einem systemischen
      Cluster zu und schlägt einen konkreten neuen Service vor.
    </p>
  </div>
</section>
"""
    )

    with st.container():
        st.markdown(
            '<div class="ai-box-label">Lücke oder Signal eingeben:</div>',
            unsafe_allow_html=True,
        )

        input_col, button_col = st.columns(
            [5.4, 1],
            vertical_alignment="center",
        )

        with input_col:
            signal = st.text_input(
                "Signal",
                key="signal_input",
                label_visibility="collapsed",
                placeholder=(
                    "z. B. Keine Anlaufstelle für Behördenfragen "
                    "auf Englisch..."
                ),
            )

        with button_col:
            analyze_clicked = st.button(
                "Analysieren ↗",
                use_container_width=True,
                key="analyze_signal",
            )

        suggestions = [
            (
                "Beratung überlastet",
                "Beratungsstellen sind überlastet – Wartezeiten bis 6 Wochen",
            ),
            (
                "Behörden & Sprache",
                "Keine einheitliche Anlaufstelle für Behördenfragen auf Englisch",
            ),
            (
                "Erstsemester-Isolation",
                "Erstsemester fühlen sich nach der Einführungswoche allein gelassen",
            ),
            (
                "BAföG-Hürden",
                "BAföG-Anträge scheitern oft an bürokratischen Hürden, nicht am Anspruch",
            ),
        ]

        suggestion_cols = st.columns([1.15, 1.25, 1.55, 1])

        for column, (label, value) in zip(
            suggestion_cols,
            suggestions,
        ):
            with column:
                st.button(
                    label,
                    use_container_width=True,
                    key=f"suggestion_{label}",
                    on_click=set_signal_suggestion,
                    args=(value,),
                )

        if analyze_clicked:
            if len(signal.strip()) < 12:
                st.warning(
                    "Bitte beschreibe die beobachtete Lücke etwas genauer."
                )
            else:
                try:
                    with st.spinner("Serviceidee wird entwickelt..."):
                        innovator = Agent4Innovator()
                        result = innovator.generate_from_signal(signal)

                    st.session_state.generated_signal_innovation = result
                    show_generated_signal_dialog(result)

                except Exception as exc:
                    st.error(
                        "Die Serviceidee konnte gerade nicht generiert werden: "
                        f"{exc}"
                    )

        existing_result = st.session_state.get(
            "generated_signal_innovation"
        )

        if existing_result:
            with st.container():
                if st.button(
                    "↗ Letzte Serviceidee erneut öffnen",
                    key="reopen_generated_signal_innovation",
                    use_container_width=True,
                ):
                    show_generated_signal_dialog(existing_result)


def render_innovation(reports, groups):
    latest = reports[0] if reports else None
    if latest:
        insight = parse_json(latest.get("report_json"))
        metadata = insight.get("llm_metadata") if isinstance(insight.get("llm_metadata"), dict) else {}
        innovations = insight.get("innovations") if isinstance(insight.get("innovations"), list) else []
        if not innovations and insight.get("opportunity"):
            innovations = [insight]
        meta_items = []
        if metadata.get("provider"):
            meta_items.append(f"Provider: {esc(metadata.get('provider'))}")
        if metadata.get("model"):
            meta_items.append(f"Model: {esc(metadata.get('model'))}")
        if metadata.get("source_count"):
            meta_items.append(f"Sources: {esc(metadata.get('source_count'))}")
        if metadata.get("prompt_strategy"):
            meta_items.append(f"Prompt: {esc(metadata.get('prompt_strategy'))}")
        meta_html = "".join(f"<span>{item}</span>" for item in meta_items)
        summary = insight.get("portfolio_summary") or "Mehrere LLM-generierte Serviceideen aus den analysierten Bedarfssignalen."
        cards = []
        for index, innovation in enumerate(innovations[:6], start=1):
            if not isinstance(innovation, dict):
                continue

            steps = innovation.get("implementation_steps") if isinstance(innovation.get("implementation_steps"), list) else []
            steps_html = "".join(f"<li>{esc(step)}</li>" for step in steps[:5])
            evidence_html = ""
            if innovation.get("evidence"):
                evidence_html = f"<p><strong>Evidence:</strong> {esc(innovation.get('evidence'))}</p>"
            steps_section = ""
            if steps_html:
                steps_section = f"<p><strong>Implementation:</strong></p><ol class=\"ai-steps\">{steps_html}</ol>"
            risk_html = ""
            if innovation.get("risk"):
                risk_html = f"<p><strong>Risk:</strong> {esc(innovation.get('risk'))}</p>"

            cards.append(
                f"""
      <div class="innovation-card">
        <div class="ai-kicker">Serviceidee {index}</div>
        <div class="ai-name">{esc(innovation.get("opportunity", "Service Opportunity"))}</div>
        <p><strong>Cluster:</strong> {esc(innovation.get("cluster", "N/A"))}</p>
        <p><strong>Concept:</strong> {esc(innovation.get("solution", "N/A"))}</p>
        <p><strong>Target group:</strong> {esc(innovation.get("target", "N/A"))}</p>
        <p><strong>Stakeholder:</strong> {esc(innovation.get("stakeholder", "N/A"))}</p>
        {evidence_html}
        {steps_section}
        {risk_html}
      </div>
"""
            )

        if not cards:
            cards.append(
                """
      <div class="innovation-card">
        <div class="ai-kicker">No valid innovation cards</div>
        <div class="ai-name">Report format could not be rendered</div>
        <p>The latest report exists, but it does not contain a usable innovation portfolio.</p>
      </div>
"""
            )
        evidence_html = ""
        steps_section = ""
        risk_html = ""
        content = f"""
    <div class="ai-result">
      <div class="ai-kicker">Latest Agent 4 LLM Report · {esc(latest.get("created_at"))}</div>
      <div class="ai-name">{esc(insight.get("opportunity", "Service Opportunity"))}</div>
      <div class="ai-meta">{meta_html}</div>
      <p><strong>Cluster:</strong> {esc(insight.get("cluster", "N/A"))}</p>
      <p><strong>Concept:</strong> {esc(insight.get("solution", "N/A"))}</p>
      <p><strong>Target group:</strong> {esc(insight.get("target", "N/A"))}</p>
      <p><strong>Stakeholder:</strong> {esc(insight.get("stakeholder", "N/A"))}</p>
      {evidence_html}
      {steps_section}
      {risk_html}
    </div>
"""
        content = f"""
    <div class="ai-summary">
      <div class="ai-kicker">Latest Agent 4 LLM Portfolio &middot; {esc(latest.get("created_at"))}</div>
      <div class="ai-meta">{meta_html}</div>
      <p>{esc(summary)}</p>
    </div>
    <div class="innovation-grid">
      {''.join(cards)}
    </div>
"""
    else:
        top_cluster = next(iter(sorted(groups.items(), key=lambda item: len(item[1]), reverse=True)), None)
        hint = ""
        if top_cluster:
            meta = CLUSTER_META.get(top_cluster[0], CLUSTER_META["Sonstiges"])
            hint = f'Top live cluster: <strong>{meta["display"]}</strong> with <strong>{len(top_cluster[1])}</strong> analyzed posts.'
        content = f"""
    <div class="empty-state">
      <strong>No Agent 4 report found yet.</strong><br>
      {hint} Run <code>python agent4_innovator.py</code> after Agent 3 has enough analyzed records to fill this section with a generated service concept.
    </div>
"""

    render_html(
        f"""
<section class="ai-section" id="innovation">
  <div class="sec-wrap">
    <div class="sec-label">Service Innovation Output</div>
    <h2 class="sec-title">Aus Signalen werden konkrete Serviceideen</h2>
    <p class="sec-body">Der Innovationsbereich ist an das Agent-4-Output gekoppelt. Sobald ein Report in der Datenbank liegt, wird hier ein kuratiertes Portfolio mehrerer Serviceideen angezeigt.</p>
    <div class="ai-box">
      {content}
    </div>
  </div>
</section>
"""
    )

    


def render_status_lab(records, analyses, status_counts):
    status_cards = []
    for status, meta in STATUS_META.items():
        status_cards.append(
            f"""
      <div class="status-card">
        <div class="status-top"><span class="status-dot" style="background:{meta["accent"]}"></span><span class="status-num">{status_counts.get(status, 0)}</span></div>
        <div class="status-label">{meta["label"]}</div>
        <div class="status-copy">{meta["copy"]}</div>
      </div>
"""
        )
    render_html(
        f"""
<div class="data-lab">
  <div class="sec-label">Operations Data Lab</div>
  <h2 class="sec-title" style="font-size:30px">Pipeline-Zustand und Beispielsignale</h2>
  <div class="status-grid">{"".join(status_cards)}</div>
</div>
"""
    )

    tab1, tab2, tab3 = st.tabs(["Latest analyzed signals", "Cleaned queue", "Raw intake"])

    with tab1:
        if not analyses:
            st.info("No analyzed records yet.")
        for item in analyses[:8]:
            row = item["row"]
            data = item["data"]
            cluster = CLUSTER_META.get(item["cluster"], CLUSTER_META["Sonstiges"])["display"]
            render_html(
                f"""
<div class="record-card">
  <div class="record-meta">
    <span class="record-pill">ID {esc(row.get("id"))}</span>
    <span class="record-pill">{cluster}</span>
    <span class="record-pill">{esc(item["urgency"])}</span>
    <span class="record-pill">{esc(item["tone"])}</span>
  </div>
  <div class="record-title">{esc(one_line(row.get("cleaned_content"), 260))}</div>
  <div class="record-json">{esc(json.dumps(data, ensure_ascii=False, indent=2))}</div>
</div>
"""
            )

    with tab2:
        cleaned = [row for row in records if status_as_int(row.get("status")) == 1]
        if not cleaned:
            st.info("No cleaned records waiting for analysis.")
        for row in cleaned[:8]:
            render_html(
                f"""
<div class="record-card">
  <div class="record-meta"><span class="record-pill">ID {esc(row.get("id"))}</span><span class="record-pill">status 1</span></div>
  <div class="record-title">{esc(one_line(row.get("cleaned_content"), 320))}</div>
</div>
"""
            )

    with tab3:
        raw = [row for row in records if status_as_int(row.get("status")) == 0]
        if not raw:
            st.info("No raw records in the intake queue.")
        for row in raw[:8]:
            render_html(
                f"""
<div class="record-card">
  <div class="record-meta"><span class="record-pill">ID {esc(row.get("id"))}</span><span class="record-pill">status 0</span></div>
  <div class="record-title">{esc(one_line(row.get("raw_content"), 320))}</div>
</div>
"""
            )

def render_footer():
    render_html(
        """
<div class="ss-footer">
  <div class="footer-brand">Service Sonar</div>
  <div class="footer-txt">Social Intelligence Platform · SQLite · Streamlit · 2026</div>
</div>
"""
    )


def main():
    render_html(CUSTOM_CSS)
    records, reports = load_data()
    status_counts = Counter(status_as_int(row.get("status")) for row in records)
    analyses, groups, stakeholder_counts, urgency_counts, _ = build_analytics(records)
    latest_report = reports[0] if reports else None
    urgent_count = urgency_counts.get("Hoch", 0)

    render_nav()
    render_hero(
        total_records=len(records),
        analyzed_count=len(analyses),
        cluster_count=len(groups),
        urgent_count=urgent_count,
    )
    render_pipeline(status_counts)
    health = get_pipeline_health(reports)
    render_pipeline_health(health)
    render_problem_dashboard(groups, len(analyses))
    render_cluster_section(groups, len(analyses))
    render_stakeholders(stakeholder_counts, reports)
    render_innovation_new(reports, groups)
    render_status_lab(records, analyses, status_counts)
    render_footer()


if __name__ == "__main__":
    main()
