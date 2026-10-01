"""Chat router: free built-in answer -> remembered answer -> paid Claude (only when asked).

Modes
- ``auto``   free answer if one matches, else a remembered answer, else DON'T call Claude:
             return ``needs_claude`` so the UI can offer an explicit "Ask Claude" button.
- ``free``   same as auto, never offers anything paid.
- ``claude`` remembered answer if the analysis is unchanged, else call Claude (counts against
             the monthly budget) and remember the result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from agent.free_answers import FreeAnswerEngine
from agent.runner import AgentError, AnalystAgent, sanitize_messages
from services.analysis_service import AnalysisNotFoundError, AnalysisService
from services.answer_cache import AnswerCache
from services.budget_service import BudgetService, estimate_cost_usd
from services.lessons_service import LessonsService
from services.output_service import OutputService

NEEDS_CLAUDE_TEXT = (
    "I can't answer that from the stored results without AI. "
    "Choose \"Ask Claude\" for a deeper answer; it uses a little of your monthly budget."
)


@dataclass
class ChatResult:
    reply: str
    source: str  # built_in | cache | claude | none
    intent: str | None = None
    needs_claude: bool = False
    estimated_cost_usd: float | None = None
    tool_calls: list[Any] = field(default_factory=list)
    iterations: int = 0
    stop_reason: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    budget: dict[str, Any] | None = None


class AnalystService:
    def __init__(
        self,
        analysis_service: AnalysisService,
        output_service: OutputService,
        agent: AnalystAgent,
        budget: BudgetService,
        cache: AnswerCache | None = None,
        free_engine: FreeAnswerEngine | None = None,
        lessons: LessonsService | None = None,
    ) -> None:
        self.analysis_service = analysis_service
        self.output_service = output_service
        self.agent = agent
        self.budget = budget
        self.cache = cache or AnswerCache()
        self.lessons = lessons
        self.free = free_engine or FreeAnswerEngine(analysis_service, output_service)

    def answer(self, analysis_id: str, raw_messages: list[dict[str, Any]], mode: str = "auto") -> ChatResult:
        if mode not in {"auto", "free", "claude"}:
            raise AgentError("mode must be auto, free or claude.", status_code=400)
        try:
            self.analysis_service.get(analysis_id)
        except AnalysisNotFoundError as exc:
            raise AgentError(str(exc), status_code=404) from exc
        messages = sanitize_messages(raw_messages)
        question = messages[-1]["content"]
        single_turn = len(messages) == 1

        # 1) Free, built-in answer.
        if mode in {"auto", "free"}:
            free = self.free.answer(analysis_id, question)
            if free is not None:
                return ChatResult(reply=free.reply, source="built_in", intent=free.intent, estimated_cost_usd=0.0)

        # 2) Remembered answer (only valid while the analysis is unchanged).
        analysis_type = self.analysis_service.get(analysis_id).analysis_type
        lessons_version = self.lessons.version(analysis_type) if self.lessons else ""
        fingerprint = AnswerCache.fingerprint(self.analysis_service, self.output_service, analysis_id, lessons_version)
        if single_turn:
            hit = self.cache.get(analysis_id, question, fingerprint)
            if hit is not None:
                return ChatResult(
                    reply=hit["reply"], source="cache", estimated_cost_usd=0.0, model=hit.get("model"),
                    tool_calls=hit.get("tool_calls", []),
                )

        # 3) Paid call, only when explicitly requested.
        if mode in {"auto", "free"}:
            return ChatResult(
                reply=NEEDS_CLAUDE_TEXT, source="none", needs_claude=(mode == "auto"),
                estimated_cost_usd=self.budget.estimated_answer_cost_usd() if mode == "auto" else None,
                budget=self.budget.status(),
            )

        reply = self.agent.chat(analysis_id, raw_messages)
        cost = estimate_cost_usd(getattr(reply, "model", None), getattr(reply, "input_tokens", 0), getattr(reply, "output_tokens", 0))
        text = getattr(reply, "reply", "")
        stop = getattr(reply, "stop_reason", None)
        if single_turn and text and stop == "end_turn":
            self.cache.put(
                analysis_id, question, fingerprint, reply=text, model=getattr(reply, "model", None), cost_usd=cost,
                tool_calls=[{"name": c.name, "ok": c.ok} for c in getattr(reply, "tool_calls", [])],
            )
        return ChatResult(
            reply=text, source="claude", estimated_cost_usd=round(cost, 4),
            tool_calls=getattr(reply, "tool_calls", []), iterations=getattr(reply, "iterations", 0),
            stop_reason=stop, model=getattr(reply, "model", None),
            input_tokens=getattr(reply, "input_tokens", 0), output_tokens=getattr(reply, "output_tokens", 0),
            budget=getattr(reply, "budget", None),
        )
