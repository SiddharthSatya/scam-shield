"""Scam Shield demo UI. Run: streamlit run ui/app.py"""

import sys
from pathlib import Path

import streamlit as st

# Streamlit runs this file as a script; make the repo root importable for `ui.*`.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ui.views import dashboard, demo_bank  # noqa: E402

st.set_page_config(page_title="Scam Shield", page_icon="", layout="wide")

nav = st.navigation([
    st.Page(demo_bank.page, title="Scam Shield", icon="", url_path="bank",
            default=True),
    st.Page(dashboard.page, title="Dashboard for Fraud Analysis(Bank)", icon="",
            url_path="dashboard"),
])
nav.run()
