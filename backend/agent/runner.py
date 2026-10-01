"""The HAP Analyst agent: a Claude tool-use loop over read-only analysis tools.

Design rules (see docs/HAP_PRODUCT_SPEC.md and the scoring engine):
- The agent explains and cites; it never writes, runs the pipeline, or approves review gates.
- Scores and recommendations stay deterministic; the model never re-scores.
- Tool results are untrusted data; the system prompt forbids following instructions in them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from agent.prompts import build_system_prompt
from agent.tools import TOOL_SCHEMAS, AnalystToolbox
from research.policy import research_enabled
from research.toolbox import RESEARCH_TOOL_SCHEMAS
from services.analysis_service import AnalysisNotFoundError, AnalysisService
from services.budget_service import BudgetExceededError, BudgetService
from services.lessons_service import LessonsService
from services.output_service import OutputService
from settings import agent_effort, agent_fallbacks_enabled, agent_max_iterations, agent_model

MAX_MESSAGES = 30
MAX_MESSAGE_CHARS = 8000
MAX_OUTPUT_TOKENS = 16000
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AgentError(Exception):
    """An error the API layer should report with a specific HTTP status."""

    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass
class ToolCallRecord:
    name: str
    input: dict[str, Any]
    ok: bool


@dataclass
class AgentReply:
    reply: str
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    iterations: int = 0
    stop_reason: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    budget: dict[str, Any] | None = None


def sanitize_messages(raw: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Keep only plain user/assistant text turns from the client, bounded in size."""
    cleaned: list[dict[str, str]] = []
    for item in raw[-MAX_MESSAGES:]:
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        cleaned.append({"role": role, "content": content[:MAX_MESSAGE_CHARS]})
    # The API requires the conversation to start with a user turn and end with one.
    while cleaned and cleaned[0]["role"] != "user":
        cleaned.pop(0)
    if not cleaned or cleaned[-1]["role"] != "user":
        raise AgentError("The last message must be from the user.", status_code=400)
    return cleaned


def _block_type(block: Any) -> str:
    return getattr(block, "type", None) or (block.get("type") if isinstance(block, dict) else "")


def _get(block: Any, key: str, default: Any = None) -> Any:
    return getattr(block, key, None) if not isinstance(block, dict) else block.get(key, default)


