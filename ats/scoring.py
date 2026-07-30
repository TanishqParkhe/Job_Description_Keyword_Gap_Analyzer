"""Transparent job-match scoring with resume readiness kept separate."""
from __future__ import annotations

from math import isfinite
from numbers import Real
from typing import Any
import re

from config import (
    ATS_FORMAT_WEIGHT,
    CONTENT_QUALITY_WEIGHT,
    EDUCATION_CERTIFICATION_WEIGHT,
    EXPERIENCE_WEIGHT,
    KEYWORD_WEIGHT,
    PROJECT_WEIGHT,
    SKILL_WEIGHT,
)

JOB_MATCH_WEIGHTS = {
    "skill_score": SKILL_WEIGHT,
    "keyword_score": KEYWORD_WEIGHT,
    "experience_score": EXPERIENCE_WEIGHT,
    "project_score": PROJECT_WEIGHT,
    "education_score": EDUCATION_CERTIFICATION_WEIGHT,
}
READINESS_WEIGHTS = {
    "ats_format_score": ATS_FORMAT_WEIGHT,
    "content_quality_score": CONTENT_QUALITY_WEIGHT,
}
ALL_SCORE_KEYS = tuple(JOB_MATCH_WEIGHTS) + tuple(READINESS_WEIGHTS)


def _score(value: Real, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"'{name}' must be numeric.")
    number = float(value)
    if not isfinite(number):
        raise ValueError(f"'{name}' must be finite.")
    return max(0.0, min(100.0, number))


def _normalised_weights(base: dict[str, float], applicability: dict[str, bool]) -> dict[str, float]:
    active = {key: weight for key, weight in base.items() if applicability.get(key, True)}
    denominator = sum(active.values())
    if denominator <= 0:
        return {key: 0.0 for key in base}
    return {key: active.get(key, 0.0) / denominator for key in base}


def calculate_score_breakdown(
    skill_score: Real,
    keyword_score: Real,
    experience_score: Real,
    project_score: Real,
    education_score: Real,
    ats_format_score: Real = 100,
    content_quality_score: Real = 100,
    applicability: dict[str, bool] | None = None,
) -> dict[str, Any]:
    """Return a job-match score and a separate resume-readiness score.

    Formatting and writing quality are intentionally not included in job match.
    This prevents a polished but irrelevant resume from receiving a misleadingly
    high compatibility percentage.
    """
    raw = locals()
    values = {key: _score(raw[key], key) for key in ALL_SCORE_KEYS}
    applicability = {key: True for key in JOB_MATCH_WEIGHTS} | dict(applicability or {})

    job_weights = _normalised_weights(JOB_MATCH_WEIGHTS, applicability)
    job_contributions = {key: round(values[key] * job_weights[key], 2) for key in JOB_MATCH_WEIGHTS}
    job_match = round(sum(job_contributions.values()), 2)

    readiness_denominator = sum(READINESS_WEIGHTS.values()) or 1.0
    readiness_weights = {key: weight / readiness_denominator for key, weight in READINESS_WEIGHTS.items()}
    readiness_contributions = {key: round(values[key] * readiness_weights[key], 2) for key in READINESS_WEIGHTS}
    readiness = round(sum(readiness_contributions.values()), 2)

    combined_weights = {**job_weights, **{key: 0.0 for key in READINESS_WEIGHTS}}
    combined_contributions = {**job_contributions, **{key: 0.0 for key in READINESS_WEIGHTS}}
    return {
        "final_score": job_match,
        "job_match_score": job_match,
        "resume_readiness_score": readiness,
        "validated_scores": {key: round(value, 2) for key, value in values.items()},
        "weights": combined_weights,
        "job_match_weights": job_weights,
        "readiness_weights": readiness_weights,
        "contributions": combined_contributions,
        "job_match_contributions": job_contributions,
        "readiness_contributions": readiness_contributions,
        "applicability": applicability,
        "not_evaluated": [key for key in JOB_MATCH_WEIGHTS if not applicability.get(key, True)],
        "explanation": "Job Match uses only JD-relevant factors. Resume Readiness is shown separately and does not raise the Job Match score.",
    }


def calculate_final_score(
    skill_score: Real,
    keyword_score: Real,
    experience_score: Real,
    project_score: Real,
    education_score: Real,
    ats_format_score: Real = 100,
    content_quality_score: Real = 100,
) -> float:
    return float(
        calculate_score_breakdown(
            skill_score,
            keyword_score,
            experience_score,
            project_score,
            education_score,
            ats_format_score,
            content_quality_score,
        )["job_match_score"]
    )


def _nonnegative(value: Real, name: str) -> float:
    return max(0.0, _score(value, name))


def calculate_experience_score(candidate_years: Real, required_years: Real) -> float:
    candidate = _nonnegative(candidate_years, "candidate_years")
    required = _nonnegative(required_years, "required_years")
    if required <= 0:
        return 0.0
    return round(min(100.0, candidate / required * 100), 2)


def _compact(value: object) -> str:
    return re.sub(r"[^a-z0-9+#]", "", str(value or "").lower())


def calculate_project_score(projects: object, required_skills: object = None) -> float:
    if not projects:
        return 0.0
    items = projects if isinstance(projects, (list, tuple, set)) else [projects]
    project_text = " ".join(
        " ".join(str(item.get(k, "")) for k in ("title", "duration", "description", "technologies"))
        if isinstance(item, dict)
        else str(item)
        for item in items
    )
    requirements = [str(x) for x in (required_skills or [])] if not isinstance(required_skills, str) else [required_skills]
    if not requirements:
        return 0.0
    compact_project = _compact(project_text)
    matched = sum(1 for item in requirements if _compact(item) and _compact(item) in compact_project)
    return round(min(100.0, matched / max(len(requirements), 1) * 100), 2)


def _degree_rank(text: str) -> int:
    value = str(text or "").lower()
    if re.search(r"ph\s*\.?d|doctor", value):
        return 5
    if re.search(r"master|m\s*\.?tech|m\s*\.?sc|mba|mca", value):
        return 4
    if re.search(r"bachelor|b\s*[-.]?\s*tech|b\s*[-.]?\s*e\b|b\s*[-.]?\s*sc|bca|\bgraduate\b", value):
        return 3
    if "diploma" in value:
        return 2
    if re.search(r"12th|higher secondary|puc", value):
        return 1
    return 0


def calculate_education_certification_score(
    candidate_education: object,
    required_education: object,
    candidate_certifications: object = None,
    required_certifications: object = None,
) -> float:
    def degree_text(value: object) -> str:
        return str(value.get("degree", "")) if isinstance(value, dict) else str(value or "")

    required_rank = _degree_rank(degree_text(required_education))
    if required_rank == 0:
        return 0.0
    candidate_rank = _degree_rank(degree_text(candidate_education))
    degree_score = min(100.0, candidate_rank / required_rank * 100) if candidate_rank else 0.0
    required_certs = {_compact(x) for x in (required_certifications or []) if _compact(x)}
    if not required_certs:
        return round(degree_score, 2)
    candidate_certs = {_compact(x) for x in (candidate_certifications or []) if _compact(x)}
    cert_score = len(required_certs & candidate_certs) / len(required_certs) * 100
    return round((degree_score * 0.75) + (cert_score * 0.25), 2)
