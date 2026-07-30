"""Application service that connects document reading, parsing, scoring and reports."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ats.ats_engine import ATSEngine
from llm.llm_engine import LLMEngine
from reports.pdf_report import generate_pdf_report
from utils.document_reader import read_document
from utils.text_cleaner import clean_text


@dataclass(slots=True)
class AnalysisService:
    """Run one complete resume-to-job analysis without depending on Streamlit."""

    llm_engine: LLMEngine
    ats_engine: ATSEngine

    @staticmethod
    def _apply_experience_override(value: str, resume_data: dict[str, Any]) -> None:
        value = value.strip()
        if not value:
            return
        try:
            years = max(0.0, float(value))
        except ValueError as error:
            raise ValueError(
                "Verified experience must be a number, such as 0, 0.5 or 2."
            ) from error
        resume_data.setdefault("experience", {}).update(
            {
                "years": years,
                "professional_years": years,
                "calculated_years": years,
                "source": "user-confirmed professional-experience value",
                "is_stated": True,
            }
        )

    def analyze_document(
        self,
        source: Any,
        pasted_text: str,
        jd_text: str,
        candidate_name: str = "",
        target_title: str = "",
        experience_override: str = "",
    ) -> dict[str, Any]:
        document = read_document(source, pasted_text=pasted_text)
        resume_data = self.llm_engine.extract_resume_data(document.text)
        cleaned_jd = clean_text(jd_text)
        jd_data = self.llm_engine.extract_job_description_data(cleaned_jd)
        self._apply_experience_override(experience_override, resume_data)

        result = self.ats_engine.analyze_resume(
            resume_text=document.text,
            jd_text=cleaned_jd,
            resume_data=resume_data,
            jd_data=jd_data,
            resume_metadata=document.metadata.model_dump(),
        )
        result["recommendations"] = self.llm_engine.generate_recommendations(result)
        result["analysis_mode"] = "Standard"
        result["candidate_name"] = (
            candidate_name or resume_data.get("candidate_name") or "Unknown candidate"
        )
        result["target_job_title"] = (
            target_title or jd_data.get("job_title") or "Unspecified role"
        )
        result["resume_text"] = document.text
        result["jd_text"] = cleaned_jd
        return result

    @staticmethod
    def build_report(analysis: dict[str, Any]) -> bytes:
        return generate_pdf_report(
            analysis,
            analysis.get("candidate_name", ""),
            analysis.get("target_job_title", ""),
        )
