"""Monthly Claude API spend tracking with a hard cap.

Every model call made for the analyst agent is recorded (tokens and estimated USD) in
``storage/usage/usage-YYYY-MM.jsonl``. Before each call the agent asks ``assert_available``;
once the month's spend reaches the cap, further calls are refused until next month.

Prices are USD per million tokens (input, output) from Anthropic's published rates. Cache
discounts are ignored, so the estimate errs on the high side. Unknown models are priced at
the most expensive known rate so a typo can never bypass the cap.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from models.common import utc_now_iso
from settings import monthly_budget_usd, usage_dir

PRICES_USD_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-opus-5": (5.0, 25.0),
    "claude-opus-4-8": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-opus-4-6": (5.0, 25.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-fable-5-1": (10.0, 50.0),
    "claude-fable-5": (10.0, 50.0),
}
UNKNOWN_MODEL_PRICE = (10.0, 50.0)
WARN_FRACTION = 0.8

_LOCK = threading.Lock()


class BudgetExceededError(Exception):
    """Raised when the monthly Claude budget has been used up."""


def price_for(model: str | None) -> tuple[float, float]:
    name = (model or "").lower()
    best = None
    for key in PRICES_USD_PER_MTOK:
        if name.startswith(key) and (best is None or len(key) > len(best)):
            best = key
    return PRICES_USD_PER_MTOK[best] if best else UNKNOWN_MODEL_PRICE


def estimate_cost_usd(model: str | None, input_tokens: int, output_tokens: int) -> float:
    in_price, out_price = price_for(model)
    return (max(input_tokens, 0) * in_price + max(output_tokens, 0) * out_price) / 1_000_000


class BudgetService:
    def __init__(self, directory: Path | None = None, cap_usd: float | None = None) -> None:
        self._directory = directory
        self._cap_override = cap_usd

    # ---- paths / config -------------------------------------------------------------------

    @property
    def directory(self) -> Path:
        directory = self._directory or usage_dir()
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    @property
    def cap_usd(self) -> float:
        return self._cap_override if self._cap_override is not None else monthly_budget_usd()

    @staticmethod
    def month_key(now: datetime | None = None) -> str:
        return (now or datetime.now(timezone.utc)).strftime("%Y-%m")

    def _file(self, month: str) -> Path:
        return self.directory / f"usage-{month}.jsonl"

    # ---- recording ------------------------------------------------------------------------

    def record(
        self,
        *,
        analysis_id: str | None,
        model: str | None,
        input_tokens: int,
        output_tokens: int,
        purpose: str = "chat",
    ) -> dict[str, Any]:
        entry = {
            "at": utc_now_iso(),
            "analysis_id": analysis_id,
            "model": model,
            "purpose": purpose,
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
            "cost_usd": round(estimate_cost_usd(model, input_tokens, output_tokens), 6),
        }
        with _LOCK:
            with self._file(self.month_key()).open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        return entry

    def spent_usd(self, month: str | None = None) -> float:
        path = self._file(month or self.month_key())
        if not path.exists():
            return 0.0
        total = 0.0
        with _LOCK:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    try:
                        total += float(json.loads(line).get("cost_usd", 0.0))
                    except (ValueError, TypeError):
                        continue
        return total

    def estimated_answer_cost_usd(self, default: float = 0.15) -> float:
        """Rough cost of one paid answer: recent average per-call cost x ~3 tool-loop calls."""
        path = self._file(self.month_key())
        costs: list[float] = []
        if path.exists():
            with _LOCK:
                with path.open("r", encoding="utf-8") as handle:
                    for line in handle:
                        try:
                            row = json.loads(line)
                        except ValueError:
                            continue
                        if row.get("purpose") == "chat":
                            costs.append(float(row.get("cost_usd", 0.0)))
        recent = costs[-20:]
        return round(sum(recent) / len(recent) * 3, 3) if recent else default

    # ---- status ---------------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        spent = self.spent_usd()
        cap = self.cap_usd
        pct = (spent / cap * 100.0) if cap > 0 else 100.0
        if pct >= 100.0:
            level = "exceeded"
        elif pct >= WARN_FRACTION * 100.0:
            level = "warning"
        else:
            level = "ok"
        return {
            "month": self.month_key(),
            "spent_usd": round(spent, 4),
            "cap_usd": round(cap, 2),
            "remaining_usd": round(max(cap - spent, 0.0), 4),
            "percent_used": round(pct, 1),
            "level": level,
        }

    def assert_available(self) -> dict[str, Any]:
        status = self.status()
        if status["level"] == "exceeded":
            raise BudgetExceededError(
                f"The monthly Claude budget (${status['cap_usd']:.2f}) is used up for {status['month']}. "
                "Raise HAP_MONTHLY_BUDGET_USD or wait until next month."
            )
        return status
