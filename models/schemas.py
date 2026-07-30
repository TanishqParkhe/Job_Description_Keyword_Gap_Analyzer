"""Strict, serializable schemas for documents and analysis evidence."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class DocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="allow")

    filename: str = "pasted_text.txt"
    file_type: str = "text"
    size_bytes: int = 0
    page_count: int = 1
    pages_read: int = 1
    ocr_pages: list[int] = Field(default_factory=list)
    extraction_quality_score: float = 100.0
    extraction_quality: Literal["High", "Medium", "Low"] = "High"
    warnings: list[str] = Field(default_factory=list)
    layout_flags: list[str] = Field(default_factory=list)
    language_hint: str = "unknown"

    @field_validator("extraction_quality_score")
    @classmethod
    def clamp_quality(cls, value: float) -> float:
        return round(max(0.0, min(100.0, float(value))), 2)


class DocumentResult(BaseModel):
    text: str
    metadata: DocumentMetadata
    page_texts: list[str] = Field(default_factory=list)


class RequirementEvidence(BaseModel):
    requirement: str
    priority: Literal["mandatory", "preferred", "general"] = "general"
    status: Literal["Strong", "Partial", "Missing"] = "Missing"
    match_method: str = "none"
    matched_resume_skill: str = ""
    evidence: list[str] = Field(default_factory=list)
    evidence_strength: int = 0
    score: float = 0.0

    @field_validator("score")
    @classmethod
    def clamp_score(cls, value: float) -> float:
        return round(max(0.0, min(100.0, float(value))), 2)


class AnalysisInput(BaseModel):
    resume_text: str
    job_description: str
    resume_metadata: dict[str, Any] = Field(default_factory=dict)
    options: dict[str, Any] = Field(default_factory=dict)

    @field_validator("resume_text", "job_description")
    @classmethod
    def require_content(cls, value: str) -> str:
        cleaned = str(value or "").strip()
        if not cleaned:
            raise ValueError("Text cannot be empty.")
        return cleaned
