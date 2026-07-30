"""Defensive parsing and normalization of structured resume/JD data."""

from __future__ import annotations

import copy
import json
import re
from typing import Any

SKILL_CATEGORIES = [
    "technical_skills", "programming_languages", "frameworks", "libraries",
    "databases", "cloud", "tools", "soft_skills", "domain_skills",
]

DEFAULT_RESUME_STRUCTURE: dict[str, Any] = {
    "candidate_name": "", "contact": {"email": "", "phone": "", "linkedin": "", "location": ""},
    "summary": "", "skills": {category: [] for category in SKILL_CATEGORIES}, "all_skills": [],
    "skill_evidence": {}, "experience": {"years": 0.0, "professional_years": 0.0, "calculated_years": 0.0, "internship_years": 0.0, "total_relevant_years": 0.0, "roles": [], "professional_roles": [], "internship_roles": [], "job_titles": [], "source": "not stated", "internship_source": "not stated", "is_stated": False, "internship_is_stated": False},
    "education": {"degree": "", "specialization": "", "institutions": []}, "projects": [],
    "certifications": [], "achievements": [], "languages": [], "sections": {}, "possible_inconsistencies": [],
    "keywords": [], "analysis_source": "unknown",
}

DEFAULT_JD_STRUCTURE: dict[str, Any] = {
    "job_title": "", "company": "", "mandatory_skills": [], "preferred_skills": [], "general_skills": [],
    "skills": {category: [] for category in SKILL_CATEGORIES}, "all_skills": [],
    "experience": {"years": 0.0, "max_years": 0.0},
    "education": {"degree": "", "specialization": ""}, "certifications": [], "responsibilities": [],
    "location": "", "employment_type": "", "shift": "", "domain": "", "keywords": [],
    "analysis_source": "unknown",
}


