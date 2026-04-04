"""Контракт решения triage-агента."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TriageDecisionType = Literal["spam", "reply", "ignore"]


@dataclass(frozen=True)
class TriageDecision:
    """Решение, что делать с сообщением группы."""

    action: TriageDecisionType
    reason: str = ""
