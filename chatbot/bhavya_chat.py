"""Bhavya AI chatbot wrapper with instant and streaming replies."""
from __future__ import annotations

from typing import Any, Iterable

from chatbot.memory import ChatMemory
from llm.llm_engine import LLMEngine


class BhavyaChatbot:
    def __init__(
        self,
        llm_engine: LLMEngine | None = None,
        memory: ChatMemory | None = None,
    ):
        self.llm_engine = llm_engine or LLMEngine()
        self.memory = memory or ChatMemory()

    def ask(
        self,
        question: object,
        analysis_context: dict[str, Any] | None = None,
    ) -> str:
        text = str(question).strip()
        if not text:
            return "Please enter a question about the resume analysis."
        history = self.memory.as_messages()
        self.memory.add("user", text)
        answer = self.llm_engine.chatbot(text, analysis_context or {}, history)
        self.memory.add("assistant", answer)
        return answer

    def stream(
        self,
        question: object,
        analysis_context: dict[str, Any] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> Iterable[str]:
        text = str(question).strip()
        if not text:
            yield "Please enter a question about the resume analysis."
            return
        yield from self.llm_engine.stream_chatbot(
            text,
            analysis_context or {},
            history or self.memory.as_messages(),
        )
