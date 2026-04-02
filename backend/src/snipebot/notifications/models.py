from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class NotificationMessage:
    title: str
    body: str

    @property
    def text(self) -> str:
        return f"{self.title}\n{self.body}".strip()


@dataclass(slots=True)
class NotificationResult:
    ok: bool
    provider_message_id: str | None = None
    error: str | None = None
