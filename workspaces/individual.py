"""Individual candidate workspace."""
from __future__ import annotations

import io
from typing import Any

import pandas as pd
import streamlit as st

from ats.formatter import analysis_to_record
from chatbot.bhavya_chat import BhavyaChatbot
from config import CHATBOT_NAME, MAX_UPLOAD_SIZE_MB, SUPPORTED_RESUME_FORMATS
from database.db import DatabaseManager
from llm.llm_engine import LLMEngine
from reports.charts import (
    create_plotly_claim_chart,
    create_plotly_gauge,
    create_plotly_readiness_chart,
    create_plotly_requirement_chart,
    create_plotly_score_chart,
)
from services.analysis_service import AnalysisService
from ui.theme import page_heading, section_heading, status_banner
from utils.document_reader import DocumentReadError


def document_input(prefix: str, label: str = "Resume") -> tuple[Any, str]:
    mode = st.radio(
        f"{label} input method",
        ["Upload file", "Paste text"],
        horizontal=True,
        key=f"{prefix}_mode",
        label_visibility="collapsed",
    )
    if mode == "Upload file":
        uploaded = st.file_uploader(
            f"Upload {label.lower()}",
            type=SUPPORTED_RESUME_FORMATS,
            key=f"{prefix}_file",
            help=(
                f"Supported: {', '.join(item.upper() for item in SUPPORTED_RESUME_FORMATS)}. "
                f"Maximum file size: {MAX_UPLOAD_SIZE_MB} MB."
            ),
        )
        return uploaded, ""
    pasted = st.text_area(
        f"Paste {label.lower()} text",
        height=285,
        key=f"{prefix}_text",
        placeholder="Paste the complete resume text here...",
    )
    return None, pasted

def score_explanation(analysis: dict[str, Any]) -> None:
    section_heading(
        "Score transparency",
        "How your Job Match was calculated",
        "Only role-related factors contribute to Job Match. Resume presentation is measured separately.",
    )
    breakdown = analysis.get("score_breakdown", {})
    labels = {
        "skill_score": "Requirements demonstrated",
        "keyword_score": "Overall role relevance",
        "experience_score": "Professional experience",
        "project_score": "Projects or portfolio",
        "education_score": "Education",
    }
    rows: list[dict[str, str]] = []
    for key, label in labels.items():
        raw = float(breakdown.get("validated_scores", {}).get(key, 0) or 0)
        used = bool(breakdown.get("applicability", {}).get(key, True))
        weight = float(breakdown.get("job_match_weights", {}).get(key, 0) or 0) * 100
        points = float(breakdown.get("job_match_contributions", {}).get(key, 0) or 0)
        rows.append(
            {
                "Factor": label,
                "Result": f"{raw:.1f}/100" if used else "Not requested",
                "Weight": f"{weight:.1f}%" if used else "0%",
                "Points added": f"{points:.2f}",
            }
        )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

def _fit_message(score: float) -> str:
    if score >= 80:
        return "Excellent alignment — the resume demonstrates most of the role clearly."
    if score >= 65:
        return "Good alignment — a few targeted improvements could strengthen the application."
    if score >= 50:
        return "Moderate alignment — several role requirements need stronger evidence."
    return "Low alignment — this role currently differs significantly from the resume profile."

def _render_chat(analysis: dict[str, Any], llm_engine: LLMEngine) -> None:
    section_heading(
        "Resume coach",
        f"Ask {CHATBOT_NAME}",
        "Common questions are answered instantly. More open-ended questions use the AI coach when available.",
    )
    quick_prompts = [
        ("Why this score?", "Why is my Job Match score at this level?"),
        ("Missing requirements", "Which requirements are missing from my resume?"),
        ("Top improvements", "What should I improve first?"),
        ("Experience summary", "What experience did you detect?"),
    ]
    quick_cols = st.columns(len(quick_prompts))
    for column, (label, prompt) in zip(quick_cols, quick_prompts):
        if column.button(label, key=f"quick_{label}", width="stretch"):
            st.session_state.pending_chat_question = prompt

    for message in st.session_state.chat_messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    typed_question = st.chat_input(
        "Ask about your score, gaps, improvements or interview preparation"
    )
    question = typed_question or st.session_state.pending_chat_question
    if question:
        st.session_state.pending_chat_question = None
        history = list(st.session_state.chat_messages)
        st.session_state.chat_messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)
        with st.chat_message("assistant"):
            answer = st.write_stream(
                BhavyaChatbot(llm_engine=llm_engine).stream(
                    question,
                    analysis,
                    history,
                )
            )
        st.session_state.chat_messages.append(
            {"role": "assistant", "content": str(answer)}
        )
        st.rerun()

