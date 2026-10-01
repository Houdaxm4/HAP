"""Lessons library: what HAP has learned from the analyst's corrections.

How learning works here (deliberately conservative):
1. The feedback store records every approve / correct / reject / thumbs-down with the analyst's reason.
2. ``propose_from_feedback`` looks for REPEATED patterns (default: at least 3 cases) and writes a
   *proposed* lesson in plain English, with the feedback ids as evidence. No AI call is needed.
3. Nothing takes effect until the analyst approves it (optionally editing the wording).
4. Approved lessons are ADVISORY: they are added to the analyst chat's instructions and shown next to the
   review decisions they concern. They never change scores, rules or workbook numbers. A lesson that
   implies a rule change stays a note for a developer; it is not applied automatically.
"""

from __future__ import annotations

import hashlib
import statistics
import threading
import uuid
from collections import defaultdict
from pathlib import Path
from typing import Any

from models.common import utc_now_iso
from services.feedback_service import FeedbackService
from services.safe_io import write_json_atomic
from settings import lessons_dir, lesson_min_support

STATUSES = ("proposed", "approved", "rejected", "retired")
MAX_TEXT_CHARS = 1200
MAX_PROMPT_LESSONS = 8
MAX_PROMPT_CHARS = 2400
_LOCK = threading.Lock()

_TARGET_LABELS = {
    "lease_rate": "lease discount rate",
    "rd_useful_life": "R&D useful life",
    "recommendation": "recommendation",
    "chat_answer": "chat answer",
}


class LessonError(ValueError):
    """Invalid lesson operation."""


