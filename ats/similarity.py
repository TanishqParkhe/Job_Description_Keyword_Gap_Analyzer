"""Dynamic JD-to-resume matching without a hardcoded skill catalogue."""
from __future__ import annotations

import re
from typing import Any, Iterable

from rapidfuzz import fuzz
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from models.schemas import RequirementEvidence
from utils.text_cleaner import normalize_for_matching, split_sentences



def normalize_skill(value: object) -> str:
    """Create format variants algorithmically, not from a skill dictionary."""
    text = str(value or "").strip().lower()
    text = text.replace("&", " and ")
    text = text.lower().replace("®", "").replace("™", "")
    text = re.sub(r"\.\s*js\b", " js", text)
    text = re.sub(r"(?<=[a-z])js\b", " js", text)
    text = re.sub(r"[^a-z0-9+#]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _compact(value: object) -> str:
    return re.sub(r"[^a-z0-9+#]", "", normalize_skill(value))


def normalize_skill_collection(values: Iterable[object] | None) -> set[str]:
    if values is None:
        return set()
    if isinstance(values, str):
        values = [values]
    return {item for value in values if (item := normalize_skill(value))}


def generated_variants(requirement: object) -> set[str]:
    """Generate punctuation/spacing variants from the requirement itself."""
    raw = str(requirement or "").strip()
    canonical = normalize_skill(raw)
    compact = _compact(raw)
    variants = {canonical, compact}
    tokens = canonical.split()
    compact_raw = _compact(raw)
    if compact_raw.endswith("js") and len(compact_raw) > 2:
        stem = compact_raw[:-2]
        variants.update({stem, stem + "js", stem + ".js", stem + " js"})
    elif tokens and tokens[-1] == "js" and len(tokens) > 1:
        stem = " ".join(tokens[:-1])
        variants.update({stem, stem + "js", stem + ".js", stem + " js"})
    variants.add(re.sub(r"\s+", "", canonical))
    return {v for v in variants if len(v) >= 2}


def _text_contains(requirement: str, text: str) -> tuple[bool, str]:
    """Match generated variants against token n-grams, preserving boundaries."""
    normalized_text = normalize_skill(text)
    tokens = re.findall(r"[a-z0-9+#]+", normalized_text)
    targets = {_compact(variant) for variant in generated_variants(requirement) if _compact(variant)}
    if not targets or not tokens:
        return False, ""
    max_words = min(6, max(1, len(normalize_skill(requirement).split()) + 2))
    candidates: list[tuple[str, str]] = []
    for size in range(1, max_words + 1):
        for index in range(0, len(tokens) - size + 1):
            display = " ".join(tokens[index:index + size])
            phrase = "".join(tokens[index:index + size])
            candidates.append((phrase, display))
            for target in targets:
                if phrase == target:
                    return True, display
                # Accept only algorithmic version/framework suffixes; do not use
                # unrestricted substring matching (which would match Go in Google).
                if phrase.startswith(target):
                    suffix = phrase[len(target):]
                    if suffix.isdigit() or suffix in {"js"}:
                        return True, display
                if target.startswith(phrase):
                    suffix = target[len(phrase):]
                    if suffix.isdigit() or suffix in {"js"}:
                        return True, display
    # High-threshold typo tolerance generated from the current requirement.
    for target in targets:
        if len(target) < 5:
            continue
        best = max(((fuzz.ratio(target, phrase), display) for phrase, display in candidates if abs(len(phrase)-len(target)) <= 2), default=(0, ""))
        if best[0] >= 91:
            return True, best[1]
    return False, ""

def match_requirement(requirement: str, resume_text_or_terms: Iterable[str] | str) -> dict[str, Any]:
    required = normalize_skill(requirement)
    if isinstance(resume_text_or_terms, str):
        found, variant = _text_contains(required, resume_text_or_terms)
        return {"score": 100.0 if found else 0.0, "method": "dynamic text match" if found else "none", "matched_skill": variant if found else ""}
    candidates = sorted(normalize_skill_collection(resume_text_or_terms))
    if not required or not candidates:
        return {"score": 0.0, "method": "none", "matched_skill": ""}
    for candidate in candidates:
        if _compact(required) == _compact(candidate):
            return {"score": 100.0, "method": "format-normalized exact", "matched_skill": candidate}
    best = max(((fuzz.token_set_ratio(required, candidate), candidate) for candidate in candidates), default=(0, ""))
    if best[0] >= 90:
        return {"score": float(best[0]), "method": "dynamic fuzzy", "matched_skill": best[1]}
    return {"score": 0.0, "method": "none", "matched_skill": ""}


def calculate_keyword_similarity(resume_text: object, jd_text: object) -> float:
    """Context similarity built only from the two current documents."""
    resume = normalize_for_matching(resume_text)
    jd = normalize_for_matching(jd_text)
    if not resume or not jd:
        return 0.0
    scores = []
    for analyzer, ngrams, weight in (("word", (1, 3), 0.72), ("char_wb", (3, 5), 0.28)):
        try:
            model = TfidfVectorizer(analyzer=analyzer, ngram_range=ngrams, stop_words="english" if analyzer == "word" else None, max_features=9000)
            matrix = model.fit_transform([resume, jd])
            scores.append(float(cosine_similarity(matrix[0:1], matrix[1:2])[0][0]) * weight)
        except ValueError:
            scores.append(0.0)
    return round(min(100.0, max(0.0, sum(scores) * 100)), 2)


def _evidence(requirement: str, resume_text: str, sections: dict[str, str]) -> tuple[list[str], int]:
    evidence: list[str] = []
    strength = 0
    for section, level in (("experience", 4), ("internships", 4), ("projects", 3), ("skills", 2), ("summary", 1), ("header", 1)):
        for sentence in split_sentences(sections.get(section, "")):
            found, _ = _text_contains(requirement, sentence)
            if found:
                evidence.append(sentence[:320])
                strength = max(strength, level)
                if len(evidence) >= 3:
                    return evidence, strength
    if not evidence:
        for sentence in split_sentences(resume_text):
            found, _ = _text_contains(requirement, sentence)
            if found:
                evidence.append(sentence[:320])
                strength = max(strength, 1)
                if len(evidence) >= 3:
                    break
    return evidence, strength


def build_requirement_matrix(
    resume_text: str,
    resume_data: dict[str, Any],
    mandatory_skills: Iterable[str],
    preferred_skills: Iterable[str] = (),
    general_skills: Iterable[str] = (),
) -> tuple[list[dict[str, Any]], float]:
    matrix: list[dict[str, Any]] = []
    weighted_total = 0.0
    total_weight = 0.0
    seen: set[str] = set()
    sections = resume_data.get("sections", {}) if isinstance(resume_data, dict) else {}
    for priority, items, weight in (("mandatory", mandatory_skills, 2.0), ("preferred", preferred_skills, 1.0), ("general", general_skills, 1.25)):
        for raw in items:
            requirement = str(raw or "").strip()
            key = _compact(requirement)
            if not key or key in seen:
                continue
            seen.add(key)
            found, variant = _text_contains(requirement, resume_text)
            evidence, strength = _evidence(requirement, resume_text, sections)
            if found and strength >= 3:
                status, score = "Strong", 100.0
            elif found:
                status, score = "Partial", 72.0
            else:
                status, score = "Missing", 0.0
            row = RequirementEvidence(
                requirement=requirement,
                priority=priority,
                status=status,
                match_method="dynamic JD-derived text match" if found else "none",
                matched_resume_skill=variant,
                evidence=evidence,
                evidence_strength=strength,
                score=score,
            ).model_dump()
            matrix.append(row)
            weighted_total += score * weight
            total_weight += weight
    return matrix, round(weighted_total / total_weight, 2) if total_weight else 0.0


def calculate_skill_match(resume_skills: Iterable[object] | None, jd_skills: Iterable[object] | None) -> dict[str, Any]:
    required = list(jd_skills or [])
    resume = list(resume_skills or [])
    details, total = [], 0.0
    for item in required:
        result = match_requirement(str(item), resume)
        details.append({"required_skill": item, **result})
        total += result["score"]
    return {
        "skill_score": round(total / len(required), 2) if required else 0.0,
        "matched_skills": [d["required_skill"] for d in details if d["score"] >= 85],
        "partial_skills": [d["required_skill"] for d in details if 45 <= d["score"] < 85],
        "missing_skills": [d["required_skill"] for d in details if d["score"] < 45],
        "details": details,
    }
