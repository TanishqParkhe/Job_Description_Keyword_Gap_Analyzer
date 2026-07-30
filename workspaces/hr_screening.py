"""HR bulk-screening workspace, including safe ZIP archive support."""
from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from ats.ats_engine import ATSEngine
from config import DEFAULT_HR_THRESHOLD, MAX_BULK_RESUMES, MAX_ZIP_SIZE_MB, SUPPORTED_RESUME_FORMATS
from hr.bulk_screening import DISPLAY_COLUMNS, screen_resumes, selected_csv, selected_zip
from llm.llm_engine import LLMEngine
from reports.pdf_report import generate_pdf_report
from ui.theme import page_heading, section_heading
from utils.document_reader import DocumentReadError
from utils.zip_resume_reader import ResumeZipError, extract_resume_zip


def _hr_summary_chart(results: list[dict[str, Any]]) -> go.Figure:
    counts = {
        "Selected": sum(item.get("decision") == "Selected" for item in results),
        "Rejected": sum(item.get("decision") == "Rejected" for item in results),
        "Errors": sum(item.get("decision") == "Error" for item in results),
    }
    figure = go.Figure(
        go.Pie(
            labels=list(counts),
            values=list(counts.values()),
            hole=0.66,
            textinfo="label+value",
            hovertemplate="%{label}: %{value}<extra></extra>",
        )
    )
    figure.update_layout(
        title="Screening outcome",
        height=330,
        margin=dict(l=20, r=20, t=55, b=20),
        showlegend=False,
        annotations=[
            dict(
                text=f"{len(results)}<br><span style='font-size:12px'>processed</span>",
                x=0.5,
                y=0.5,
                font_size=24,
                showarrow=False,
            )
        ],
    )
    return figure

def _hr_score_chart(results: list[dict[str, Any]]) -> go.Figure:
    valid = [item for item in results if item.get("decision") != "Error"]
    figure = go.Figure(
        go.Histogram(
            x=[float(item.get("score", 0)) for item in valid],
            nbinsx=10,
            hovertemplate="Candidates: %{y}<br>Job Match range: %{x}<extra></extra>",
        )
    )
    figure.update_layout(
        title="Job Match distribution",
        xaxis_title="Job Match score",
        yaxis_title="Candidates",
        height=330,
        margin=dict(l=35, r=20, t=55, b=45),
        bargap=0.08,
    )
    return figure

