"""Public parsing facade and optional Ollama-powered resume coach."""
from __future__ import annotations

import json
import re
from typing import Any

from config import (
    DEEP_OLLAMA_MODEL,
    FAST_OLLAMA_MODEL,
    LLM_TIMEOUT_SECONDS,
    MASK_PII_BEFORE_LLM,
    OLLAMA_HOST,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    OLLAMA_NUM_CTX,
    OLLAMA_NUM_PREDICT,
)
from llm.local_extractor import _merge_nonempty, _offline_jd, _offline_resume
from llm.parser import normalize_structure, parse_llm_response
from llm.prompts import (
    CHATBOT_PROMPT,
    JD_SKILL_EXTRACTION_PROMPT,
    RECOMMENDATION_PROMPT,
    RESUME_SKILL_EXTRACTION_PROMPT,
)
from utils.security import redact_pii, wrap_untrusted_content
from utils.text_cleaner import clean_text, normalize_for_matching

try:
    import ollama  # type: ignore
except ImportError:  # AI is optional; fast local analysis still works.
    ollama = None

class LLMEngine:
    """Fast local parsing plus an optional low-latency Ollama coach."""

    def __init__(
        self,
        model: str = OLLAMA_MODEL,
        host: str = OLLAMA_HOST,
        *,
        fast_model: str = FAST_OLLAMA_MODEL,
        deep_model: str = DEEP_OLLAMA_MODEL,
    ):
        self.host = host
        self.fast_model = fast_model or model
        self.deep_model = deep_model or model
        self.model = self.fast_model  # Backward-compatible public attribute.
        self.last_error = ""
        self._availability_cache: dict[str, bool] = {}
        if ollama is None:
            self._client = None
        else:
            try:
                self._client = ollama.Client(host=host, timeout=LLM_TIMEOUT_SECONDS)
            except TypeError:  # Older Python client compatibility.
                self._client = ollama.Client(host=host)

    def _installed_models(self, force: bool = False) -> list[str]:
        cache_key = "__models__"
        if not force and cache_key in self._availability_cache:
            return list(getattr(self, "_model_names", []))
        if self._client is None:
            self._availability_cache[cache_key] = False
            self._model_names = []
            return []
        try:
            models = self._client.list()
            raw = (
                models.get("models", [])
                if isinstance(models, dict)
                else getattr(models, "models", [])
            )
            names = [
                str(item.get("model") or item.get("name") or "")
                if isinstance(item, dict)
                else str(
                    getattr(item, "model", "") or getattr(item, "name", "")
                )
                for item in raw
            ]
            self._model_names = [name for name in names if name]
            self._availability_cache[cache_key] = True
            return self._model_names
        except Exception as error:
            self.last_error = str(error)
            self._model_names = []
            self._availability_cache[cache_key] = False
            return []

    def resolve_model(self, *, prefer_fast: bool = True, force: bool = False) -> str:
        """Choose the smallest configured installed model, then fall back safely."""
        names = self._installed_models(force=force)
        candidates = (
            [self.fast_model, self.deep_model, OLLAMA_MODEL]
            if prefer_fast
            else [self.deep_model, self.fast_model, OLLAMA_MODEL]
        )
        for candidate in candidates:
            if not candidate or candidate.lower() == "disabled":
                continue
            if any(name == candidate or name.startswith(candidate + ":") for name in names):
                return candidate
        return ""

    def is_available(self, force: bool = False, *, prefer_fast: bool = True) -> bool:
        return bool(self.resolve_model(prefer_fast=prefer_fast, force=force))

    @staticmethod
    def _content(response: Any) -> str:
        if isinstance(response, dict):
            return str(response.get("message", {}).get("content", ""))
        message = getattr(response, "message", None)
        return str(
            getattr(message, "content", "")
            or (message.get("content", "") if isinstance(message, dict) else "")
        )

    @staticmethod
    def _compact_analysis(analysis: dict[str, Any]) -> dict[str, Any]:
        matrix = []
        for row in analysis.get("requirement_matrix", [])[:40]:
            matrix.append(
                {
                    "requirement": row.get("requirement"),
                    "priority": row.get("priority"),
                    "status": row.get("status"),
                    "evidence": (row.get("evidence") or [])[:2],
                }
            )
        actions = []
        for item in analysis.get("action_plan", [])[:8]:
            if isinstance(item, dict):
                actions.append(
                    {
                        "priority": item.get("priority"),
                        "area": item.get("area"),
                        "action": item.get("action"),
                    }
                )
        return {
            "candidate": analysis.get("candidate_name"),
            "target_role": analysis.get("target_job_title"),
            "job_match": analysis.get("job_match_score", analysis.get("ats_score")),
            "resume_readiness": analysis.get("resume_readiness_score"),
            "confidence": analysis.get("analysis_confidence"),
            "matched": analysis.get("matched_skills", [])[:25],
            "partial": analysis.get("partial_skills", [])[:25],
            "missing": analysis.get("missing_skills", [])[:30],
            "mandatory_missing": analysis.get("mandatory_missing", [])[:20],
            "professional_experience_years": analysis.get(
                "candidate_professional_experience_years",
                analysis.get("candidate_experience_years"),
            ),
            "internship_years": analysis.get("candidate_internship_years"),
            "required_experience_years": analysis.get("required_experience_years"),
            "experience_evaluated": analysis.get("experience_evaluated"),
            "requirements": matrix,
            "action_plan": actions,
            "interview_questions": analysis.get("interview_questions", [])[:8],
        }

    def _chat_options(self, *, json_mode: bool = False) -> dict[str, Any]:
        return {
            "temperature": 0.0 if json_mode else 0.2,
            "num_ctx": OLLAMA_NUM_CTX,
            "num_predict": OLLAMA_NUM_PREDICT,
        }

    def _ask_json(self, prompt: str, text: str, schema: str) -> dict[str, Any]:
        if not self.is_available():
            return {}
        model = self.resolve_model(prefer_fast=True) or self.model
        if not model or self._client is None:
            return {}
        protected = (redact_pii(text) if MASK_PII_BEFORE_LLM else text)[:14000]
        recommendation_schema = {
            "type": "object",
            "properties": {
                "recommendations": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 8,
                }
            },
            "required": ["recommendations"],
        }
        output_format: Any = recommendation_schema if schema == "analysis" else "json"
        try:
            response = self._client.chat(
                model=model,
                format=output_format,
                keep_alive=OLLAMA_KEEP_ALIVE,
                options=self._chat_options(json_mode=True),
                messages=[
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": wrap_untrusted_content(protected, schema),
                    },
                ],
            )
            content = self._content(response)
            if schema in {"resume", "jd"}:
                return parse_llm_response(content, schema)
            cleaned = re.sub(
                r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I | re.S
            )
            try:
                value = json.loads(cleaned)
            except json.JSONDecodeError:
                object_start, object_end = cleaned.find("{"), cleaned.rfind("}")
                array_start, array_end = cleaned.find("["), cleaned.rfind("]")
                if object_start >= 0 and object_end > object_start:
                    value = json.loads(cleaned[object_start : object_end + 1])
                elif array_start >= 0 and array_end > array_start:
                    value = json.loads(cleaned[array_start : array_end + 1])
                else:
                    value = {}
            if isinstance(value, dict):
                if schema == "analysis" and "recommendations" not in value:
                    suggestions = value.get("suggestions") or value.get("actions")
                    if isinstance(suggestions, list):
                        value["recommendations"] = suggestions
                return value
            if schema == "analysis" and isinstance(value, list):
                return {"recommendations": value}
            return {}
        except Exception as error:
            # Some older Ollama builds accept only format="json".
            if schema == "analysis" and "format" in str(error).lower():
                try:
                    response = self._client.chat(
                        model=model,
                        format="json",
                        keep_alive=OLLAMA_KEEP_ALIVE,
                        options=self._chat_options(json_mode=True),
                        messages=[
                            {"role": "system", "content": prompt},
                            {
                                "role": "user",
                                "content": wrap_untrusted_content(protected, schema),
                            },
                        ],
                    )
                    value = json.loads(self._content(response))
                    if isinstance(value, list):
                        return {"recommendations": value}
                    return value if isinstance(value, dict) else {}
                except Exception as fallback_error:
                    self.last_error = str(fallback_error)
                    return {}
            self.last_error = str(error)
            return {}

    # These are deliberately fast and never call Ollama.
    def extract_resume_data(self, resume_text: object) -> dict[str, Any]:
        return _offline_resume(clean_text(resume_text))

    def extract_job_description_data(self, jd_text: object) -> dict[str, Any]:
        return _offline_jd(clean_text(jd_text))

    def enhance_resume_data(
        self, resume_text: object, base: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        base = base or self.extract_resume_data(resume_text)
        enhanced = self._ask_json(
            RESUME_SKILL_EXTRACTION_PROMPT, clean_text(resume_text), "resume"
        )
        result = (
            normalize_structure(_merge_nonempty(base, enhanced), "resume")
            if enhanced
            else base
        )
        result["analysis_source"] = (
            "local analysis with AI review"
            if enhanced
            else base.get("analysis_source", "local analysis")
        )
        # Never allow AI to invent experience: preserve verified local calculation.
        result["experience"] = base.get("experience", {})
        return result

    def enhance_job_description_data(
        self, jd_text: object, base: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        base = base or self.extract_job_description_data(jd_text)
        enhanced = self._ask_json(
            JD_SKILL_EXTRACTION_PROMPT, clean_text(jd_text), "jd"
        )
        if not enhanced:
            return base
        result = normalize_structure(_merge_nonempty(base, enhanced), "jd")
        for key in ("mandatory_skills", "preferred_skills", "general_skills"):
            seen: set[str] = set()
            merged: list[str] = []
            for item in base.get(key, []) + result.get(key, []):
                token = re.sub(r"[^a-z0-9+#]", "", str(item).lower())
                if token and token not in seen:
                    seen.add(token)
                    merged.append(str(item))
            result[key] = merged
        result["analysis_source"] = "local analysis with AI review"
        return result

    def enhance_analysis(self, analysis: dict[str, Any]) -> list[str]:
        """Generate extra advice with one short model call; never re-analyze files."""
        payload = json.dumps(
            self._compact_analysis(analysis), ensure_ascii=False, default=str
        )
        response = self._ask_json(RECOMMENDATION_PROMPT, payload, "analysis")
        return [
            str(item).strip()
            for item in response.get("recommendations", [])
            if str(item).strip()
        ][:8]

    def generate_recommendations(self, analysis: dict[str, Any]) -> list[str]:
        actions = analysis.get("action_plan", [])
        return [
            str(item.get("action", ""))
            for item in actions
            if isinstance(item, dict) and item.get("action")
        ][:12]

    def instant_chatbot_answer(
        self, question: object, analysis: dict[str, Any]
    ) -> str | None:
        """Answer common analysis questions immediately without an LLM."""
        query = normalize_for_matching(question)
        if not query:
            return "Please ask a question about the resume analysis."

        score = float(
            analysis.get("job_match_score", analysis.get("ats_score", 0.0)) or 0
        )
        matched = [str(item) for item in analysis.get("matched_skills", [])]
        partial = [str(item) for item in analysis.get("partial_skills", [])]
        missing = [str(item) for item in analysis.get("missing_skills", [])]
        actions = [
            str(item.get("action", ""))
            for item in analysis.get("action_plan", [])
            if isinstance(item, dict) and item.get("action")
        ]

        if re.search(r"\b(your name|who are you|what are you called)\b", query):
            return "I’m Bhavya AI, your resume analysis assistant."
        if re.search(r"\b(score|job match|match percentage|why.*low|why.*high)\b", query):
            return (
                f"Your Job Match is **{score:.1f}/100**. "
                f"The resume strongly shows **{len(matched)}** requirements, has partial evidence for "
                f"**{len(partial)}**, and is missing **{len(missing)}**. "
                "The requirement table shows the exact evidence used for every decision."
            )
        if re.search(r"\b(missing|gap|gaps|skills?.*need|requirements?.*missing)\b", query):
            if not missing:
                return "No job requirement is currently marked as missing. Review partial matches for evidence that could still be strengthened."
            return "The main missing requirements are: **" + ", ".join(missing[:12]) + "**. Add them only after you genuinely learn or use them."
        if re.search(r"\b(improve|improvement|change|changes|fix|better|next step|what should i do)\b", query):
            if not actions:
                return "No urgent change was identified. Review the requirement evidence and keep every claim truthful."
            return "Start with these changes:\n\n" + "\n".join(
                f"{index}. {action}" for index, action in enumerate(actions[:5], 1)
            )
        if re.search(r"\b(experience|internship|fresher|years?)\b", query):
            professional = float(
                analysis.get(
                    "candidate_professional_experience_years",
                    analysis.get("candidate_experience_years", 0),
                )
                or 0
            )
            internship = float(analysis.get("candidate_internship_years", 0) or 0)
            professional_text = (
                f"{professional:g} years"
                if analysis.get("experience_was_stated")
                else "not stated"
            )
            internship_text = (
                f"{internship * 12:.0f} months"
                if analysis.get("internship_was_stated")
                else "not stated"
            )
            return (
                f"Professional experience: **{professional_text}**. "
                f"Internship or training: **{internship_text}**. "
                "Education and project dates are not counted as employment."
            )
        if re.search(r"\b(interview|questions?|prepare)\b", query):
            questions = [
                str(item)
                for item in analysis.get("interview_questions", [])
                if str(item).strip()
            ]
            if questions:
                return "Prepare these first:\n\n" + "\n".join(
                    f"{index}. {item}" for index, item in enumerate(questions[:6], 1)
                )
            focus = (matched + partial)[:5]
            if focus:
                return "Be ready to explain where and how you used: **" + ", ".join(focus) + "**. Use a clear problem–action–result example."
        if re.search(r"\b(selected|rejected|threshold|shortlist|pass)\b", query):
            return (
                "HR selection is based on the configured Job Match threshold and, when enabled, mandatory requirements. "
                "Resume Readiness does not increase the Job Match score."
            )
        return None

    def _fallback_coach_answer(self, analysis: dict[str, Any]) -> str:
        actions = self.generate_recommendations(analysis)
        if actions:
            return "Focus first on: " + "; ".join(actions[:3])
        return "Review the requirement evidence table and strengthen only claims that are true and defensible."

    def stream_chatbot(
        self,
        question: object,
        analysis: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ):
        """Yield an instant local answer or stream a concise fast-model response."""
        query = clean_text(question)
        instant = self.instant_chatbot_answer(query, analysis)
        if instant is not None:
            yield instant
            return
        model = self.resolve_model(prefer_fast=True)
        if not model or self._client is None:
            yield self._fallback_coach_answer(analysis)
            return

        context = json.dumps(
            self._compact_analysis(analysis), ensure_ascii=False, default=str
        )[:10000]
        safe_history = []
        for item in (history or [])[-6:]:
            role = item.get("role")
            content = clean_text(item.get("content", ""))[:700]
            if role in {"user", "assistant"} and content:
                safe_history.append({"role": role, "content": content})
        messages = [
            {"role": "system", "content": CHATBOT_PROMPT},
            *safe_history,
            {
                "role": "user",
                "content": wrap_untrusted_content(context, "analysis")
                + "\nQUESTION:\n"
                + wrap_untrusted_content(query, "question")
                + "\nAnswer in under 140 words.",
            },
        ]
        try:
            stream = self._client.chat(
                model=model,
                messages=messages,
                stream=True,
                keep_alive=OLLAMA_KEEP_ALIVE,
                options=self._chat_options(json_mode=False),
            )
            produced = False
            for chunk in stream:
                content = self._content(chunk)
                if content:
                    produced = True
                    yield content
            if not produced:
                yield self._fallback_coach_answer(analysis)
        except Exception as error:
            self.last_error = str(error)
            yield self._fallback_coach_answer(analysis)

    def chatbot(
        self,
        question: object,
        analysis: dict[str, Any],
        history: list[dict[str, str]] | None = None,
    ) -> str:
        return "".join(self.stream_chatbot(question, analysis, history)).strip()