def _deep_merge(default: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(default)
    for key, item in value.items():
        if key in result and isinstance(result[key], dict) and isinstance(item, dict):
            result[key] = _deep_merge(result[key], item)
        else:
            result[key] = item
    return result


def _list(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, (tuple, set)):
        return list(value)
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[,;|\n]", value) if item.strip()]
    return [value]


def _number(value: object) -> float:
    try:
        return max(0.0, float(value or 0))
    except (TypeError, ValueError):
        return 0.0


def _coerce_mapping_shapes(data: object, schema: str) -> dict[str, Any]:
    """Convert common LLM shape mistakes into the expected mapping structure.

    Local parsing remains the source of truth. This function only prevents malformed
    optional AI output (for example ``"skills": ["Python"]``) from crashing the app.
    """
    if isinstance(data, list):
        dictionaries = [item for item in data if isinstance(item, dict)]
        if dictionaries:
            merged: dict[str, Any] = {}
            for item in dictionaries:
                merged.update(item)
            data = merged
        else:
            values = [str(item).strip() for item in data if str(item).strip()]
            data = (
                {"general_skills": values}
                if schema == "jd"
                else {"skills": {"technical_skills": values}}
            )

    raw = copy.deepcopy(data) if isinstance(data, dict) else {}

    skills = raw.get("skills")
    if not isinstance(skills, dict):
        raw["skills"] = {"technical_skills": _list(skills)}

    if schema == "resume":
        if not isinstance(raw.get("contact"), dict):
            raw["contact"] = {}
        experience = raw.get("experience")
        if isinstance(experience, list):
            raw["experience"] = {"roles": experience}
        elif not isinstance(experience, dict):
            raw["experience"] = {"years": experience}
        education = raw.get("education")
        if isinstance(education, list):
            raw["education"] = {"institutions": education}
        elif not isinstance(education, dict):
            raw["education"] = {"degree": str(education or "")}
        if not isinstance(raw.get("skill_evidence"), dict):
            raw["skill_evidence"] = {}
        if not isinstance(raw.get("sections"), dict):
            raw["sections"] = {}
    else:
        experience = raw.get("experience")
        if not isinstance(experience, dict):
            raw["experience"] = {"years": experience}
        education = raw.get("education")
        if isinstance(education, list):
            raw["education"] = {"degree": ", ".join(str(x) for x in education)}
        elif not isinstance(education, dict):
            raw["education"] = {"degree": str(education or "")}

    return raw


def normalize_structure(data: object, schema: str = "resume") -> dict[str, Any]:
    default = DEFAULT_JD_STRUCTURE if schema == "jd" else DEFAULT_RESUME_STRUCTURE
    raw = _coerce_mapping_shapes(data, schema)
    result = _deep_merge(default, raw)

    # Defend again after merging in case a future caller bypasses the coercion helper.
    if not isinstance(result.get("skills"), dict):
        result["skills"] = {category: [] for category in SKILL_CATEGORIES}
    for category in SKILL_CATEGORIES:
        result["skills"][category] = [
            str(item).strip()
            for item in _list(result["skills"].get(category))
            if str(item).strip()
        ]

    if schema == "resume":
        if not isinstance(result.get("experience"), dict):
            result["experience"] = copy.deepcopy(DEFAULT_RESUME_STRUCTURE["experience"])
        result["experience"]["years"] = _number(result["experience"].get("years"))
        result["experience"]["calculated_years"] = _number(result["experience"].get("calculated_years"))
        result["experience"]["professional_years"] = _number(
            result["experience"].get("professional_years", result["experience"].get("years"))
        )
        result["experience"]["internship_years"] = _number(result["experience"].get("internship_years"))
        result["experience"]["total_relevant_years"] = _number(result["experience"].get("total_relevant_years"))
        for key in ("projects", "certifications", "achievements", "languages", "possible_inconsistencies"):
            result[key] = _list(result.get(key))
    else:
        if not isinstance(result.get("experience"), dict):
            result["experience"] = copy.deepcopy(DEFAULT_JD_STRUCTURE["experience"])
        result["experience"]["years"] = _number(result["experience"].get("years"))
        result["experience"]["max_years"] = _number(result["experience"].get("max_years"))
        for key in ("mandatory_skills", "preferred_skills", "general_skills", "certifications", "responsibilities"):
            result[key] = [str(item).strip() for item in _list(result.get(key)) if str(item).strip()]

    result["all_skills"] = flatten_skills(result)
    result["skills_flat"] = list(result["all_skills"])
    return result


def _decode_json_value(text: str) -> Any:
    """Decode plain or fenced JSON, accepting either an object or an array."""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S).strip()
    candidates = [cleaned]
    object_start, object_end = cleaned.find("{"), cleaned.rfind("}")
    array_start, array_end = cleaned.find("["), cleaned.rfind("]")
    if object_start >= 0 and object_end > object_start:
        candidates.append(cleaned[object_start:object_end + 1])
    if array_start >= 0 and array_end > array_start:
        candidates.append(cleaned[array_start:array_end + 1])
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except (json.JSONDecodeError, TypeError):
            continue
    return {}


def parse_llm_response(response: object, schema: str = "resume") -> dict[str, Any]:
    if isinstance(response, (dict, list)):
        return normalize_structure(response, schema)
    value = _decode_json_value(str(response or ""))
    return normalize_structure(value, schema)

def flatten_skills(data: object) -> list[str]:
    if not isinstance(data, dict):
        return []
    values: list[str] = []
    skills = data.get("skills", {})
    if isinstance(skills, dict):
        for items in skills.values():
            values.extend(str(item).strip() for item in _list(items) if str(item).strip())
    for key in ("all_skills", "mandatory_skills", "preferred_skills", "general_skills", "keywords"):
        values.extend(str(item).strip() for item in _list(data.get(key)) if str(item).strip())
    deduplicated: list[str] = []
    seen: set[str] = set()
    for item in values:
        normalized = item.lower()
        if normalized not in seen:
            seen.add(normalized)
            deduplicated.append(item)
    return deduplicated