def hr_page(llm_engine: LLMEngine, ats_engine: ATSEngine) -> None:
    page_heading(
        "HR Resume Screening",
        "Upload individual files or one ZIP archive, apply a clear cutoff, and shortlist candidates for review.",
    )

    with st.container(border=True):
        top_left, top_right = st.columns([1.05, 1], gap="large")
        with top_left:
            section_heading("Candidate batch", "Choose how to upload resumes")
            input_mode = st.radio(
                "Upload method",
                ["Multiple resume files", "ZIP archive"],
                horizontal=True,
                label_visibility="collapsed",
            )
            bulk_files: list[Any] = []
            zip_upload = None
            if input_mode == "Multiple resume files":
                bulk_files = st.file_uploader(
                    f"Upload up to {MAX_BULK_RESUMES} resumes",
                    type=SUPPORTED_RESUME_FORMATS,
                    accept_multiple_files=True,
                    key="bulk_files",
                )
            else:
                zip_upload = st.file_uploader(
                    "Upload a ZIP containing resumes",
                    type=["zip"],
                    key="bulk_zip",
                    help=(
                        f"The archive may contain folders and up to {MAX_BULK_RESUMES} supported resumes. "
                        f"Maximum ZIP size: {MAX_ZIP_SIZE_MB} MB."
                    ),
                )
                st.caption("PDF, DOCX, TXT, PNG, JPG and JPEG resumes inside the ZIP are accepted.")

        with top_right:
            section_heading("Role criteria", "Set the job and screening rule")
            bulk_jd = st.text_area(
                "Job description used for every resume",
                height=250,
                key="bulk_jd",
                placeholder="Paste the complete job description here...",
            )
            threshold = st.slider(
                "Minimum Job Match required",
                0,
                100,
                DEFAULT_HR_THRESHOLD,
                5,
            )
            mandatory_gate = st.checkbox(
                "Reject candidates missing a mandatory requirement",
                value=False,
                help="Enable this only when the job description clearly labels mandatory requirements.",
            )

        start_screening = st.button(
            "Screen Candidate Batch",
            type="primary",
            width="stretch",
        )

    if start_screening:
        if not bulk_jd.strip():
            st.error("Paste the job description.")
        else:
            try:
                warnings: list[str] = []
                files_to_process: list[Any]
                if input_mode == "ZIP archive":
                    if zip_upload is None:
                        raise ResumeZipError("Upload a ZIP archive containing resumes.")
                    with st.spinner("Checking and extracting the resume archive..."):
                        files_to_process, warnings = extract_resume_zip(zip_upload)
                else:
                    files_to_process = list(bulk_files or [])
                    if not files_to_process:
                        raise ValueError("Upload at least one resume.")
                    if len(files_to_process) > MAX_BULK_RESUMES:
                        raise ValueError(
                            f"Upload no more than {MAX_BULK_RESUMES} resumes at once."
                        )

                progress_bar = st.progress(0, text="Starting screening...")

                def update_progress(done: int, total: int) -> None:
                    progress_bar.progress(
                        done / max(total, 1),
                        text=f"Processed {done} of {total} resumes",
                    )

                results = screen_resumes(
                    files_to_process,
                    bulk_jd,
                    threshold=threshold,
                    mandatory_gate=mandatory_gate,
                    llm_engine=llm_engine,
                    ats_engine=ats_engine,
                    progress=update_progress,
                )
                progress_bar.progress(1.0, text=f"Completed {len(results)} resumes")
                st.session_state.bulk_results = results
                st.session_state.bulk_warnings = warnings
            except (ResumeZipError, DocumentReadError, ValueError) as error:
                st.error(str(error))
            except Exception as error:
                st.error(f"The candidate batch could not be screened: {error}")

    if st.session_state.bulk_results:
        results = st.session_state.bulk_results
        selected = [item for item in results if item["decision"] == "Selected"]
        rejected = [item for item in results if item["decision"] == "Rejected"]
        errors = [item for item in results if item["decision"] == "Error"]
        average_score = (
            sum(float(item.get("score", 0)) for item in results if item["decision"] != "Error")
            / max(1, len(results) - len(errors))
        )

        st.divider()
        section_heading("Screening dashboard", "Candidate batch results")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Processed", len(results))
        m2.metric("Selected", len(selected))
        m3.metric("Rejected", len(rejected))
        m4.metric("Errors", len(errors))
        m5.metric("Average Job Match", f"{average_score:.1f}")

        if st.session_state.bulk_warnings:
            with st.expander("ZIP processing notes"):
                for warning in st.session_state.bulk_warnings[:50]:
                    st.write("• " + warning)

        chart_left, chart_right = st.columns(2)
        with chart_left:
            st.plotly_chart(_hr_summary_chart(results), width="stretch")
        with chart_right:
            st.plotly_chart(_hr_score_chart(results), width="stretch")

        selected_tab, rejected_tab, errors_tab = st.tabs(
            [
                f"Selected ({len(selected)})",
                f"Rejected ({len(rejected)})",
                f"Errors ({len(errors)})",
            ]
        )
        display_cols = DISPLAY_COLUMNS

        with selected_tab:
            if selected:
                selected_frame = pd.DataFrame(selected)[display_cols]
                st.dataframe(
                    selected_frame,
                    width="stretch",
                    hide_index=True,
                    height=min(660, 120 + 36 * len(selected_frame)),
                    column_config={
                        "score": st.column_config.ProgressColumn(
                            "Job Match",
                            min_value=0,
                            max_value=100,
                            format="%.1f",
                        ),
                        "readiness": st.column_config.ProgressColumn(
                            "Readiness",
                            min_value=0,
                            max_value=100,
                            format="%.1f",
                        ),
                    },
                )
                d1, d2 = st.columns(2)
                d1.download_button(
                    "Download selected-candidate CSV",
                    selected_csv(results),
                    "selected_candidates.csv",
                    "text/csv",
                    width="stretch",
                )
                d2.download_button(
                    "Download selected resumes as ZIP",
                    selected_zip(results),
                    "selected_resumes.zip",
                    "application/zip",
                    width="stretch",
                    type="primary",
                )
            else:
                st.info("No candidate passed the current screening criteria.")

        with rejected_tab:
            if rejected:
                st.dataframe(
                    pd.DataFrame(rejected)[display_cols],
                    width="stretch",
                    hide_index=True,
                    height=min(660, 120 + 36 * len(rejected)),
                )
            else:
                st.success("No candidates were rejected.")

        with errors_tab:
            if errors:
                st.dataframe(
                    pd.DataFrame(errors)[display_cols],
                    width="stretch",
                    hide_index=True,
                )
            else:
                st.success("Every resume was processed successfully.")

        if selected:
            section_heading("Candidate review", "Open a shortlisted candidate")
            selected_labels = [
                f"{item['candidate']} — {item['score']:.1f}% — {item['filename']}"
                for item in selected
            ]
            chosen_label = st.selectbox("Candidate", selected_labels)
            chosen = selected[selected_labels.index(chosen_label)]
            detail = chosen["analysis"]
            dc1, dc2, dc3, dc4 = st.columns(4)
            dc1.metric("Job Match", f"{detail.get('job_match_score', detail.get('ats_score', 0)):.1f}/100")
            dc2.metric("Readiness", f"{detail.get('resume_readiness_score', 0):.1f}/100")
            dc3.metric("Strong", len(detail.get("matched_skills", [])))
            dc4.metric("Missing", len(detail.get("missing_skills", [])))

            detail_rows = [
                {
                    "Requirement": row.get("requirement"),
                    "Priority": row.get("priority"),
                    "Result": row.get("status"),
                    "Evidence": " | ".join(row.get("evidence", [])) or "No evidence",
                }
                for row in detail.get("requirement_matrix", [])
            ]
            if detail_rows:
                st.dataframe(pd.DataFrame(detail_rows), width="stretch", hide_index=True)
            try:
                detail_report = generate_pdf_report(
                    detail,
                    chosen.get("candidate", ""),
                    detail.get("jd_data", {}).get("job_title", ""),
                )
                st.download_button(
                    "Download this candidate's PDF report",
                    detail_report,
                    file_name=f"{chosen['candidate']}_analysis.pdf",
                    mime="application/pdf",
                    width="stretch",
                    type="primary",
                )
            except Exception as error:
                st.error(f"This candidate's report could not be generated: {error}")
