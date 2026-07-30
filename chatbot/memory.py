"""Small in-memory conversation store for the resume chatbot."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ChatMemory:
    max_messages: int = 20
    messages: list[dict[str, str]] = field(default_factory=list)

    def add(self, role: str, content: object) -> None:
        role = role if role in {"user", "assistant", "system"} else "user"
        text = str(content).strip()
        if not text:
            return
        self.messages.append({"role": role, "content": text})
        self.messages = self.messages[-self.max_messages :]

    def clear(self) -> None:
        self.messages.clear()

    def as_text(self) -> str:
        return "\n".join(f"{item['role'].title()}: {item['content']}" for item in self.messages)

    def as_messages(self) -> list[dict[str, str]]:
        return list(self.messages)
