"""Explainable ATS-format, content-quality and consistency checks."""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from config import REQUIRED_SECTIONS
from utils.security import detect_prompt_injection
from utils.text_cleaner import clean_text, split_sentences

_ACTION_VERBS = {
    "achieved", "analyzed", "automated", "built", "created", "delivered", "designed", "developed", "drove",
    "implemented", "improved", "increased", "launched", "led", "managed", "optimized", "reduced", "resolved",
    "streamlined", "supported", "tested", "trained", "transformed", "visualized", "collaborated", "engineered",
}
_FIRST_PERSON = re.compile(r"\b(i|me|my|mine|we|our|ours)\b", re.I)
_METRIC = re.compile(r"(?:\b\d+(?:\.\d+)?\s*(?:%|percent|hours?|days?|weeks?|months?|years?|users?|records?|rows?|clients?|customers?|projects?|reports?|₹|\$|usd|inr)\b|[₹$]\s*\d+)", re.I)


def _check(checks: list[dict[str, Any]], category: str, name: str, status: str, severity: str, details: str, recommendation: str = "") -> None:
    checks.append({
        "category": category, "name": name, "status": status, "severity": severity,
        "details": details, "recommendation": recommendation,
    })


def _score_checks(checks: list[dict[str, Any]], category: str) -> float:
    relevant = [item for item in checks if item["category"] == category]
    if not relevant:
        return 100.0
    penalties = {"low": 5, "medium": 12, "high": 24}
    score = 100.0
    for item in relevant:
        if item["status"] == "Review":
            score -= penalties.get(item["severity"], 8) * 0.90
        elif item["status"] == "Problem":
            score -= penalties.get(item["severity"], 12)
    return round(max(0.0, min(100.0, score)), 2)


