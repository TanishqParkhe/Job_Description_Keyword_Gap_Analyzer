"""Saved-analysis history and privacy controls."""
from __future__ import annotations

import streamlit as st

from analytics.history_analytics import records_to_dataframe, summarize_analyses
from database.db import DatabaseManager
from ui.theme import mini_card, page_heading


def history_page(database: DatabaseManager) -> None:
    page_heading(
        "History & Privacy",
        "Review analyses saved on this computer and remove them whenever you choose.",
    )
    info1, info2, info3 = st.columns(3)
    with info1:
        mini_card("Private by default", "An analysis is saved only when you select the save option.")
    with info2:
        mini_card("Bulk uploads", "HR batch resumes are processed for the session and are not added to history.")
    with info3:
        mini_card("Your control", "Saved analysis history can be permanently removed from this page.")

    records = database.list_analyses(limit=200) if database.enabled else []
    summary = summarize_analyses(records)
    st.write("")
    c1, c2, c3 = st.columns(3)
    c1.metric("Saved analyses", summary["count"])
    c2.metric("Average Job Match", f"{summary['average_score']:.1f}")
    c3.metric("Highest Job Match", f"{summary['highest_score']:.1f}")

    if records:
        frame = records_to_dataframe(records)
        st.dataframe(frame, width="stretch", hide_index=True)
        with st.container(border=True):
            st.markdown("#### Delete saved history")
            st.caption("This action cannot be undone.")
            confirm = st.checkbox(
                "I understand that all saved analysis history will be permanently deleted"
            )
            if st.button("Delete all saved history", disabled=not confirm):
                database.delete_all()
                st.rerun()
    else:
        st.info("No analyses have been saved yet.")
