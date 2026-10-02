"""Remember paid answers so asking the same question again is free.

An answer is reused only while the analysis is unchanged: the cache key includes a
fingerprint of the analysis record and every stored artifact (name, size, modified time).
Any pipeline run, review decision or new output changes the fingerprint and retires the
old answers automatically. Answers also expire after ``TTL_DAYS``.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from models.common import utc_now_iso
from services.analysis_service import AnalysisService
from services.output_service import OutputService
from services.safe_io import validate_analysis_id, write_json_atomic
from settings import answer_cache_dir

TTL_DAYS = 30
MAX_QUESTION_KEY_CHARS = 400
_LOCK = threading.Lock()


def normalize_question(question: str) -> str:
    text = re.sub(r"\s+", " ", (question or "").strip().lower())
    return text.rstrip(" ?!.")[:MAX_QUESTION_KEY_CHARS]


class AnswerCache:
    def __init__(self, directory: Path | None = None) -> None:
        self._directory = directory

    def _folder(self, analysis_id: str) -> Path:
        validate_analysis_id(analysis_id)
        base = self._directory or answer_cache_dir()
        folder = base / analysis_id
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    @staticmethod
    def question_key(question: str) -> str:
        return hashlib.sha256(normalize_question(question).encode("utf-8")).hexdigest()[:32]

    @staticmethod
    def fingerprint(
        analysis_service: AnalysisService, output_service: OutputService, analysis_id: str, extra: str = ""
    ) -> str:
        analysis = analysis_service.get(analysis_id)
        parts: list[Any] = [analysis.updated_at, analysis.status, extra]
        directory = output_service.analysis_output_dir(analysis_id)
        for path in sorted(directory.iterdir(), key=lambda p: p.name):
            if path.is_file():
                stat = path.stat()
                parts.append([path.name, stat.st_size, stat.st_mtime_ns])
        return hashlib.sha256(json.dumps(parts, default=str).encode("utf-8")).hexdigest()

    def get(self, analysis_id: str, question: str, fingerprint: str) -> dict[str, Any] | None:
        path = self._folder(analysis_id) / f"{self.question_key(question)}.json"
        if not path.exists():
            return None
        try:
            with _LOCK, path.open("r", encoding="utf-8") as handle:
                entry = json.load(handle)
        except (OSError, ValueError):
            return None
        if entry.get("fingerprint") != fingerprint:
            return None
        try:
            created = datetime.fromisoformat(entry["created_at"])
        except (KeyError, ValueError):
            return None
        if datetime.now(timezone.utc) - created > timedelta(days=TTL_DAYS):
            return None
        return entry

    def put(
        self,
        analysis_id: str,
        question: str,
        fingerprint: str,
        *,
        reply: str,
        model: str | None,
        cost_usd: float,
        tool_calls: list[dict[str, Any]] | None = None,
    ) -> None:
        entry = {
            "created_at": utc_now_iso(),
            "fingerprint": fingerprint,
            "question": normalize_question(question),
            "reply": reply,
            "model": model,
            "cost_usd": round(cost_usd, 6),
            "tool_calls": tool_calls or [],
        }
        with _LOCK:
            write_json_atomic(self._folder(analysis_id) / f"{self.question_key(question)}.json", entry)

    def invalidate(self, analysis_id: str, question: str) -> bool:
        path = self._folder(analysis_id) / f"{self.question_key(question)}.json"
        with _LOCK:
            if path.exists():
                path.unlink()
                return True
        return False