def analyze_resume_quality(
    resume_text: str,
    resume_data: dict[str, Any],
    metadata: dict[str, Any] | None = None,
    jd_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = clean_text(resume_text)
    metadata = metadata or {}
    sections = resume_data.get("sections", {}) if isinstance(resume_data, dict) else {}
    checks: list[dict[str, Any]] = []

    quality = float(metadata.get("extraction_quality_score", 100) or 0)
    if quality < 52:
        _check(checks, "format", "Extraction reliability", "Problem", "high", f"Only {quality:.0f}% extraction confidence was achieved.", "Use a clearer file or manually verify all extracted content.")
    elif quality < 78:
        _check(checks, "format", "Extraction reliability", "Review", "medium", f"Extraction quality is {quality:.0f}%; some content may be out of order.", "Review names, dates, bullets and skill evidence.")
    else:
        _check(checks, "format", "Extraction reliability", "Safe", "low", "The document produced clear readable text.")

    flags = metadata.get("layout_flags", []) or []
    if any("multi-column" in str(flag).lower() for flag in flags):
        _check(checks, "format", "Column layout", "Review", "medium", "A multi-column layout was detected and reconstructed.", "Use a single-column version when applying through older ATS systems.")
    else:
        _check(checks, "format", "Column layout", "Safe", "low", "No strong multi-column parsing risk was detected.")

    if metadata.get("ocr_pages"):
        _check(checks, "format", "Image/OCR dependence", "Review", "high", f"OCR was needed on page(s): {metadata.get('ocr_pages')}.", "Prefer a text-based PDF or DOCX when possible.")
    else:
        _check(checks, "format", "Image/OCR dependence", "Safe", "low", "Important text was not dependent on OCR.")

    page_count = int(metadata.get("page_count", 1) or 1)
    if page_count > 3:
        _check(checks, "format", "Resume length", "Review", "medium", f"The resume has {page_count} pages.", "For most early-career roles, keep the most relevant content within one or two pages.")
    else:
        _check(checks, "format", "Resume length", "Safe", "low", f"The resume length is {page_count} page(s).")

    missing_sections = []
    for display in REQUIRED_SECTIONS:
        key = display.lower()
        if key == "summary" and not (sections.get("summary") or resume_data.get("summary")):
            missing_sections.append(display)
        elif key == "skills" and not (sections.get("skills") or resume_data.get("all_skills")):
            missing_sections.append(display)
        elif key == "projects" and not resume_data.get("projects"):
            missing_sections.append(display)
        elif key == "experience" and not sections.get("experience") and not sections.get("internships") and not resume_data.get("experience", {}).get("roles") and not resume_data.get("projects"):
            missing_sections.append(display)
        elif key == "education" and not resume_data.get("education", {}).get("degree") and not sections.get("education"):
            missing_sections.append(display)
    if missing_sections:
        _check(checks, "format", "Standard sections", "Review", "medium", "Missing or unrecognized sections: " + ", ".join(missing_sections) + ".", "Use conventional headings so recruiters and ATS parsers can identify the content.")
    else:
        _check(checks, "format", "Standard sections", "Safe", "low", "All core sections were recognized.")

    contact = resume_data.get("contact", {})
    absent_contact = [name for name in ("email", "phone") if not contact.get(name)]
    if absent_contact:
        _check(checks, "content", "Contact information", "Problem", "high", "Missing detected contact fields: " + ", ".join(absent_contact) + ".", "Place a readable email and phone number near the top of the resume.")
    else:
        _check(checks, "content", "Contact information", "Safe", "low", "Email and phone number were detected.")

    bullets = [line.strip(" •-\t") for line in text.splitlines() if line.strip().startswith(("•", "-", "*"))]
    long_bullets = [item for item in bullets if len(item.split()) > 38]
    if long_bullets:
        _check(checks, "content", "Bullet length", "Review", "medium", f"{len(long_bullets)} bullet(s) exceed about 38 words.", "Split long bullets so each communicates one action and one result.")
    else:
        _check(checks, "content", "Bullet length", "Safe", "low", "No excessive bullet length was detected.")

    first_person_count = len(_FIRST_PERSON.findall(text))
    if first_person_count >= 4:
        _check(checks, "content", "First-person wording", "Review", "low", f"First-person words appeared {first_person_count} times.", "Resume bullets are usually stronger without repeated I/my/we wording.")
    else:
        _check(checks, "content", "First-person wording", "Safe", "low", "First-person wording is limited.")

    content_lines = bullets or [item for item in split_sentences(sections.get("experience", "") + "\n" + sections.get("projects", "")) if len(item.split()) >= 5]
    action_count = sum(1 for item in content_lines if item.split() and item.split()[0].lower().strip(".,") in _ACTION_VERBS)
    action_ratio = action_count / len(content_lines) if content_lines else 0
    if content_lines and action_ratio < 0.35:
        _check(checks, "content", "Action-oriented bullets", "Review", "medium", f"Only {action_ratio:.0%} of detected achievement lines begin with a strong action verb.", "Start relevant bullets with truthful action verbs such as developed, analyzed, automated or improved.")
    else:
        _check(checks, "content", "Action-oriented bullets", "Safe", "low", "The detected bullets are reasonably action-oriented.")

    metric_count = sum(1 for item in content_lines if _METRIC.search(item))
    metric_ratio = metric_count / len(content_lines) if content_lines else 0
    if content_lines and metric_ratio < 0.18:
        _check(checks, "content", "Measurable outcomes", "Review", "medium", f"Only {metric_count} of {len(content_lines)} relevant lines contain measurable evidence.", "Add verified scale, time saved, accuracy, users, volume or business impact where genuinely known.")
    else:
        _check(checks, "content", "Measurable outcomes", "Safe", "low", "The resume includes useful measurable evidence.")

    normalized_sentences = [re.sub(r"\W+", " ", item.lower()).strip() for item in split_sentences(text)]
    repeated = [sentence for sentence, count in Counter(normalized_sentences).items() if count >= 2 and len(sentence.split()) >= 6]
    if repeated:
        _check(checks, "content", "Repeated content", "Review", "medium", f"{len(repeated)} repeated statement pattern(s) were detected.", "Remove duplicated bullets and keep the strongest evidence once.")
    else:
        _check(checks, "content", "Repeated content", "Safe", "low", "No substantial repeated statements were detected.")

    words = re.findall(r"\b[a-z][a-z+#.-]{2,}\b", text.lower())
    common = Counter(words).most_common(1)
    if common and common[0][1] > max(15, len(words) * 0.045):
        _check(checks, "content", "Keyword repetition", "Review", "medium", f"The word '{common[0][0]}' appears unusually often ({common[0][1]} times).", "Use keywords naturally and support them with evidence instead of repeating them.")
    else:
        _check(checks, "content", "Keyword repetition", "Safe", "low", "No obvious keyword stuffing was detected.")

    evidence = resume_data.get("skill_evidence", {})
    unsupported = [skill for skill, items in evidence.items() if items and max(int(item.get("strength", 0)) for item in items if isinstance(item, dict)) <= 2]
    if len(unsupported) >= 5:
        _check(checks, "content", "Skill evidence", "Review", "medium", f"{len(unsupported)} skills appear only in the skills/summary area without project or work evidence.", "Demonstrate important skills in truthful project or experience bullets.")
    else:
        _check(checks, "content", "Skill evidence", "Safe", "low", "Most detected skills have reasonable contextual support or the unsupported count is limited.")

    inconsistencies = resume_data.get("possible_inconsistencies", []) or []
    if inconsistencies:
        _check(checks, "content", "Date consistency", "Review", "high", " ".join(str(item) for item in inconsistencies[:3]), "Verify all start/end dates and the stated total experience.")
    else:
        _check(checks, "content", "Date consistency", "Safe", "low", "No obvious date contradiction was detected.")

    injection = detect_prompt_injection(text)
    if injection["findings"]:
        _check(checks, "security", "Embedded instructions", "Review", "high", injection["message"], "Remove irrelevant instructions from the document; the analyzer ignores them.")
    else:
        _check(checks, "security", "Embedded instructions", "Safe", "low", injection["message"])

    return {
        "checks": checks,
        "ats_format_score": _score_checks(checks, "format"),
        "content_quality_score": _score_checks(checks, "content"),
        "security": injection,
        "claim_strength": {
            "professional": sum(1 for items in evidence.values() if any(isinstance(item, dict) and int(item.get("strength", 0)) >= 4 for item in items)),
            "project": sum(1 for items in evidence.values() if any(isinstance(item, dict) and int(item.get("strength", 0)) == 3 for item in items)),
            "listed_only": len(unsupported),
        },
    }