def _label(target: str) -> str:
    return _TARGET_LABELS.get(target, target.replace("_", " "))


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class LessonsService:
    def __init__(self, directory: Path | None = None, feedback: FeedbackService | None = None) -> None:
        self._directory = directory
        self.feedback = feedback or FeedbackService()

    @property
    def path(self) -> Path:
        directory = self._directory or lessons_dir()
        directory.mkdir(parents=True, exist_ok=True)
        return directory / "lessons.json"

    # ---- storage --------------------------------------------------------------------------

    def _load(self) -> list[dict[str, Any]]:
        path = self.path
        if not path.exists():
            return []
        import json

        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return []
        return data if isinstance(data, list) else []

    def _save(self, lessons: list[dict[str, Any]]) -> None:
        write_json_atomic(self.path, lessons)

    def list(self, status: str | None = None, analysis_type: str | None = None) -> list[dict[str, Any]]:
        if status is not None and status not in STATUSES:
            raise LessonError(f"status must be one of {STATUSES}.")
        with _LOCK:
            lessons = self._load()
        if status:
            lessons = [item for item in lessons if item.get("status") == status]
        if analysis_type:
            lessons = [item for item in lessons if item.get("analysis_type") in (analysis_type, "all")]
        return sorted(lessons, key=lambda item: item.get("created_at", ""), reverse=True)

    def get(self, lesson_id: str) -> dict[str, Any]:
        for item in self._load():
            if item.get("id") == lesson_id:
                return item
        raise LessonError("Lesson not found.")

    # ---- proposing ------------------------------------------------------------------------

    def propose_from_feedback(self) -> list[dict[str, Any]]:
        """Create *proposed* lessons from repeated feedback. Idempotent: known patterns are skipped."""
        rows = self.feedback.list(limit=1000)
        min_support = lesson_min_support()
        candidates: list[dict[str, Any]] = []

        # A) Repeated corrections of the agent's decisions, per decision type and analysis type.
        groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row.get("target") in (None, "chat_answer"):
                continue
            if row.get("action") in {"approve", "correct", "reject"}:
                groups[(row["target"], row.get("analysis_type") or "all")].append(row)
        for (target, analysis_type), items in groups.items():
            fixes = [r for r in items if r.get("action") in {"correct", "reject"}]
            if len(fixes) < min_support:
                continue
            candidates.append(self._decision_lesson(target, analysis_type, items, fixes))

        # B) Repeated "not right" marks on chat answers, with reasons.
        chat: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in rows:
            if row.get("target") == "chat_answer" and row.get("action") == "thumbs_down":
                chat[row.get("analysis_type") or "all"].append(row)
        for analysis_type, items in chat.items():
            with_reason = [r for r in items if r.get("reason")]
            if len(with_reason) >= min_support:
                candidates.append(self._chat_lesson(analysis_type, with_reason))

        created: list[dict[str, Any]] = []
        with _LOCK:
            lessons = self._load()
            known = {item.get("signature") for item in lessons if item.get("status") != "retired"}
            for cand in candidates:
                if cand["signature"] in known:
                    continue
                lessons.append(cand)
                created.append(cand)
                known.add(cand["signature"])
            if created:
                self._save(lessons)
        return created

    @staticmethod
    def _top_reasons(rows: list[dict[str, Any]], limit: int = 3) -> list[str]:
        seen: list[str] = []
        for row in rows:
            reason = (row.get("reason") or "").strip()
            if reason and reason not in seen:
                seen.append(reason[:200])
            if len(seen) >= limit:
                break
        return seen

    def _decision_lesson(self, target: str, analysis_type: str, items: list[dict], fixes: list[dict]) -> dict[str, Any]:
        rate = len(fixes) / len(items)
        sentence = (
            f"For {analysis_type.replace('_', ' ')} analyses the analyst corrected the agent's "
            f"{_label(target)} in {len(fixes)} of {len(items)} reviewed cases ({rate:.0%})."
        )
        pairs = [(r.get("agent_value"), r.get("analyst_value")) for r in fixes if _is_number(r.get("agent_value")) and _is_number(r.get("analyst_value"))]
        if len(pairs) >= 2:
            deltas = [b - a for a, b in pairs]
            direction = "higher" if statistics.median(deltas) > 0 else "lower"
            sentence += f" The analyst's value was typically {direction} (median change {statistics.median(deltas):+.4g})."
        reasons = self._top_reasons(fixes)
        if reasons:
            sentence += " Reasons given: " + "; ".join(reasons) + "."
        sentence += f" Treat the agent's {_label(target)} as a starting point and check it against filing evidence before relying on it."
        return self._new(
            signature=f"decision|{target}|{analysis_type}",
            target=target, analysis_type=analysis_type, kind="decision_correction",
            title=f"Analyst often corrects the {_label(target)}", text=sentence,
            evidence=[r["id"] for r in fixes], support_count=len(fixes),
        )

    def _chat_lesson(self, analysis_type: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        reasons = self._top_reasons(rows, limit=5)
        sentence = (
            f"Analysts marked {len(rows)} chat answers as not right. Reasons: " + "; ".join(reasons) + ". "
            "Before answering, verify each figure against the cited artifact, quote the period and unit, "
            "and say plainly when the stored results do not contain the answer."
        )
        return self._new(
            signature=f"chat|chat_answer|{analysis_type}",
            target="chat_answer", analysis_type=analysis_type, kind="chat_quality",
            title="Chat answers were marked not right", text=sentence,
            evidence=[r["id"] for r in rows], support_count=len(rows),
        )

    @staticmethod
    def _new(*, signature: str, target: str, analysis_type: str, kind: str, title: str, text: str,
             evidence: list[str], support_count: int) -> dict[str, Any]:
        return {
            "id": uuid.uuid4().hex[:12],
            "created_at": utc_now_iso(),
            "status": "proposed",
            "signature": signature,
            "kind": kind,
            "target": target,
            "analysis_type": analysis_type,
            "title": title,
            "text": text[:MAX_TEXT_CHARS],
            "evidence": evidence[:50],
            "support_count": support_count,
            "decided_at": None,
            "decision_note": None,
        }

    # ---- decisions by the analyst -----------------------------------------------------------

    def _decide(self, lesson_id: str, new_status: str, *, text: str | None = None, note: str | None = None) -> dict[str, Any]:
        with _LOCK:
            lessons = self._load()
            for item in lessons:
                if item.get("id") != lesson_id:
                    continue
                if new_status == "approved" and item.get("status") not in {"proposed", "retired", "rejected"}:
                    raise LessonError(f"A {item.get('status')} lesson cannot be approved.")
                if new_status == "retired" and item.get("status") != "approved":
                    raise LessonError("Only approved lessons can be retired.")
                if new_status == "rejected" and item.get("status") != "proposed":
                    raise LessonError("Only proposed lessons can be rejected.")
                if text is not None:
                    cleaned = text.strip()
                    if not cleaned:
                        raise LessonError("Lesson text cannot be empty.")
                    item["text"] = cleaned[:MAX_TEXT_CHARS]
                item["status"] = new_status
                item["decided_at"] = utc_now_iso()
                item["decision_note"] = (note or "").strip()[:500] or None
                self._save(lessons)
                return item
        raise LessonError("Lesson not found.")

    def approve(self, lesson_id: str, *, text: str | None = None, note: str | None = None) -> dict[str, Any]:
        return self._decide(lesson_id, "approved", text=text, note=note)

    def reject(self, lesson_id: str, *, note: str | None = None) -> dict[str, Any]:
        return self._decide(lesson_id, "rejected", note=note)

    def retire(self, lesson_id: str, *, note: str | None = None) -> dict[str, Any]:
        return self._decide(lesson_id, "retired", note=note)

    # ---- applying approved lessons (advisory only) -------------------------------------------

    def approved(self, analysis_type: str | None = None, targets: set[str] | None = None) -> list[dict[str, Any]]:
        items = self.list(status="approved", analysis_type=analysis_type)
        if targets is not None:
            items = [item for item in items if item.get("target") in targets]
        return items

    def prompt_lines(self, analysis_type: str | None) -> list[str]:
        """Short lesson texts for the analyst chat's instructions (bounded)."""
        lines: list[str] = []
        used = 0
        for item in self.approved(analysis_type)[:MAX_PROMPT_LESSONS]:
            text = item["text"]
            if used + len(text) > MAX_PROMPT_CHARS:
                break
            lines.append(text)
            used += len(text)
        return lines

    def version(self, analysis_type: str | None) -> str:
        """Changes whenever the set or wording of applicable approved lessons changes (cache key)."""
        parts = [f"{item['id']}:{hashlib.sha1(item['text'].encode('utf-8')).hexdigest()[:8]}" for item in self.approved(analysis_type)]
        return hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:12]
