"""Streamlit Community Cloud entrypoint for the Service Sonar dashboard."""

import runpy
from pathlib import Path


DASHBOARD_PATH = Path(__file__).with_name("dashboard.py")

if not DASHBOARD_PATH.exists():
    raise FileNotFoundError(f"Dashboard entrypoint not found: {DASHBOARD_PATH}")

runpy.run_path(str(DASHBOARD_PATH), run_name="__main__")