class AnalystAgent:
    """Answers analyst questions about ONE analysis using read-only tools."""

    def __init__(
        self,
        analysis_service: AnalysisService,
        output_service: OutputService,
        client_factory: Callable[[], Any] | None = None,
        budget_service: BudgetService | None = None,
        lessons_service: LessonsService | None = None,
    ) -> None:
        self.analysis_service = analysis_service
        self.output_service = output_service
        self.budget = budget_service or BudgetService()
        self.lessons = lessons_service
        self._client_factory = client_factory
        self._client: Any | None = None

    # ---- client ---------------------------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        if self._client_factory is not None:
            self._client = self._client_factory()
            return self._client
        try:
            import anthropic  # imported lazily so the rest of HAP runs without it
        except ImportError as exc:
            raise AgentError(
                "The analyst agent needs the 'anthropic' package. Run: pip install -r requirements.txt",
                status_code=503,
            ) from exc
        if not (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")):
            raise AgentError(
                "The analyst agent is not configured. Set ANTHROPIC_API_KEY in the backend environment.",
                status_code=503,
            )
        self._client = anthropic.Anthropic()
        return self._client

    def _create(self, client: Any, *, system: str, messages: list[Any], model: str | None = None) -> Any:
        params: dict[str, Any] = {
            "model": model or agent_model(),
            "max_tokens": MAX_OUTPUT_TOKENS,
            "system": system,
            "tools": TOOL_SCHEMAS + (RESEARCH_TOOL_SCHEMAS if research_enabled() else []),
            "messages": messages,
            "output_config": {"effort": agent_effort()},
        }
        if agent_fallbacks_enabled():
            try:
                return client.beta.messages.create(betas=[FALLBACK_BETA], fallbacks="default", **params)
            except TypeError as exc:
                # An older SDK without the fallbacks parameter: continue without server-side fallback.
                if "fallbacks" not in str(exc) and "betas" not in str(exc):
                    raise
        return client.messages.create(**params)

    @staticmethod
    def _translate_api_error(exc: Exception) -> AgentError:
        name = type(exc).__name__
        status = getattr(exc, "status_code", None)
        if name in {"AuthenticationError", "PermissionDeniedError"} or status in {401, 403}:
            return AgentError("The Anthropic API rejected the credentials. Check ANTHROPIC_API_KEY.", 503)
        if name == "RateLimitError" or status == 429:
            return AgentError("The analyst agent is rate limited. Try again in a moment.", 429)
        if name in {"APIConnectionError", "APITimeoutError"}:
            return AgentError("Could not reach the Anthropic API. Check the network and try again.", 503)
        if status == 400 and "credit" in str(exc).lower():
            return AgentError("The Anthropic account has no credit available.", 503)
        return AgentError(f"The analyst agent hit an API error ({name}).", 502)

    # ---- chat -----------------------------------------------------------------------------

    def chat(
        self,
        analysis_id: str,
        raw_messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        purpose: str = "chat",
        extra_system: str = "",
    ) -> AgentReply:
        try:
            toolbox = AnalystToolbox(self.analysis_service, self.output_service, analysis_id)
        except AnalysisNotFoundError as exc:
            raise AgentError(str(exc), status_code=404) from exc
        messages: list[Any] = list(sanitize_messages(raw_messages))
        analysis = toolbox.analysis
        system = build_system_prompt(
            company=analysis.company,
            ticker=analysis.ticker,
            analysis_type=analysis.analysis_type,
            status=analysis.status,
            lessons=self.lessons.prompt_lines(analysis.analysis_type) if self.lessons else None,
        )
        system += extra_system
        client = self._get_client()
        result = AgentReply(reply="")
        limit = agent_max_iterations()

        for _ in range(limit):
            try:
                self.budget.assert_available()
            except BudgetExceededError as exc:
                raise AgentError(str(exc), status_code=429) from exc
            try:
                response = self._create(client, system=system, messages=messages, model=model)
            except AgentError:
                raise
            except Exception as exc:  # noqa: BLE001 - mapped to a clean HTTP error
                if isinstance(exc, TypeError) and "authentication" in str(exc).lower():
                    raise AgentError(
                        "The analyst agent is not configured. Set ANTHROPIC_API_KEY in the backend environment.",
                        status_code=503,
                    ) from exc
                if type(exc).__module__.startswith("anthropic"):
                    raise self._translate_api_error(exc) from exc
                raise
            result.iterations += 1
            result.model = getattr(response, "model", result.model)
            usage = getattr(response, "usage", None)
            result.input_tokens += int(getattr(usage, "input_tokens", 0) or 0)
            result.output_tokens += int(getattr(usage, "output_tokens", 0) or 0)
            result.stop_reason = getattr(response, "stop_reason", None)
            self.budget.record(
                analysis_id=analysis_id,
                model=result.model or model or agent_model(),
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
                purpose=purpose,
            )
            result.budget = self.budget.status()

            if result.stop_reason == "refusal":
                result.reply = (
                    "The model declined to answer this request. Try rephrasing, "
                    "or ask about a specific figure or flag in this analysis."
                )
                return result

            tool_uses = [b for b in response.content if _block_type(b) == "tool_use"]
            if result.stop_reason != "tool_use" or not tool_uses:
                texts = [_get(b, "text", "") for b in response.content if _block_type(b) == "text"]
                result.reply = "\n\n".join(t for t in texts if t).strip()
                if result.stop_reason == "max_tokens":
                    result.reply += "\n\n[Answer was cut off at the length limit. Ask me to continue.]"
                return result

            # Echo the assistant turn (including any thinking blocks) unchanged, then answer
            # every tool call in ONE user message.
            messages.append({"role": "assistant", "content": response.content})
            tool_results: list[dict[str, Any]] = []
            for block in tool_uses:
                name = _get(block, "name", "")
                tool_input = _get(block, "input", {}) or {}
                text, is_error = toolbox.execute(name, tool_input)
                result.tool_calls.append(ToolCallRecord(name=name, input=dict(tool_input), ok=not is_error))
                item: dict[str, Any] = {"type": "tool_result", "tool_use_id": _get(block, "id"), "content": text}
                if is_error:
                    item["is_error"] = True
                tool_results.append(item)
            messages.append({"role": "user", "content": tool_results})

        result.reply = (
            "I reached my tool-use limit before finishing. Please ask a narrower question "
            "(for example about one module, flag or figure)."
        )
        return result