def _build_report(analysis: dict[str, Any], service: AnalysisService) -> bytes | None:
    try:
        return service.build_report(analysis)
    except Exception as error:
        st.error(f"The PDF report could not be generated: {error}")
        return None


def show_analysis(analysis: dict[str, Any], service: AnalysisService, llm_engine: LLMEngine) -> None:
    score = float(analysis.get("job_match_score", analysis.get("ats_score", 0)) or 0)
    status_banner(_fit_message(score))

    cols = st.columns(6)
    cols[0].metric("Job Match", f"{score:.1f}/100")
    cols[1].metric("Resume Readiness", f"{analysis.get('resume_readiness_score', 0):.1f}/100")
    cols[2].metric("Confidence", f"{analysis.get('analysis_confidence', 0):.0f}%")
    cols[3].metric("Strong", len(analysis.get("matched_skills", [])))
    cols[4].metric("Partial", len(analysis.get("partial_skills", [])))
    cols[5].metric("Missing", len(analysis.get("missing_skills", [])))

    report = _build_report(analysis, service)
    if report is not None:
        st.download_button(
            "Download full PDF report",
            report,
            file_name="Bhavya_AI_Resume_Analysis_Report.pdf",
            mime="application/pdf",
            width="stretch",
            type="primary",
        )

    overview_tab, evidence_tab, improvement_tab, coach_tab = st.tabs(
        ["Overview", "Requirement Evidence", "Improvement Plan", "Resume Coach"]
    )

    with overview_tab:
        left, right = st.columns(2)
        with left:
            st.plotly_chart(create_plotly_gauge(analysis), width="stretch")
        with right:
            st.plotly_chart(create_plotly_requirement_chart(analysis), width="stretch")

        strong = len(analysis.get("matched_skills", []))
        partial = len(analysis.get("partial_skills", []))
        missing = len(analysis.get("missing_skills", []))
        total = strong + partial + missing
        if total:
            st.info(
                f"The role contains {total} usable requirements. The resume strongly demonstrates "
                f"{strong}, partially demonstrates {partial}, and does not currently show {missing}."
            )

        score_explanation(analysis)
        st.plotly_chart(create_plotly_score_chart(analysis), width="stretch")

        section_heading(
            "Verified timeline",
            "Experience summary",
            "Professional work, internships, education and projects are kept separate.",
        )
        c1, c2, c3, c4 = st.columns(4)
        professional = float(
            analysis.get(
                "candidate_professional_experience_years",
                analysis.get("candidate_experience_years", 0),
            )
            or 0
        )
        internship = float(analysis.get("candidate_internship_years", 0) or 0)
        if analysis.get("experience_was_stated"):
            c1.metric("Professional experience", f"{professional:g} years")
        else:
            c1.metric("Professional experience", "Not stated")
        if analysis.get("internship_was_stated"):
            c2.metric("Internship / training", f"{internship * 12:.0f} months")
        else:
            c2.metric("Internship / training", "Not stated")
        if analysis.get("experience_evaluated"):
            c3.metric("JD minimum", f"{analysis.get('required_experience_years', 0):g} years")
            c4.metric("Experience result", f"{analysis.get('experience_score', 0):.1f}/100")
        else:
            c3.metric("JD minimum", "Not specified")
            c4.metric("Experience result", "Not evaluated")

        visual_left, visual_right = st.columns(2)
        with visual_left:
            claim_strength = analysis.get("claim_strength", {})
            claim_total = sum(
                float(claim_strength.get(key, 0) or 0)
                for key in ("professional", "project", "listed_only")
            )
            if claim_total:
                st.plotly_chart(create_plotly_claim_chart(analysis), width="stretch")
            else:
                st.info("Evidence-strength visualization will appear when role requirements match.")
        with visual_right:
            st.plotly_chart(create_plotly_readiness_chart(analysis), width="stretch")

    with evidence_tab:
        section_heading(
            "Evidence matrix",
            "What was found — and where",
            "Strong means demonstrated in context; partial means limited evidence; missing means no reliable evidence was found.",
        )
        matrix = analysis.get("requirement_matrix", [])
        if matrix:
            rows = [
                {
                    "Requirement": row.get("requirement"),
                    "Priority": str(row.get("priority", "general")).title(),
                    "Result": row.get("status"),
                    "Resume evidence": " | ".join(row.get("evidence", []))
                    or "No reliable evidence found",
                }
                for row in matrix
            ]
            filter_choice = st.segmented_control(
                "Filter requirements",
                ["All", "Found", "Missing"],
                default="All",
                label_visibility="collapsed",
            )
            visible_rows = rows
            if filter_choice == "Found":
                visible_rows = [row for row in rows if row["Result"] != "Missing"]
            elif filter_choice == "Missing":
                visible_rows = [row for row in rows if row["Result"] == "Missing"]
            if visible_rows:
                st.dataframe(
                    pd.DataFrame(visible_rows),
                    width="stretch",
                    hide_index=True,
                    height=min(760, 115 + 38 * len(visible_rows)),
                )
            else:
                st.success("No requirements are present in this filter.")
        else:
            st.warning("No reliable requirements could be extracted from the job description.")

        mandatory_missing = analysis.get("mandatory_missing", [])
        if mandatory_missing:
            st.error("Missing mandatory requirements: " + ", ".join(mandatory_missing))

    with improvement_tab:
        section_heading(
            "Priorities",
            "What to improve first",
            "Recommendations are ordered by likely value and never ask you to invent experience or skills.",
        )
        actions = analysis.get("action_plan", [])
        if actions:
            action_frame = pd.DataFrame(actions)
            columns = [
                name
                for name in ("priority", "area", "action", "impact", "effort")
                if name in action_frame.columns
            ]
            st.dataframe(action_frame[columns], width="stretch", hide_index=True)
        else:
            st.success("No urgent improvement action was identified.")

        with st.expander("Resume readability and quality checks"):
            checks = pd.DataFrame(analysis.get("quality_checks", []))
            if checks.empty:
                st.info("No quality checks are available for this analysis.")
            else:
                columns = [
                    name
                    for name in ("name", "status", "details", "recommendation")
                    if name in checks.columns
                ]
                st.dataframe(checks[columns], width="stretch", hide_index=True)

        ai_recommendations = analysis.get("ai_recommendations", [])
        if ai_recommendations:
            section_heading("Optional AI review", "Additional tailored suggestions")
            for index, item in enumerate(ai_recommendations, 1):
                st.markdown(f"**{index}.** {item}")

        if st.button("Generate additional tailored suggestions", width="stretch"):
            with st.spinner("Preparing suggestions..."):
                suggestions = llm_engine.enhance_analysis(analysis)
            if suggestions:
                st.session_state.analysis["ai_recommendations"] = suggestions
                st.rerun()
            else:
                st.warning(
                    "Additional suggestions are not available right now. The existing analysis and action plan remain complete."
                )

    with coach_tab:
        _render_chat(analysis, llm_engine)

