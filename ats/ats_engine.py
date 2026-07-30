"""Explainable, fast resume–job compatibility engine."""
from __future__ import annotations
from typing import Any, Iterable
import re

from ats.scoring import calculate_education_certification_score, calculate_experience_score, calculate_project_score, calculate_score_breakdown
from ats.similarity import build_requirement_matrix, calculate_keyword_similarity
from llm.parser import normalize_structure
from quality.resume_quality import analyze_resume_quality
from utils.security import detect_prompt_injection


class ATSEngine:
    @staticmethod
    def _rating(score: float) -> str:
        if score >= 80: return "Strong job match"
        if score >= 65: return "Good job match"
        if score >= 45: return "Partial job match"
        return "Low job match — major requirements are missing"

    @staticmethod
    def _confidence(metadata: dict[str, Any], jd_data: dict[str, Any], matrix: list[dict[str, Any]], sources: Iterable[str], security_findings: int) -> float:
        document_quality = float(metadata.get("extraction_quality_score", 82) or 0)
        requirement_completeness = min(100.0, 40.0 + len(matrix) * 5.0) if matrix else 30.0
        jd_structure = 96.0 if jd_data.get("job_title") and matrix else 70.0
        parser_quality = 94.0 if any("Ollama" in str(source) for source in sources) else 88.0
        score = document_quality * .43 + requirement_completeness * .25 + jd_structure * .17 + parser_quality * .15 - security_findings * 7
        return round(max(20.0, min(98.0, score)), 2)

    @staticmethod
    def _action_plan(matrix: list[dict[str, Any]], checks: list[dict[str, Any]], breakdown: dict[str, Any]) -> list[dict[str, Any]]:
        actions: list[dict[str, Any]] = []
        missing_mandatory = [r["requirement"] for r in matrix if r["priority"] == "mandatory" and r["status"] == "Missing"]
        partial = [r["requirement"] for r in matrix if r["status"] == "Partial"]
        missing_preferred = [r["requirement"] for r in matrix if r["priority"] == "preferred" and r["status"] == "Missing"]
        if missing_mandatory:
            actions.append({"priority":"Critical","impact":"High","effort":"Varies","area":"Mandatory requirements","action":"Do not add these unless true. Build real evidence for: " + ", ".join(missing_mandatory[:8]) + ".","estimated_points":min(20.0, len(missing_mandatory)*2.5)})
        if partial:
            actions.append({"priority":"High","impact":"High","effort":"Low–Medium","area":"Evidence strength","action":"Show where and how you used: " + ", ".join(partial[:8]) + ".","estimated_points":min(14.0, len(partial)*1.8)})
        if missing_preferred:
            actions.append({"priority":"Medium","impact":"Medium","effort":"Varies","area":"Preferred requirements","action":"Preferred gaps are not always disqualifying. Consider truthful evidence for: " + ", ".join(missing_preferred[:8]) + ".","estimated_points":min(8.0, len(missing_preferred)*1.2)})
        for item in checks:
            if item.get("status") in {"Review", "Problem"} and item.get("recommendation"):
                actions.append({"priority":"High" if item.get("severity") == "high" else "Medium","impact":"High" if item.get("severity") == "high" else "Medium","effort":"Low–Medium","area":item.get("name", "Resume quality"),"action":item["recommendation"],"estimated_points":3.0 if item.get("severity") == "high" else 1.5})
        rank = {"Critical":0,"High":1,"Medium":2,"Low":3}
        unique, seen = [], set()
        for item in sorted(actions, key=lambda x:(rank.get(x["priority"],9),-float(x.get("estimated_points",0)))):
            key = item["action"].lower()
            if key not in seen:
                seen.add(key); unique.append(item)
        return unique[:12]

    @staticmethod
    def _interview_questions(matrix: list[dict[str, Any]], resume_data: dict[str, Any]) -> list[str]:
        result = []
        for row in matrix:
            if row["status"] == "Strong":
                result.append(f"Explain exactly where you used {row['requirement']}, your contribution and the outcome.")
            elif row["status"] == "Partial":
                result.append(f"What truthful hands-on example can you give for {row['requirement']}?")
        return result[:12]

    def analyze_resume(self, resume_skills: object=None, jd_skills: object=None, resume_text: object="", jd_text: object="", resume_data: dict[str, Any]|None=None, jd_data: dict[str, Any]|None=None, resume_metadata: dict[str, Any]|None=None) -> dict[str, Any]:
        resume_text_value, jd_text_value = str(resume_text or "").strip(), str(jd_text or "").strip()
        if not resume_text_value: raise ValueError("Resume text is empty.")
        if not jd_text_value: raise ValueError("Job description is empty.")
        structured_resume = normalize_structure(resume_data, "resume")
        structured_jd = normalize_structure(jd_data, "jd")
        if jd_skills and not any(structured_jd.get(k) for k in ("mandatory_skills","preferred_skills","general_skills")):
            structured_jd["general_skills"] = list(jd_skills)
        mandatory = structured_jd.get("mandatory_skills", [])
        preferred = structured_jd.get("preferred_skills", [])
        general = structured_jd.get("general_skills", [])
        matrix, skill_score = build_requirement_matrix(resume_text_value, structured_resume, mandatory, preferred, general)
        context_score = calculate_keyword_similarity(resume_text_value, structured_jd.get("comparison_text") or jd_text_value)
        matched = [r["requirement"] for r in matrix if r["status"] == "Strong"]
        partial = [r["requirement"] for r in matrix if r["status"] == "Partial"]
        missing = [r["requirement"] for r in matrix if r["status"] == "Missing"]
        structured_resume["all_skills"] = matched + partial
        candidate_exp = structured_resume.get("experience", {})
        jd_exp = structured_jd.get("experience", {})
        candidate_years = float(candidate_exp.get("professional_years", candidate_exp.get("years", 0)) or 0)
        internship_years = float(candidate_exp.get("internship_years", 0) or 0)
        required_years = float(jd_exp.get("years", 0) or 0)
        experience_applicable = required_years > 0
        experience_score = calculate_experience_score(candidate_years, required_years)
        all_required = [r["requirement"] for r in matrix]
        project_applicable = bool(re.search(r"(?i)\b(projects?|portfolio|case study|github)\b", jd_text_value))
        project_score = calculate_project_score(structured_resume.get("projects", []), all_required) if project_applicable else 0.0
        required_degree = bool(structured_jd.get("education", {}).get("degree"))
        education_score = calculate_education_certification_score(structured_resume.get("education", {}), structured_jd.get("education", {}), structured_resume.get("certifications", []), structured_jd.get("certifications", []))
        quality = analyze_resume_quality(resume_text_value, structured_resume, resume_metadata or {}, structured_jd)
        applicability = {
            "skill_score": bool(matrix),
            "keyword_score": True,
            "experience_score": experience_applicable,
            "project_score": project_applicable,
            "education_score": required_degree,
            "ats_format_score": True,
            "content_quality_score": True,
        }
        breakdown = calculate_score_breakdown(skill_score, context_score, experience_score, project_score, education_score, quality["ats_format_score"], quality["content_quality_score"], applicability=applicability)
        final_score = float(breakdown["job_match_score"])
        readiness_score = float(breakdown["resume_readiness_score"])
        resume_security, jd_security = detect_prompt_injection(resume_text_value), detect_prompt_injection(jd_text_value)
        security_findings = len(resume_security["findings"]) + len(jd_security["findings"])
        confidence = self._confidence(resume_metadata or {}, structured_jd, matrix, (structured_resume.get("analysis_source", ""), structured_jd.get("analysis_source", "")), security_findings)
        claim_strength = {"professional": sum(1 for r in matrix if int(r.get("evidence_strength",0)) >= 4), "project": sum(1 for r in matrix if int(r.get("evidence_strength",0)) == 3), "listed_only": sum(1 for r in matrix if 1 <= int(r.get("evidence_strength",0)) <= 2)}
        action_plan = self._action_plan(matrix, quality["checks"], breakdown)
        mandatory_missing = [r["requirement"] for r in matrix if r["priority"] == "mandatory" and r["status"] == "Missing"]
        return {
            "ats_score": final_score, "job_match_score": final_score, "compatibility_score": final_score, "resume_readiness_score": readiness_score, "analysis_confidence": confidence, "rating": self._rating(final_score),
            "skill_score": skill_score, "keyword_score": context_score, "context_score": context_score,
            "experience_score": experience_score, "project_score": project_score, "education_score": education_score,
            "ats_format_score": quality["ats_format_score"], "content_quality_score": quality["content_quality_score"], "score_breakdown": breakdown,
            "requirement_matrix": matrix, "matched_skills": matched, "partial_skills": partial, "missing_skills": missing, "mandatory_missing": mandatory_missing,
            "resume_skills": matched + partial, "required_skills": all_required,
            "candidate_experience_years": candidate_years, "candidate_professional_experience_years": candidate_years, "candidate_internship_years": internship_years, "required_experience_years": required_years,
            "candidate_experience_source": candidate_exp.get("source", "not stated"), "candidate_internship_source": candidate_exp.get("internship_source", "not stated"), "experience_was_stated": bool(candidate_exp.get("is_stated")), "internship_was_stated": bool(candidate_exp.get("internship_is_stated")), "experience_evaluated": experience_applicable,
            "quality_checks": quality["checks"], "claim_strength": claim_strength, "possible_inconsistencies": structured_resume.get("possible_inconsistencies", []),
            "action_plan": action_plan, "improvement_simulator": action_plan[:8], "interview_questions": self._interview_questions(matrix, structured_resume),
            "security": {"resume":resume_security,"job_description":jd_security}, "resume_metadata": resume_metadata or {}, "resume_data": structured_resume, "jd_data": structured_jd,
            "analysis_mode": "Standard",
            "limitations": ["This is an explainable compatibility estimate, not an employer's private ATS score.", "Only requirements discovered from the current JD are used for skill scoring.", "Professional experience and internship duration are shown separately; education and project dates are ignored.", "Recommendations must never be used to add untrue skills, results or experience."],
        }

    def compare_jobs(self, resume_text: str, resume_data: dict[str, Any], jobs: list[dict[str, Any]], resume_metadata: dict[str, Any]|None=None) -> list[dict[str, Any]]:
        results=[]
        for index, job in enumerate(jobs,1):
            if not str(job.get("text","")).strip(): continue
            analysis=self.analyze_resume(resume_text=resume_text,jd_text=job["text"],resume_data=resume_data,jd_data=job.get("data") or {},resume_metadata=resume_metadata)
            results.append({"role":job.get("title") or analysis["jd_data"].get("job_title") or f"Role {index}","score":analysis["ats_score"],"confidence":analysis["analysis_confidence"],"matched":len(analysis["matched_skills"]),"missing":len(analysis["missing_skills"]),"analysis":analysis})
        return sorted(results,key=lambda x:x["score"],reverse=True)
