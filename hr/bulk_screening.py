"""Reusable, privacy-preserving HR bulk screening."""
from __future__ import annotations

import io
import zipfile
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

from ats.ats_engine import ATSEngine
from config import BULK_WORKERS
from llm.llm_engine import LLMEngine
from utils.document_reader import read_document
from utils.security import safe_filename
from utils.text_cleaner import clean_text

DISPLAY_COLUMNS = [
    "candidate",
    "filename",
    "score",
    "readiness",
    "confidence",
    "strong",
    "partial",
    "missing",
    "mandatory_missing",
    "decision",
    "reason",
]


def _file_bytes(item: Any) -> tuple[bytes, str]:
    name = safe_filename(getattr(item, "name", "resume"))
    if isinstance(item, (bytes, bytearray)):
        return bytes(item), name
    if hasattr(item, "getvalue"):
        return bytes(item.getvalue()), name
    if hasattr(item, "read"):
        if hasattr(item, "seek"):
            item.seek(0)
        raw = item.read()
        if hasattr(item, "seek"):
            item.seek(0)
        return bytes(raw), name
    raise ValueError("Unsupported bulk resume input.")


def _screen_one(
    item: Any,
    *,
    cleaned_jd: str,
    jd_data: dict[str, Any],
    threshold: float,
    mandatory_gate: bool,
    llm_engine: LLMEngine,
    ats_engine: ATSEngine,
) -> dict[str, Any]:
    raw, filename = _file_bytes(item)
    try:
        holder = io.BytesIO(raw)
        holder.name = filename
        document = read_document(holder)
        resume_data = llm_engine.extract_resume_data(document.text)
        analysis = ats_engine.analyze_resume(
            resume_text=document.text,
            jd_text=cleaned_jd,
            resume_data=resume_data,
            jd_data=jd_data,
            resume_metadata=document.metadata.model_dump(),
        )
        job_match = float(
            analysis.get("job_match_score", analysis.get("ats_score", 0.0))
        )
        passes_score = job_match >= float(threshold)
        passes_gate = not mandatory_gate or not analysis.get("mandatory_missing")
        selected = passes_score and passes_gate
        reason = (
            "Passed screening criteria"
            if selected
            else "Below the selected Job Match threshold"
            if not passes_score
            else "Missing a mandatory requirement"
        )
        return {
            "filename": filename,
            "candidate": resume_data.get("candidate_name") or filename,
            "score": round(job_match, 2),
            "readiness": round(float(analysis.get("resume_readiness_score", 0.0)), 2),
            "confidence": round(float(analysis.get("analysis_confidence", 0.0)), 2),
            "strong": len(analysis.get("matched_skills", [])),
            "partial": len(analysis.get("partial_skills", [])),
            "missing": len(analysis.get("missing_skills", [])),
            "mandatory_missing": ", ".join(analysis.get("mandatory_missing", [])),
            "decision": "Selected" if selected else "Rejected",
            "reason": reason,
            "file_bytes": raw,
            "analysis": analysis,
        }
    except Exception as error:
        return {
            "filename": filename,
            "candidate": filename,
            "score": 0.0,
            "readiness": 0.0,
            "confidence": 0.0,
            "strong": 0,
            "partial": 0,
            "missing": 0,
            "mandatory_missing": "",
            "decision": "Error",
            "reason": str(error),
            "file_bytes": raw,
            "analysis": {},
        }


def screen_resumes(
    files: Iterable[Any],
    jd_text: str,
    *,
    threshold: float,
    mandatory_gate: bool = False,
    llm_engine: LLMEngine | None = None,
    ats_engine: ATSEngine | None = None,
    progress: Callable[[int, int], None] | None = None,
    workers: int | None = None,
) -> list[dict[str, Any]]:
    """Screen resumes locally without contacting Ollama.

    Independent resumes are processed concurrently to keep large HR batches
    responsive. The job description is parsed only once and reused safely.
    """
    llm_engine = llm_engine or LLMEngine()
    ats_engine = ats_engine or ATSEngine()
    cleaned_jd = clean_text(jd_text)
    if not cleaned_jd:
        raise ValueError("Job description is empty.")
    jd_data = llm_engine.extract_job_description_data(cleaned_jd)
    items = list(files)
    if not items:
        return []

    max_workers = max(1, min(int(workers or BULK_WORKERS), len(items), 8))
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="resume") as pool:
        futures = [
            pool.submit(
                _screen_one,
                item,
                cleaned_jd=cleaned_jd,
                jd_data=jd_data,
                threshold=threshold,
                mandatory_gate=mandatory_gate,
                llm_engine=llm_engine,
                ats_engine=ats_engine,
            )
            for item in items
        ]
        for completed, future in enumerate(as_completed(futures), 1):
            results.append(future.result())
            if progress:
                progress(completed, len(items))

    decision_order = {"Selected": 0, "Rejected": 1, "Error": 2}
    return sorted(
        results,
        key=lambda item: (
            decision_order.get(item.get("decision", "Error"), 3),
            -float(item.get("score", 0.0)),
            str(item.get("filename", "")).lower(),
        ),
    )


def selected_csv(results: list[dict[str, Any]]) -> bytes:
    selected = [item for item in results if item.get("decision") == "Selected"]
    return (
        pd.DataFrame(selected, columns=DISPLAY_COLUMNS)
        .to_csv(index=False)
        .encode("utf-8")
    )


def selected_zip(results: list[dict[str, Any]]) -> bytes:
    selected = [item for item in results if item.get("decision") == "Selected"]
    buffer = io.BytesIO()
    used: set[str] = set()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for index, item in enumerate(selected, 1):
            name = safe_filename(item.get("filename") or f"resume_{index}")
            stem, dot, suffix = name.rpartition(".")
            candidate = name
            counter = 2
            while candidate.lower() in used:
                candidate = (
                    f"{stem or name}_{counter}{dot}{suffix}"
                    if dot
                    else f"{name}_{counter}"
                )
                counter += 1
            used.add(candidate.lower())
            archive.writestr(candidate, item["file_bytes"])
    return buffer.getvalue()