def individual_page(service: AnalysisService, llm_engine: LLMEngine, database: DatabaseManager) -> None:
    page_heading(
        "Individual Resume Analysis",
        "Compare one resume with one job description and see the exact evidence behind the result.",
    )
    with st.form("individual_analysis_form", clear_on_submit=False):
        left, right = st.columns(2, gap="large")
        with left:
            section_heading("Step 1", "Add the resume")
            candidate = st.text_input("Candidate name", placeholder="Optional")
            source, pasted = document_input("individual")
            experience = st.text_input(
                "Verified professional experience in years",
                placeholder="Optional — enter 0 for a fresher",
            )
        with right:
            section_heading("Step 2", "Add the target role")
            title = st.text_input("Target role", placeholder="Optional")
            jd = st.text_area(
                "Job description",
                height=390,
                placeholder="Paste the complete job description here...",
            )
            save = st.checkbox("Save this analysis in local history", value=False)
        submitted = st.form_submit_button(
            "Analyze Resume",
            type="primary",
            width="stretch",
        )

    if submitted:
        if source is None and not pasted.strip():
            st.error("Upload or paste a resume.")
        elif not jd.strip():
            st.error("Paste the job description.")
        else:
            try:
                with st.spinner("Analyzing the resume and role..."):
                    result = service.analyze_document(
                        source,
                        pasted,
                        jd,
                        candidate,
                        title,
                        experience,
                    )
                st.session_state.analysis = result
                st.session_state.chat_messages = []
                stored_source = source
                if source is not None:
                    stored_source = io.BytesIO(source.getvalue())
                    stored_source.name = source.name
                st.session_state.fast_inputs = {
                    "source": stored_source,
                    "pasted": pasted,
                    "jd": jd,
                    "candidate": candidate,
                    "title": title,
                    "experience": experience,
                }
                if save and database.enabled:
                    database.save_analysis(
                        analysis_to_record(
                            result,
                            result["candidate_name"],
                            result["target_job_title"],
                        )
                    )
            except (DocumentReadError, ValueError) as error:
                st.error(str(error))
            except Exception as error:
                st.error(f"Analysis could not be completed: {error}")

    if st.session_state.analysis:
        st.divider()
        show_analysis(st.session_state.analysis, service, llm_engine)
