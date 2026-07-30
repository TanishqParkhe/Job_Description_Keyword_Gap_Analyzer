"""Formatting helpers shared by UI, database and reports."""

from __future__ import annotations

import json
from typing import Any


def format_score(score: object) -> str:
    try: return f"{float(score):.1f}%"
    except (TypeError, ValueError): return "0.0%"


def format_skill_list(skills: object, empty_text: str = "None detected") -> str:
    if not skills: return empty_text
    if isinstance(skills, str): return skills
    try: values = [str(item).strip() for item in skills if str(item).strip()]
    except TypeError: values = [str(skills).strip()]
    return ", ".join(values) if values else empty_text


def analysis_to_record(analysis: dict[str, Any], candidate_name: str = "", job_title: str = "") -> dict[str, Any]:
    return {
        "candidate_name": candidate_name.strip() or analysis.get("resume_data", {}).get("candidate_name") or "Unknown candidate",
        "job_title": job_title.strip() or analysis.get("jd_data", {}).get("job_title") or "Unspecified role",
        "ats_score": float(analysis.get("ats_score", 0) or 0), "rating": str(analysis.get("rating", "")),
        "matched_skills": list(analysis.get("matched_skills", [])), "missing_skills": list(analysis.get("missing_skills", [])),
        "analysis": analysis,
    }


def analysis_to_json(analysis: dict[str, Any]) -> str:
    return json.dumps(analysis, ensure_ascii=False, default=str)
