"""Focused tests for the final Team Edition workflow."""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from ats.ats_engine import ATSEngine
from database.db import DatabaseManager
from hr.bulk_screening import screen_resumes, selected_zip
from llm.llm_engine import LLMEngine
from reports.pdf_report import generate_pdf_report
from services.analysis_service import AnalysisService
from utils.zip_resume_reader import extract_resume_zip


class Upload:
    def __init__(self, name: str, data: bytes):
        self.name = name
        self._data = data

    def getvalue(self) -> bytes:
        return self._data

    def read(self) -> bytes:
        return self._data

    def seek(self, _position: int) -> int:
        return 0


def sample_resume() -> str:
    return """VED PRAKASH SINGH
SUMMARY
Data graduate with hands-on Python and SQL project work.
SKILLS
Python, SQL, Pandas
EDUCATION
B.Tech | Jan 2021 - Jul 2024
PROJECTS
Sales Dashboard | Jan 2024 - May 2024
Developed a Python and SQL dashboard for sales reporting.
INTERNSHIP
Railway Intern | Jun 2023 - Aug 2023
Assisted with network monitoring and maintenance.
"""


def sample_jd() -> str:
    return """Role: Data Analyst
Mandatory skills: Python, SQL
Preferred skills: Power BI
Build dashboards and analyze business data.
Education: B.Tech or any graduate.
"""


def test_dynamic_extraction_and_experience_separation() -> None:
    engine = LLMEngine()
    resume = engine.extract_resume_data(sample_resume())
    jd = engine.extract_job_description_data(sample_jd())
    assert resume["experience"]["professional_years"] == 0
    assert 0.2 <= resume["experience"]["internship_years"] <= 0.3
    requirements = jd["mandatory_skills"] + jd["preferred_skills"] + jd["general_skills"]
    assert any("python" in item.lower() for item in requirements)
    assert any("sql" in item.lower() for item in requirements)


def test_end_to_end_analysis_and_pdf() -> None:
    llm = LLMEngine()
    service = AnalysisService(llm_engine=llm, ats_engine=ATSEngine())
    analysis = service.analyze_document(
        None,
        sample_resume(),
        sample_jd(),
        candidate_name="Ved Prakash Singh",
        target_title="Data Analyst",
    )
    assert 0 <= analysis["job_match_score"] <= 100
    assert analysis["experience_was_stated"] is False
    assert analysis["internship_was_stated"] is True
    pdf = generate_pdf_report(analysis, "Ved Prakash Singh", "Data Analyst")
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 10_000


def test_hr_zip_screening() -> None:
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("candidates/good.txt", sample_resume())
        archive.writestr("candidates/other.txt", "NAME\nSKILLS\nJava and Spring\n")
        archive.writestr("notes/readme.md", "ignored")
    upload = Upload("resumes.zip", archive_buffer.getvalue())
    resumes, warnings = extract_resume_zip(upload)
    assert len(resumes) == 2
    assert any("unsupported" in item.lower() for item in warnings)
    results = screen_resumes(resumes, sample_jd(), threshold=30)
    assert len(results) == 2
    assert results[0]["score"] >= results[1]["score"]
    shortlisted = selected_zip(results)
    assert shortlisted.startswith(b"PK")


def test_local_history_database(tmp_path: Path) -> None:
    database = DatabaseManager(tmp_path / "history.db")
    row_id = database.save_analysis(
        {
            "candidate_name": "Candidate",
            "job_title": "Data Analyst",
            "ats_score": 72.5,
            "rating": "Good job match",
            "matched_skills": ["Python"],
            "missing_skills": ["Power BI"],
            "analysis": {"job_match_score": 72.5},
        }
    )
    assert row_id is not None
    assert len(database.list_analyses()) == 1
    assert database.delete_all() is True
    assert database.list_analyses() == []
