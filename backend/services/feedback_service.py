"""Analyst feedback store: what the agent proposed, what the analyst decided, and why.

This is the raw material for learning. Nothing here changes agent behavior by itself;
repeated corrections will later be turned into *proposed* lessons that the analyst approves.

Storage: ``storage/feedback/feedback.jsonl`` (append-only, one JSON object per line).
"""

from __future__ import annotations

import json
import re
import threading
import uuid
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from models.common import utc_now_iso
from services.safe_io import validate_analysis_id
from settings import feedback_dir

VALID_ACTIONS = frozenset(
    {"approve", "correct", "reject", "request_more_evidence", "thumbs_up", "thumbs_down", "comment"}
)
_TARGET_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
MAX_REASON_CHARS = 2000
MAX_CONTEXT_CHARS = 4000
MAX_VALUE_CHARS = 1000
_LOCK = threading.Lock()


class FeedbackError(ValueError):
    """Invalid feedback payload."""


def _bounded_json(value: Any, limit: int, what: str) -> Any:
    if value is None:
        return None
    try:
        encoded = json.dumps(value, default=str)
    except (TypeError, ValueError) as exc:
        raise FeedbackError(f"{what} is not JSON serializable.") from exc
    if len(encoded) > limit:
        raise FeedbackError(f"{what} is too large (max {limit} characters).")
    return json.loads(encoded)


class FeedbackService:
    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory

    @property
    def path(self) -> Path:
        directory = self._directory or feedback_dir()
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "feedback.jsonl"

    # ---- write ----------------------------------------------------------------------------

    def add(
        self,
        *,
        analysis_id: str,
        target: str,
        action: str,
        agent_value: Any = None,
        analyst_value: Any = None,
        reason: str | None = None,
        context: dict[str, Any] | None = None,
        ticker: str | None = None,
        analysis_type: str | None = None,
        source: str = "ui",
    ) -> dict[str, Any]:
        validate_analysis_id(analysis_id)
        if action not in VALID_ACTIONS:
            raise FeedbackError(f"action must be one of {sorted(VALID_ACTIONS)}.")
        if not isinstance(target, str) or not _TARGET_RE.fullmatch(target):
            raise FeedbackError("target must be lowercase letters, digits or underscores.")
        if action == "correct" and analyst_value is None:
            raise FeedbackError("A correction must include analyst_value.")
        reason_text = (reason or "").strip()
        if len(reason_text) > MAX_REASON_CHARS:
            raise FeedbackError(f"reason is too long (max {MAX_REASON_CHARS} characters).")
        record = {
            "id": uuid.uuid4().hex,
            "created_at": utc_now_iso(),
            "analysis_id": analysis_id,
            "ticker": ticker,
            "analysis_type": analysis_type,
            "target": target,
            "action": action,
            "agent_value": _bounded_json(agent_value, MAX_VALUE_CHARS, "agent_value"),
            "analyst_value": _bounded_json(analyst_value, MAX_VALUE_CHARS, "analyst_value"),
            "reason": reason_text or None,
            "context": _bounded_json(context, MAX_CONTEXT_CHARS, "context"),
            "source": source,
        }
        with _LOCK:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record) + "\n")
        return record

    # ---- read -----------------------------------------------------------------------------

    def _all(self) -> list[dict[str, Any]]:
        path = self.path
        if not path.exists():
            return []
        rows: list[dict[str, Any]] = []
        with _LOCK:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rows.append(json.loads(line))
                    except ValueError:
                        continue  # a torn line must never break reads
        return rows

    def list(
        self,
        *,
        analysis_id: str | None = None,
        target: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        rows = self._all()
        if analysis_id is not None:
            rows = [r for r in rows if r.get("analysis_id") == analysis_id]
        if target is not None:
            rows = [r for r in rows if r.get("target") == target]
        rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
        return rows[: max(1, min(limit, 1000))]

    def summary(self) -> dict[str, Any]:
        rows = self._all()
        by_target: dict[str, Counter] = defaultdict(Counter)
        for row in rows:
            by_target[row.get("target", "?")][row.get("action", "?")] += 1
        targets: dict[str, Any] = {}
        for target, counts in sorted(by_target.items()):
            decisions = counts["approve"] + counts["correct"] + counts["reject"]
            targets[target] = {
                "counts": dict(counts),
                "decisions": decisions,
                "correction_rate": round((counts["correct"] + counts["reject"]) / decisions, 3) if decisions else None,
                "thumbs_up": counts["thumbs_up"],
                "thumbs_down": counts["thumbs_down"],
            }
        return {"total": len(rows), "targets": targets}
