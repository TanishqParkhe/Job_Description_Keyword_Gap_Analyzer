"""Deterministic resume and job-description extraction used by fast analysis."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

from dateutil import parser as date_parser

from llm.parser import normalize_structure
from utils.text_cleaner import clean_text, normalize_for_matching, split_sentences

_SECTION_ALIASES = {
    "summary": {"summary", "professional summary", "profile", "career objective", "objective", "about me"},
    "skills": {"skills", "technical skills", "core competencies", "technologies", "tools and technologies", "expertise", "key skills"},
    "experience": {"experience", "work experience", "professional experience", "employment", "employment history", "career history", "work history", "professional background", "employment record", "career experience", "work profile", "professional career"},
    "projects": {"projects", "project experience", "academic projects", "personal projects", "key projects"},
    "education": {"education", "academic background", "academic qualifications", "qualifications"},
    "certifications": {"certifications", "certificates", "professional certifications"},
    "achievements": {"achievements", "awards", "accomplishments"},
    "languages": {"languages", "language proficiency"},
    "internships": {"internship", "internships", "internship experience", "training and internships", "industrial training", "work placement"},
}
_HEADING_LOOKUP = {alias: canonical for canonical, aliases in _SECTION_ALIASES.items() for alias in aliases}
_MONTHS = "jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december"
_DATE_TOKEN = rf"(?:(?:{_MONTHS})[ .'-]*\d{{2,4}}|\d{{4}})"
_DATE_RANGE = re.compile(rf"(?P<start>{_DATE_TOKEN})\s*(?:-|–|—|to)\s*(?P<end>present|current|now|{_DATE_TOKEN})", re.I)


def _heading(line: str) -> str:
    value = re.sub(r"[:\-–—]+$", "", normalize_for_matching(line)).strip()
    return _HEADING_LOOKUP.get(value, "") if len(value) <= 55 else ""


def split_sections(text: object) -> dict[str, str]:
    sections: dict[str, list[str]] = {"header": []}
    current = "header"
    for line in clean_text(text).splitlines():
        found = _heading(line)
        if found:
            current = found
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return {name: clean_text("\n".join(lines)) for name, lines in sections.items() if clean_text("\n".join(lines))}


def _candidate_name(sections: dict[str, str]) -> str:
    for line in sections.get("header", "").splitlines()[:6]:
        value = line.strip(" |•-")
        if not value or "@" in value or re.search(r"\d{5,}", value) or len(value) > 70:
            continue
        if 2 <= len(value.split()) <= 5 and not any(word in value.lower() for word in ("resume", "curriculum", "developer", "analyst", "engineer")):
            return value
    return ""


def _contacts(text: str) -> dict[str, str]:
    email = re.search(r"(?i)\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", text)
    phone = re.search(r"(?<!\d)(\+?\d[\d\s().-]{7,}\d)(?!\d)", text)
    linkedin = re.search(r"(?i)(?:https?://)?(?:www\.)?linkedin\.com/\S+", text)
    return {"email": email.group(0) if email else "", "phone": phone.group(1).strip() if phone else "", "linkedin": linkedin.group(0).rstrip(".,)") if linkedin else "", "location": ""}


def _parse_date(value: str) -> date | None:
    if normalize_for_matching(value) in {"present", "current", "now"}:
        return date.today()
    try:
        parsed = date_parser.parse(value, default=datetime(2000, 1, 1), fuzzy=False)
        if parsed.year < 1950 or parsed.year > date.today().year + 1:
            return None
        return date(parsed.year, parsed.month, 1)
    except (ValueError, OverflowError):
        return None


def _months_between(start: date, end: date) -> int:
    return max(0, (end.year - start.year) * 12 + end.month - start.month + 1)


def _merge_intervals(intervals: list[tuple[date, date]]) -> int:
    if not intervals:
        return 0
    merged: list[list[date]] = []
    for start, end in sorted(intervals):
        if not merged or (start.year, start.month) > (merged[-1][1].year, merged[-1][1].month + 1):
            merged.append([start, end])
        elif end > merged[-1][1]:
            merged[-1][1] = end
    return sum(_months_between(start, end) for start, end in merged)


def _dated_intervals(section_text: str, kind: str) -> tuple[list[tuple[date, date]], list[dict[str, Any]], list[str]]:
    intervals: list[tuple[date, date]] = []
    roles: list[dict[str, Any]] = []
    inconsistencies: list[str] = []
    for line in clean_text(section_text).splitlines():
        for match in _DATE_RANGE.finditer(line):
            start, end = _parse_date(match.group("start")), _parse_date(match.group("end"))
            if not start or not end:
                continue
            if start > end:
                inconsistencies.append(f"A {kind.lower()} date range appears reversed: {match.group(0)}")
                continue
            intervals.append((start, end))
            roles.append({
                "type": kind,
                "text": line[:320],
                "start": start.isoformat(),
                "end": end.isoformat(),
                "months": _months_between(start, end),
            })
    return intervals, roles, inconsistencies


def _resume_experience(text: str, sections: dict[str, str]) -> dict[str, Any]:
    """Keep full-time/professional work and internship duration separate.

    Education, certification and project dates are never searched. Internship
    duration is visible to the user but is not silently converted into full-time
    professional experience.
    """
    professional_source = clean_text(sections.get("experience", ""))
    internship_source = clean_text(sections.get("internships", ""))
    explicit_patterns = [
        r"(?i)\b(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+of\s+(?:professional|full[- ]time|work|industry|relevant)\s+experience\b",
        r"(?i)\b(?:professional|full[- ]time|work|industry|relevant)\s+experience\s+(?:of|:)?\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\b",
    ]
    explicit = 0.0
    for pattern in explicit_patterns:
        match = re.search(pattern, text)
        if match:
            explicit = float(match.group(1))
            break

    professional_intervals, professional_roles, professional_issues = _dated_intervals(professional_source, "Professional work")
    internship_intervals, internship_roles, internship_issues = _dated_intervals(internship_source, "Internship/training")
    calculated_professional = round(_merge_intervals(professional_intervals) / 12, 2)
    internship_years = round(_merge_intervals(internship_intervals) / 12, 2)
    professional_years = explicit if explicit else calculated_professional
    source = "explicit professional-experience statement" if explicit else "verified professional work-section dates" if calculated_professional else "not stated"
    inconsistencies = professional_issues + internship_issues
    if explicit and calculated_professional and abs(explicit - calculated_professional) > 1.5:
        inconsistencies.append(
            f"The explicit professional experience ({explicit:g} years) differs from verified professional-work dates ({calculated_professional:g} years)."
        )
    return {
        "years": professional_years,
        "professional_years": professional_years,
        "calculated_years": calculated_professional,
        "internship_years": internship_years,
        "total_relevant_years": round(professional_years + internship_years, 2),
        "roles": professional_roles + internship_roles,
        "professional_roles": professional_roles,
        "internship_roles": internship_roles,
        "job_titles": [],
        "inconsistencies": inconsistencies,
        "source": source,
        "internship_source": "verified internship/training date ranges" if internship_years else "not stated",
        "is_stated": bool(explicit or calculated_professional),
        "internship_is_stated": bool(internship_years),
    }

def _jd_experience(text: str) -> dict[str, Any]:
    patterns = [
        r"(?i)(?:minimum|min\.?|at least|required)?\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)\s+(?:of\s+)?(?:professional|work|industry|relevant|hands-on)?\s*experience",
        r"(?i)experience\s*(?:required|needed|:|of)?\s*(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)",
    ]
    years = 0.0
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            years = float(match.group(1)); break
    range_match = re.search(r"(?i)(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)\s+(?:of\s+)?experience", text)
    maximum = 0.0
    if range_match:
        years, maximum = float(range_match.group(1)), float(range_match.group(2))
    return {"years": years, "max_years": maximum, "is_stated": bool(years), "source": "job description" if years else "not specified"}


def _education(text: str) -> dict[str, Any]:
    """Return the highest clearly detected qualification, not the last one."""
    normalized = normalize_for_matching(text)
    candidates: list[tuple[int, str]] = []
    patterns = [
        (5, "PhD", r"\b(ph\s*d|doctorate|doctoral)\b"),
        (4, "Master's degree", r"\b(master'?s?|m\s*tech|m\s*sc|mba|mca)\b"),
        (3, "Bachelor's degree", r"\b(bachelor'?s?|b\s*tech|b\s*e\b|b\s*sc|bca|any graduate|graduate)\b"),
        (2, "Diploma", r"\bdiploma\b"),
    ]
    for rank, display, pattern in patterns:
        if re.search(pattern, normalized, re.I):
            candidates.append((rank, display))
    degree = max(candidates, default=(0, ""))[1]
    return {"degree": degree, "specialization": "", "institutions": []}

def _section_items(section: str, limit: int = 30) -> list[str]:
    result = []
    for line in clean_text(section).splitlines():
        value = line.strip(" •-\t")
        if 3 <= len(value) <= 700:
            result.append(value)
        if len(result) >= limit:
            break
    return result


def _project_items(section: str) -> list[dict[str, Any]]:
    """Group project headings, duration and bullets into coherent projects."""
    lines = [line.strip(" •-\t") for line in clean_text(section).splitlines() if line.strip(" •-\t")]
    projects: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    def flush() -> None:
        nonlocal current
        if current and (current.get("title") or current.get("bullets")):
            current["description"] = " ".join(current.pop("bullets", []))
            projects.append(current)
        current = None

    for line in lines:
        if re.match(r"(?i)^duration\s*:", line):
            if current is None:
                current = {"title": "Project", "duration": "", "bullets": [], "technologies": []}
            current["duration"] = re.sub(r"(?i)^duration\s*:\s*", "", line).strip()
            continue
        looks_like_bullet = bool(re.match(r"(?i)^(developed|built|created|designed|implemented|automated|reduced|improved|programmed|used|integrated|analyzed|trained|deployed|worked|assisted)\b", line))
        if looks_like_bullet:
            if current is None:
                current = {"title": "Project", "duration": "", "bullets": [], "technologies": []}
            current["bullets"].append(line)
            continue
        # PDF line wrapping can split one bullet into short lowercase fragments.
        if current and current.get("bullets") and line[:1].islower():
            current["bullets"][-1] = current["bullets"][-1].rstrip() + " " + line
            continue
        if len(line) <= 140 and len(line.split()) <= 16:
            flush()
            current = {"title": line, "duration": "", "bullets": [], "technologies": []}
        else:
            if current is None:
                current = {"title": "Project", "duration": "", "bullets": [], "technologies": []}
            current["bullets"].append(line)
    flush()
    return projects[:20]

def _split_compound_technology_text(value: str) -> list[str]:
    """Split concatenated job-board key skills without a technology dictionary."""
    pieces: list[str] = []
    for raw in re.split(r"[,;|•\n]|\.\s+(?=[A-Z])|\s+/\s+|\s+and\s+", value):
        raw = raw.strip(" .:()[]{}-'\"")
        if not raw:
            continue
        # Node.jsReact.js -> Node.js, React.js
        subparts = re.split(r"(?<=\.js)(?=[A-Z])", raw)
        for part in subparts:
            # TypeScriptCSSJavascriptHTML -> TypeScript, CSS, Javascript, HTML
            if re.fullmatch(r"(?:[A-Z][a-z]+){2,}[A-Z]{2,}.*", part) or re.search(r"[A-Z]{2,}[A-Z][a-z]", part):
                tokens = re.findall(r"[A-Z][a-z]+(?:[A-Z][a-z]+)*|[A-Z]{2,}(?=[A-Z]|$)|[A-Z]+\d+", part)
                pieces.extend(tokens or [part])
            else:
                pieces.append(part)
    return pieces


def _technical_shape(value: str) -> bool:
    value = value.strip()
    if not (2 <= len(value) <= 55) or len(value.split()) > 5:
        return False
    return bool(re.search(r"\d|[.+#/-]", value) or re.fullmatch(r"[A-Z][A-Z0-9-]{1,11}", value) or re.search(r"[a-z][A-Z]|[A-Z][a-z]", value))


def _clean_requirement(value: str) -> str:
    value = re.sub(r"(?i)\b(hands?[- ]on|strong|good|excellent|sound|proficiency|proficient|working knowledge|experience with|experience in|knowledge of|familiarity with|secure coding standards?)\b", "", value)
    value = re.sub(r"(?i)\b(skills?|keyskills?|required|preferred|mandatory|desired|qualification|technically)\b", "", value)
    value = re.sub(r"(?i)\s+experience$", "", value)
    return re.sub(r"\s+", " ", value).strip(" .:;-()[]{}")


def _extract_requirements(text: str) -> tuple[list[str], list[str], list[str]]:
    """Discover requirement terms only from the current JD.

    The parser uses layout, punctuation and grammar. It does not consult a
    technology catalogue. Job-board labels and explanatory boilerplate are
    filtered before matching.
    """
    mandatory: list[str] = []
    preferred: list[str] = []
    general: list[str] = []
    lines = clean_text(text).splitlines()
    in_key_skills = False
    in_requirement_block = False
    requirement_block_priority = "general"
    ignored_metadata = re.compile(r"(?i)^(role|industry type|department|employment type|role category|education|ug|pg|location)\s*:")
    boilerplate = re.compile(r"(?i)skills?\s+highlighted.*preferred\s+key\s*skills?|preferred\s+key\s*skills?\s+are\s+highlighted")
    non_skill_phrase = re.compile(r"(?i)\b(should|able to|provide solutions?|technically sound|responsible for|work with team|excellent communication)\b")

    def add(value: str, priority: str, explicit: bool = False) -> None:
        cleaned = _clean_requirement(value)
        if not cleaned or boilerplate.search(cleaned) or non_skill_phrase.search(cleaned):
            return
        if not explicit and not _technical_shape(cleaned):
            return
        if explicit and (len(cleaned.split()) > 5 or len(cleaned) > 60 or not re.search(r"[A-Za-z]", cleaned)):
            return
        compact = re.sub(r"[^a-z0-9+#]", "", cleaned.lower())
        generic_labels = {
            "hand", "handson", "secure", "role", "full", "stack", "developer", "industry", "type", "services",
            "consulting", "department", "engineering", "software", "employment", "time", "permanent", "category",
            "education", "any", "graduate", "specialization", "keyskills", "skills", "preferredkeyskills",
        }
        if not compact or compact in generic_labels:
            return
        for bucket in (mandatory, preferred, general):
            for existing in list(bucket):
                if re.sub(r"[^a-z0-9+#]", "", existing.lower()) == compact:
                    if priority == "mandatory" and bucket is not mandatory:
                        bucket.remove(existing); mandatory.append(existing)
                    elif priority == "preferred" and bucket is general:
                        bucket.remove(existing); preferred.append(existing)
                    return
        (preferred if priority == "preferred" else mandatory if priority == "mandatory" else general).append(cleaned)

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()
        if not stripped or boilerplate.search(stripped):
            continue
        if re.fullmatch(r"(?i)(key\s*skills?|skills?)\s*:??", stripped):
            in_key_skills = True
            in_requirement_block = False
            continue
        if re.fullmatch(r"(?i)(requirements?|qualifications?|must have|what you bring|preferred qualifications?)\s*:??", stripped):
            in_requirement_block = True
            in_key_skills = False
            requirement_block_priority = "preferred" if "preferred" in lower else "mandatory" if "must" in lower else "general"
            continue
        if (in_key_skills or in_requirement_block) and ignored_metadata.match(stripped):
            in_key_skills = False
            in_requirement_block = False
        if in_requirement_block and re.fullmatch(r"(?i)(responsibilities|about us|benefits|what we offer|job description)\s*:??", stripped):
            in_requirement_block = False

        candidate_source = stripped if in_key_skills else stripped.lstrip("-•* ") if in_requirement_block else ""
        priority = requirement_block_priority if in_requirement_block else "general"
        marker = re.search(
            r"(?i)(hands?[- ]on|must have|you must have|you should have|required skills?|requirements?|mandatory|preferred|nice to have|good to have|knowledge of|experience (?:with|in)|proficient in)\s*[:\-]?\s*(.+)",
            stripped,
        )
        if marker:
            candidate_source = marker.group(2)
            priority = "preferred" if re.search(r"(?i)preferred|nice to have|good to have", marker.group(1)) else "mandatory" if re.search(r"(?i)must|required|mandatory", marker.group(1)) else "general"

        candidate_source = re.split(r"(?i)\b(?:secure coding|technically sound|should be able|responsibilities?)\b", candidate_source)[0]
        for piece in _split_compound_technology_text(candidate_source):
            add(piece, priority, explicit=True)

        for acronym in re.findall(r"\(([A-Z][A-Z0-9.+#-]{1,15})\)", stripped):
            add(acronym, priority, explicit=True)
        exp_term = re.search(r"\b([A-Z][A-Za-z0-9.+#-]{1,30})\s+experience\b", stripped)
        if exp_term:
            add(exp_term.group(1), priority, explicit=True)

    # Job boards often repeat the same technology with and without a version
    # suffix (for example HTML and HTML5, CSS and CSS3). Deduplicate these
    # algorithmically without consulting a technology catalogue. The more
    # specific versioned spelling is retained, while the strongest priority
    # found for either spelling is preserved.
    priority_rank = {"general": 0, "preferred": 1, "mandatory": 2}
    entries: list[tuple[str, str, int]] = []
    for bucket_name, bucket in (("mandatory", mandatory), ("preferred", preferred), ("general", general)):
        for position, item in enumerate(bucket):
            entries.append((item, bucket_name, position))

    groups: dict[str, list[tuple[str, str, int, str]]] = {}
    for item, bucket_name, position in entries:
        compact = re.sub(r"[^a-z0-9+#]", "", item.lower())
        family = re.sub(r"\d+$", "", compact) or compact
        groups.setdefault(family, []).append((item, bucket_name, position, compact))

    rebuilt = {"mandatory": [], "preferred": [], "general": []}
    ordered_groups = sorted(groups.values(), key=lambda group: min(item[2] for item in group))
    for group in ordered_groups:
        strongest = max(group, key=lambda item: priority_rank[item[1]])[1]
        # Prefer a trailing-version form when both a base and versioned form
        # were discovered; otherwise keep the earliest spelling from the JD.
        chosen = max(
            group,
            key=lambda item: (
                bool(re.search(r"\d+$", item[3])),
                len(re.search(r"\d+$", item[3]).group(0)) if re.search(r"\d+$", item[3]) else 0,
                -item[2],
            ),
        )[0]
        rebuilt[strongest].append(chosen)

    return rebuilt["mandatory"], rebuilt["preferred"], rebuilt["general"]

def _job_title(text: str) -> str:
    match = re.search(r"(?i)(?:job title|position|role)\s*[:\-]\s*([^\n]{2,100})", text)
    if match:
        return match.group(1).strip()
    for line in clean_text(text).splitlines()[:15]:
        if 2 <= len(line.split()) <= 8 and re.search(r"(?i)developer|engineer|analyst|manager|consultant|architect|specialist|intern", line):
            return line.strip(" :-")
    return ""


def _offline_resume(text: str) -> dict[str, Any]:
    sections = split_sections(text)
    experience = _resume_experience(text, sections)
    result = {
        "candidate_name": _candidate_name(sections),
        "contact": _contacts(text),
        "summary": sections.get("summary", ""),
        "skills": {}, "all_skills": [], "skill_evidence": {},
        "experience": experience,
        "education": _education(sections.get("education", "") or ""),
        "projects": _project_items(sections.get("projects", "")),
        "certifications": _section_items(sections.get("certifications", "")),
        "achievements": _section_items(sections.get("achievements", "")),
        "languages": _section_items(sections.get("languages", "")),
        "sections": sections,
        "possible_inconsistencies": experience.get("inconsistencies", []),
        "keywords": [],
        "analysis_source": "fast local parser (no AI, no skill catalogue)",
    }
    return normalize_structure(result, "resume")


def _offline_jd(text: str) -> dict[str, Any]:
    mandatory, preferred, general = _extract_requirements(text)
    normalized = normalize_for_matching(text)
    comparison_lines = []
    for line in clean_text(text).splitlines():
        lower = line.lower().strip()
        if re.match(r"^(industry type|department|employment type|role category)\s*:", lower):
            continue
        if "skills highlighted" in lower or "equal opportunity" in lower or "diversity and inclusion" in lower:
            continue
        comparison_lines.append(line)
    comparison_text = clean_text("\n".join(comparison_lines))
    employment = next((item for item in ("full time", "part time", "contract", "internship", "temporary", "permanent") if item in normalized), "")
    location_match = re.search(r"(?i)(?:location|job location)\s*[:\-]\s*([^\n]{2,100})", text)
    result = {
        "job_title": _job_title(text),
        "mandatory_skills": mandatory, "preferred_skills": preferred, "general_skills": general,
        "skills": {}, "all_skills": mandatory + preferred + general,
        "experience": _jd_experience(text),
        "education": _education(text),
        "certifications": [],
        "responsibilities": [item for item in split_sentences(comparison_text) if len(item.split()) >= 4 and not re.search(r"(?i)skills? highlighted|industry type|role category|employment type", item)][:30],
        "location": location_match.group(1).strip() if location_match else "",
        "employment_type": employment, "shift": "", "domain": "", "keywords": [],
        "comparison_text": comparison_text,
        "analysis_source": "fast local parser (JD-derived requirements only)",
    }
    return normalize_structure(result, "jd")


def _merge_nonempty(base: Any, enhanced: Any) -> Any:
    """Merge optional AI output without allowing type mismatches to corrupt local data."""
    if isinstance(base, dict):
        if not isinstance(enhanced, dict):
            return base
        result = dict(base)
        for key, value in enhanced.items():
            result[key] = _merge_nonempty(result.get(key), value)
        return result
    if isinstance(base, list):
        if not isinstance(enhanced, list):
            return base
        combined: list[Any] = []
        fingerprints: set[str] = set()
        for item in base + enhanced:
            try:
                fingerprint = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
            except TypeError:
                fingerprint = str(item)
            if fingerprint not in fingerprints:
                fingerprints.add(fingerprint)
                combined.append(item)
        return combined
    if enhanced in (None, "", [], {}, 0, 0.0):
        return base
    return enhanced


