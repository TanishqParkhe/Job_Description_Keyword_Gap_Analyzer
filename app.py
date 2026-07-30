"""Streamlit entry point for the Bhavya AI Resume Analyzer Team Edition."""
from __future__ import annotations

import streamlit as st

from ats.ats_engine import ATSEngine
from config import ASSETS_FOLDER, PROJECT_NAME, PROJECT_VERSION, ensure_directories
from database.db import DatabaseManager
from llm.llm_engine import LLMEngine
from services.analysis_service import AnalysisService
from ui.theme import apply_theme, hero
from workspaces.history import history_page
from workspaces.hr_screening import hr_page
from workspaces.individual import individual_page

ensure_directories()
st.set_page_config(
    page_title=PROJECT_NAME,
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)
apply_theme()


@st.cache_resource
def get_services() -> tuple[LLMEngine, ATSEngine, DatabaseManager, AnalysisService]:
    """Create long-lived application services once per Streamlit server."""
    llm_engine = LLMEngine()
    ats_engine = ATSEngine()
    database = DatabaseManager()
    analysis_service = AnalysisService(llm_engine=llm_engine, ats_engine=ats_engine)
    return llm_engine, ats_engine, database, analysis_service


SESSION_DEFAULTS = {
    "analysis": None,
    "chat_messages": [],
    "bulk_results": None,
    "bulk_warnings": [],
    "fast_inputs": None,
    "pending_chat_question": None,
}
for key, default in SESSION_DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = default

llm_engine, ats_engine, database, analysis_service = get_services()

avatar = ASSETS_FOLDER / "bhavya_avatar.png"
if avatar.exists():
    st.sidebar.image(str(avatar), width=84)
st.sidebar.markdown(f"## {PROJECT_NAME}")
st.sidebar.caption("Evidence-led resume analysis and candidate screening.")
workspace = st.sidebar.radio(
    "Workspace",
    ["Individual Analysis", "HR Screening", "History & Privacy"],
    label_visibility="collapsed",
)
st.sidebar.divider()
st.sidebar.caption(f"Team Edition · Version {PROJECT_VERSION}")

hero()
if workspace == "Individual Analysis":
    individual_page(analysis_service, llm_engine, database)
elif workspace == "HR Screening":
    hr_page(llm_engine, ats_engine)
else:
    history_page(database)
