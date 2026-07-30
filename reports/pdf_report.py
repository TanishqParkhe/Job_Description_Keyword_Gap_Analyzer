"""Compact, readable, evidence-backed PDF report."""
from __future__ import annotations

import os
import re
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from fpdf import FPDF

from config import REPORT_TITLE
from reports.charts import (
    create_claim_chart_png,
    create_coverage_chart_png,
    create_readiness_chart_png,
    create_score_chart_png,
    create_summary_scores_png,
)


def _font_candidates() -> list[tuple[str, str]]:
    return [
        ("/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
        ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\arialbd.ttf"),
        (r"C:\Windows\Fonts\calibri.ttf", r"C:\Windows\Fonts\calibrib.ttf"),
    ]


class ResumeReportPDF(FPDF):
    def __init__(self) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.alias_nb_pages()
        self.set_auto_page_break(auto=True, margin=16)
        self.unicode_font = False
        self.font_name = "Helvetica"
        for regular, bold in _font_candidates():
            if os.path.exists(regular):
                self.add_font("ReportFont", "", regular)
                if os.path.exists(bold):
                    self.add_font("ReportFont", "B", bold)
                self.font_name = "ReportFont"
                self.unicode_font = True
                break
        if self.unicode_font:
            fallbacks = [
                ("FallbackDevanagari", "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"),
                ("FallbackBengali", "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf"),
                ("FallbackKannada", "/usr/share/fonts/truetype/noto/NotoSansKannada-Regular.ttf"),
                ("FallbackTamil", "/usr/share/fonts/truetype/noto/NotoSansTamil-Regular.ttf"),
                ("FallbackTelugu", "/usr/share/fonts/truetype/noto/NotoSansTelugu-Regular.ttf"),
                ("FallbackWindowsIndic", r"C:\Windows\Fonts\Nirmala.ttf"),
            ]
            names = []
            for name, path in fallbacks:
                if os.path.exists(path):
                    self.add_font(name, "", path)
                    names.append(name)
            if names:
                self.set_fallback_fonts(names, exact_match=False)

    def safe(self, value: object) -> str:
        text = str(value or "")
        text = re.sub(r"\S{70,}", lambda match: " ".join(match.group(0)[i:i + 55] for i in range(0, len(match.group(0)), 55)), text)
        if self.unicode_font:
            return text
        replacements = {"•": "-", "–": "-", "—": "-", "₹": "INR ", "✓": "OK", "⚠": "!", "×": "x"}
        for old, new in replacements.items():
            text = text.replace(old, new)
        return text.encode("latin-1", "replace").decode("latin-1")

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font(self.font_name, "B", 9)
        self.set_text_color(55, 65, 81)
        self.cell(0, 6, self.safe(REPORT_TITLE), align="L")
        self.ln(8)
        self.set_draw_color(220, 224, 230)
        self.line(12, 15, 198, 15)

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(self.font_name, "", 8)
        self.set_text_color(90, 98, 110)
        self.cell(0, 6, self.safe(f"Page {self.page_no()}/{{nb}}  •  Decision-support report; not an employer's private ATS"), align="C")

    def title_block(self, title: str, subtitle: str = "") -> None:
        self.set_font(self.font_name, "B", 17)
        self.set_text_color(24, 55, 94)
        self.set_x(self.l_margin)
        self.multi_cell(0, 9, self.safe(title), new_x="LMARGIN", new_y="NEXT")
        if subtitle:
            self.set_font(self.font_name, "", 9)
            self.set_text_color(90, 98, 110)
            self.set_x(self.l_margin)
            self.multi_cell(0, 5, self.safe(subtitle), new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def section(self, title: str) -> None:
        if self.get_y() > 267:
            self.add_page()
        self.set_fill_color(236, 242, 250)
        self.set_text_color(24, 55, 94)
        self.set_font(self.font_name, "B", 11)
        self.cell(0, 8, self.safe(title), fill=True)
        self.ln(9)

    def paragraph(self, text: object, size: float = 9, bold: bool = False, spacing: float = 4.8) -> None:
        self.set_text_color(32, 38, 48)
        self.set_font(self.font_name, "B" if bold else "", size)
        self.set_x(self.l_margin)
        self.multi_cell(0, spacing, self.safe(text), new_x="LMARGIN", new_y="NEXT")
        self.ln(1)

    def bullet(self, text: object, size: float = 8.8) -> None:
        self.set_font(self.font_name, "", size)
        self.set_text_color(32, 38, 48)
        self.set_x(self.l_margin)
        self.multi_cell(0, 4.7, self.safe("• " + str(text)), new_x="LMARGIN", new_y="NEXT")
        self.ln(0.3)


def _temp_image(data: bytes) -> Path:
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
    handle.write(data)
    handle.close()
    return Path(handle.name)


def _add_image(pdf: ResumeReportPDF, data: bytes, x: float, y: float | None = None, w: float = 170) -> None:
    path = _temp_image(data)
    try:
        pdf.image(str(path), x=x, y=y, w=w)
    finally:
        path.unlink(missing_ok=True)


def _status_color(status: str) -> tuple[int, int, int]:
    return {
        "Strong": (22, 163, 74),
        "Partial": (217, 119, 6),
        "Missing": (220, 38, 38),
        "Safe": (22, 163, 74),
        "Review": (217, 119, 6),
        "Problem": (220, 38, 38),
    }.get(status, (75, 85, 99))


def _score_card(pdf: ResumeReportPDF, x: float, y: float, w: float, label: str, value: float, note: str, color: tuple[int, int, int]) -> None:
    pdf.set_fill_color(248, 250, 252)
    pdf.set_draw_color(215, 222, 230)
    pdf.rect(x, y, w, 30, style="DF")
    pdf.set_xy(x + 3, y + 3)
    pdf.set_font(pdf.font_name, "B", 8)
    pdf.set_text_color(75, 85, 99)
    pdf.cell(w - 6, 5, pdf.safe(label), align="C")
    pdf.set_xy(x + 3, y + 9)
    pdf.set_font(pdf.font_name, "B", 20)
    pdf.set_text_color(*color)
    pdf.cell(w - 6, 10, pdf.safe(f"{value:.1f}"), align="C")
    pdf.set_xy(x + 3, y + 21)
    pdf.set_font(pdf.font_name, "", 7.5)
    pdf.set_text_color(75, 85, 99)
    pdf.cell(w - 6, 5, pdf.safe(note), align="C")


def _requirement_table(pdf: ResumeReportPDF, rows: Iterable[dict[str, Any]]) -> None:
    for row in rows:
        evidence = "; ".join(row.get("evidence", [])[:2]) or "No reliable resume evidence found."
        requirement = str(row.get("requirement", ""))
        priority = str(row.get("priority", "general")).title()
        status = str(row.get("status", "Missing"))
        match_method = str(row.get("match_method", "none"))
        estimated_lines = max(1, len(pdf.safe(evidence)) // 100 + 1)
        height = 18 + min(4, estimated_lines) * 4.2
        if pdf.get_y() + height > 273:
            pdf.add_page()
            pdf.title_block("2. Requirement evidence - continued")
        x, y = pdf.l_margin, pdf.get_y()
        width = pdf.w - pdf.l_margin - pdf.r_margin
        pdf.set_fill_color(248, 250, 252)
        pdf.set_draw_color(215, 222, 230)
        pdf.rect(x, y, width, height, style="DF")
        pdf.set_xy(x + 3, y + 3)
        pdf.set_font(pdf.font_name, "B", 9)
        pdf.set_text_color(24, 55, 94)
        pdf.cell(96, 5, pdf.safe(requirement))
        pdf.set_font(pdf.font_name, "", 8)
        pdf.set_text_color(75, 85, 99)
        pdf.cell(38, 5, pdf.safe(priority))
        pdf.set_font(pdf.font_name, "B", 8)
        pdf.set_text_color(*_status_color(status))
        pdf.cell(0, 5, pdf.safe(status), align="R")
        pdf.set_xy(x + 3, y + 9)
        pdf.set_font(pdf.font_name, "", 7.6)
        pdf.set_text_color(90, 98, 110)
        pdf.cell(0, 4, pdf.safe(f"Matching method: {match_method}"))
        pdf.set_xy(x + 3, y + 14)
        pdf.set_font(pdf.font_name, "", 8)
        pdf.set_text_color(32, 38, 48)
        pdf.multi_cell(width - 6, 4.2, pdf.safe("Evidence: " + evidence), new_x="LMARGIN", new_y="NEXT")
        pdf.set_y(y + height + 2.5)


def _quality_cards(pdf: ResumeReportPDF, checks: list[dict[str, Any]]) -> None:
    for check in checks:
        status = str(check.get("status", ""))
        details = str(check.get("details", ""))
        recommendation = str(check.get("recommendation", ""))
        height = 15 + min(3, max(1, len(details) // 110 + 1)) * 4.2 + (5 if recommendation else 0)
        if pdf.get_y() + height > 273:
            pdf.add_page()
            pdf.title_block("4. Resume Readiness - continued")
        x, y = pdf.l_margin, pdf.get_y()
        width = pdf.w - pdf.l_margin - pdf.r_margin
        pdf.set_fill_color(249, 250, 251)
        pdf.set_draw_color(222, 226, 232)
        pdf.rect(x, y, width, height, style="DF")
        pdf.set_xy(x + 3, y + 3)
        pdf.set_font(pdf.font_name, "B", 8.5)
        pdf.set_text_color(*_status_color(status))
        pdf.cell(25, 5, pdf.safe(status))
        pdf.set_text_color(24, 55, 94)
        pdf.cell(0, 5, pdf.safe(check.get("name", "")))
        pdf.set_xy(x + 3, y + 9)
        pdf.set_font(pdf.font_name, "", 7.8)
        pdf.set_text_color(32, 38, 48)
        pdf.multi_cell(width - 6, 4.1, pdf.safe(details), new_x="LMARGIN", new_y="NEXT")
        if recommendation:
            pdf.set_font(pdf.font_name, "", 7.5)
            pdf.set_text_color(75, 85, 99)
            pdf.set_x(x + 3)
            pdf.multi_cell(width - 6, 4, pdf.safe("Recommended: " + recommendation), new_x="LMARGIN", new_y="NEXT")
        pdf.set_y(y + height + 2)


def generate_pdf_report(analysis: dict[str, Any], candidate_name: str = "", job_title: str = "") -> bytes:
    pdf = ResumeReportPDF()
    generated = datetime.now().strftime("%d %B %Y, %I:%M %p")
    candidate = candidate_name or analysis.get("resume_data", {}).get("candidate_name") or "Unknown candidate"
    role = job_title or analysis.get("jd_data", {}).get("job_title") or "Unspecified role"
    job_match = float(analysis.get("job_match_score", analysis.get("ats_score", 0)) or 0)
    readiness = float(analysis.get("resume_readiness_score", 0) or 0)
    confidence = float(analysis.get("analysis_confidence", 0) or 0)
    strong = analysis.get("matched_skills", [])
    partial = analysis.get("partial_skills", [])
    missing = analysis.get("missing_skills", [])

    # Page 1: executive summary
    pdf.add_page()
    pdf.set_fill_color(24, 55, 94)
    pdf.rect(0, 0, 210, 43, style="F")
    pdf.set_xy(14, 10)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(pdf.font_name, "B", 18)
    pdf.multi_cell(182, 8, pdf.safe(REPORT_TITLE))
    pdf.set_font(pdf.font_name, "", 8.5)
    pdf.set_x(14)
    pdf.cell(0, 5, pdf.safe(f"Generated {generated}"))
    pdf.set_xy(14, 49)
    pdf.set_text_color(32, 38, 48)
    pdf.set_font(pdf.font_name, "B", 12)
    pdf.cell(0, 7, pdf.safe(candidate))
    pdf.ln(7)
    pdf.set_font(pdf.font_name, "", 9.5)
    pdf.cell(0, 6, pdf.safe(f"Target role: {role}"))

    _score_card(pdf, 14, 66, 57, "JOB MATCH", job_match, "Used for HR cutoff", (37, 99, 235))
    _score_card(pdf, 76.5, 66, 57, "RESUME READINESS", readiness, "Formatting + writing", (139, 92, 246))
    _score_card(pdf, 139, 66, 57, "ANALYSIS CONFIDENCE", confidence, "Reliability of extraction", (14, 165, 233))
    pdf.set_y(101)
    _add_image(pdf, create_coverage_chart_png(analysis), x=18, w=174)
    pdf.set_y(151)
    pdf.section("What this result means")
    total = len(strong) + len(partial) + len(missing)
    pdf.paragraph(
        f"The JD produced {total} usable requirements. The resume strongly demonstrates {len(strong)}, "
        f"mentions {len(partial)} with weaker evidence, and does not show {len(missing)}. "
        f"Job Match measures suitability for this role. Resume Readiness measures presentation quality and does not increase Job Match."
    )
    pdf.paragraph(analysis.get("rating", ""), bold=True, size=10)
    if strong:
        pdf.paragraph("Strongest evidence", bold=True)
        for item in strong[:4]:
            pdf.bullet(item)
    if missing:
        pdf.paragraph("Highest-priority gaps", bold=True)
        for item in missing[:5]:
            pdf.bullet(item)

    # Page 2: score calculation
    pdf.add_page()
    pdf.title_block("1. How the Job Match score was calculated", "Only factors requested by this JD can contribute. Resume formatting is reported separately.")
    _add_image(pdf, create_score_chart_png(analysis), x=18, w=174)
    pdf.ln(2)
    breakdown = analysis.get("score_breakdown", {})
    pdf.section("Applicable factors and weighted points")
    labels = {
        "skill_score": "JD requirement coverage",
        "keyword_score": "Overall context relevance",
        "experience_score": "Professional-experience requirement",
        "project_score": "Project/portfolio requirement",
        "education_score": "Education requirement",
    }
    for key, contribution in breakdown.get("job_match_contributions", {}).items():
        used = bool(breakdown.get("applicability", {}).get(key, True))
        raw = float(breakdown.get("validated_scores", {}).get(key, 0))
        weight = float(breakdown.get("job_match_weights", {}).get(key, 0)) * 100
        if used:
            pdf.bullet(f"{labels.get(key, key)}: {raw:.1f}/100 × {weight:.1f}% = {float(contribution):.2f} Job Match points")
        else:
            pdf.bullet(f"{labels.get(key, key)}: Not evaluated because the JD did not request it")
    pdf.section("Why there are three different scores")
    pdf.bullet("Job Match: how closely the resume satisfies this JD; this is the score used for HR screening.")
    pdf.bullet("Resume Readiness: ATS readability and writing quality; it cannot hide missing role requirements.")
    pdf.bullet("Analysis Confidence: how reliable the extraction and interpretation appear to be.")

    # Page 3+: requirements
    pdf.add_page()
    pdf.title_block("2. Requirement evidence matrix", "Each requirement comes from this JD. Strong = demonstrated in project/work evidence; Partial = only listed or weakly shown; Missing = no reliable evidence.")
    matrix = analysis.get("requirement_matrix", [])
    _requirement_table(pdf, matrix or [{"requirement": "No reliable requirements detected", "priority": "general", "status": "Partial", "match_method": "none", "evidence": ["Use a fuller or cleaner job description."]}])

    # Eligibility and evidence page
    pdf.add_page()
    pdf.title_block("3. Eligibility, experience and evidence")
    professional = float(analysis.get("candidate_professional_experience_years", analysis.get("candidate_experience_years", 0)) or 0)
    internship = float(analysis.get("candidate_internship_years", 0) or 0)
    required = float(analysis.get("required_experience_years", 0) or 0)
    pdf.section("Experience - kept deliberately separate")
    pdf.bullet(f"Full-time/professional experience: {professional:g} years" if analysis.get("experience_was_stated") else "Full-time/professional experience: Not stated")
    pdf.bullet(f"Internship/training duration: {internship:g} years ({internship * 12:.0f} months)" if analysis.get("internship_was_stated") else "Internship/training duration: Not stated")
    pdf.bullet(f"JD minimum professional experience: {required:g} years" if analysis.get("experience_evaluated") else "JD minimum professional experience: Not specified; therefore not scored")
    pdf.bullet("Education, project and certification dates are never counted as employment experience.")
    pdf.section("Education")
    candidate_degree = analysis.get("resume_data", {}).get("education", {}).get("degree") or "Not clearly detected"
    required_degree = analysis.get("jd_data", {}).get("education", {}).get("degree") or "Not specified"
    education_result = f"{analysis.get('education_score', 0):.1f}/100" if analysis.get("score_breakdown", {}).get("applicability", {}).get("education_score") else "Not evaluated"
    pdf.bullet(f"Candidate highest detected qualification: {candidate_degree}")
    pdf.bullet(f"JD education requirement: {required_degree}")
    pdf.bullet(f"Education result: {education_result}")
    pdf.section("Projects - grouped as complete project records")
    projects = analysis.get("resume_data", {}).get("projects", [])
    if projects:
        for project in projects[:8]:
            title = project.get("title") or "Project"
            duration = project.get("duration") or "duration not stated"
            description = project.get("description") or "No description detected"
            pdf.paragraph(f"{title} ({duration})", bold=True, size=8.8)
            pdf.paragraph(description, size=8.2, spacing=4.3)
    else:
        pdf.paragraph("No clearly separated projects were detected.")
    claim_strength = analysis.get("claim_strength", {})
    if sum(float(claim_strength.get(key, 0) or 0) for key in ("professional", "project", "listed_only")):
        _add_image(pdf, create_claim_chart_png(analysis), x=35, w=140)
    else:
        pdf.paragraph("Evidence-strength chart is not applicable because no requirement from this JD matched the resume.", size=8.2)

    # Readiness and action plan
    pdf.add_page()
    pdf.title_block("4. Resume Readiness and practical improvements", "These checks improve presentation, but they do not replace missing role skills.")
    _add_image(pdf, create_readiness_chart_png(analysis), x=27, w=155)
    pdf.set_y(87)
    pdf.section("Readiness checks")
    _quality_cards(pdf, analysis.get("quality_checks", []))
    pdf.section("Prioritized action plan - what to improve first")
    for index, item in enumerate(analysis.get("action_plan", [])[:10], 1):
        pdf.paragraph(f"{index}. [{item.get('priority', 'Medium')}] {item.get('area', 'Improvement')}", bold=True, size=8.6)
        pdf.paragraph(item.get("action", ""), size=8.2, spacing=4.2)

    # Transparency
    pdf.add_page()
    pdf.title_block("5. Extraction, privacy and limitations")
    metadata = analysis.get("resume_metadata", {})
    pdf.section("Extraction diagnostics")
    for label, value in (
        ("File type", metadata.get("file_type", "unknown")),
        ("Pages read", f"{metadata.get('pages_read', 1)} of {metadata.get('page_count', 1)}"),
        ("OCR pages", metadata.get("ocr_pages", []) or "None"),
        ("Extraction quality", f"{metadata.get('extraction_quality', 'Unknown')} ({metadata.get('extraction_quality_score', 0):.0f}%)"),
        ("Layout flags", ", ".join(metadata.get("layout_flags", [])) or "None"),
    ):
        pdf.bullet(f"{label}: {value}")
    pdf.section("Security and privacy")
    security = analysis.get("security", {})
    pdf.paragraph(
        "Resume content risk: " + str(security.get("resume", {}).get("risk", "unknown")) +
        ". Job-description content risk: " + str(security.get("job_description", {}).get("risk", "unknown")) +
        ". Uploaded text is treated as untrusted data and is never followed as an instruction."
    )
    pdf.section("Important limitations")
    for item in analysis.get("limitations", []):
        pdf.bullet(item)
    pdf.paragraph("Never add a skill, metric, employer, qualification or achievement unless it is true and can be defended in an interview.", bold=True)

    return bytes(pdf.output())
