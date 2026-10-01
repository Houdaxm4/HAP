"""API payloads for the analyst chat endpoint."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=8000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=30)
    mode: Literal["auto", "free", "claude"] = Field(
        default="auto",
        description="auto/free never make a paid call; claude may (and remembers the answer).",
    )


class ToolCallSummary(BaseModel):
    name: str
    input: dict
    ok: bool


class ChatResponse(BaseModel):
    reply: str
    tool_calls: list[ToolCallSummary] = Field(default_factory=list)
    iterations: int = 0
    stop_reason: str | None = None
    model: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    budget: dict[str, Any] | None = None
    source: Literal["built_in", "cache", "claude", "none"] = "claude"
    intent: str | None = None
    needs_claude: bool = False
    estimated_cost_usd: float | None = None


class FeedbackRequest(BaseModel):
    """One piece of analyst feedback on something the agent proposed or said."""

    target: str = Field(min_length=1, max_length=40, description="e.g. lease_rate, rd_useful_life, recommendation, chat_answer")
    action: Literal["approve", "correct", "reject", "request_more_evidence", "thumbs_up", "thumbs_down", "comment"]
    agent_value: Any = None
    analyst_value: Any = None
    reason: str | None = Field(default=None, max_length=2000)
    context: dict[str, Any] | None = None


class CheckpointAnswer(BaseModel):
    decision: Literal["approve", "revise", "stop"]
    note: str | None = Field(default=None, max_length=2000)
