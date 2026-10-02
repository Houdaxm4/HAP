"""Keep only the latest run per company (and analysis type); delete older stored analyses.

Always a plan first (nothing is deleted until ``apply``). Never deleted:
  - the latest COMPLETE run of each (ticker, analysis type), or the latest run if none is complete
  - a run that is still processing
  - a run referenced by a certification record (storage/certifications) or by a regression case
  - an id listed in storage/retention_keep.json (a JSON list of analysis ids)
"""

from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from services.safe_io import validate_analysis_id

ACTIVE_STATES = {"processing", "recalculating"}
HEX8 = re.compile(r"(?<![0-9a-f])[0-9a-f]{8}(?![0-9a-f])")
FULL_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _dir_size(path: Path) -> int:
    total = 0
    stack = [str(path)]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(_long(current)) as entries:
                for entry in entries:
                    if entry.is_dir(follow_symlinks=False):
                        stack.append(entry.path)
                    else:
                        try:
                            total += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            pass
        except OSError:
            continue
    return total


def _long(path: str) -> str:
    """Extended-length path on Windows (the SEC caches nest deeply)."""
    if os.name == "nt" and not path.startswith("\\\\?\\"):
        return "\\\\?\\" + os.path.abspath(path)
    return path


@dataclass
class Plan:
    keep: list[dict[str, Any]] = field(default_factory=list)
    delete: list[dict[str, Any]] = field(default_factory=list)
    protected: list[dict[str, Any]] = field(default_factory=list)

    @property
    def bytes_freed(self) -> int:
        return sum(item["bytes"] for item in self.delete)


class RetentionService:
    def __init__(self, storage_root: Path) -> None:
        self.root = storage_root
        self.analyses = storage_root / "analyses"
        self.outputs = storage_root / "outputs"
        self.uploads = storage_root / "uploads"

    # ---- references that protect a run ------------------------------------------------------------------------

    def referenced(self, regression_dir: Path | None = None) -> set[str]:
        """Analysis ids (full) and 8-hex prefixes mentioned by certification records and regression cases."""
        found: set[str] = set()
        certs = self.root / "certifications"
        if certs.exists():
            for path in certs.rglob("*"):
                found.update(HEX8.findall(path.name.lower()))
                found.update(FULL_ID.findall(path.name.lower()))
                if path.is_file() and path.suffix.lower() in {".json", ".md", ".txt"} and path.stat().st_size < 400_000:
                    try:
                        text = path.read_text(encoding="utf-8", errors="ignore").lower()
                    except OSError:
                        continue
                    found.update(FULL_ID.findall(text))
        if regression_dir and regression_dir.exists():
            for case in regression_dir.glob("*/case.json"):
                try:
                    source = json.loads(case.read_text(encoding="utf-8")).get("source_analysis_id")
                except (OSError, ValueError):
                    continue
                if source:
                    found.add(str(source).lower())
        keep_file = self.root / "retention_keep.json"
        if keep_file.exists():
            try:
                found.update(str(x).lower() for x in json.loads(keep_file.read_text(encoding="utf-8")))
            except (OSError, ValueError):
                pass
        return found

    # ---- planning ---------------------------------------------------------------------------------------------

    def _records(self) -> list[dict[str, Any]]:
        rows = []
        for path in sorted(self.analyses.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            analysis_id = str(data.get("analysis_id") or path.stem)
            try:
                validate_analysis_id(analysis_id)
            except Exception:  # noqa: BLE001 - never touch an odd record
                continue
            rows.append({
                "id": analysis_id,
                "ticker": str(data.get("ticker") or "?").upper(),
                "type": str(data.get("analysis_type") or "?").lower(),
                "status": str(data.get("status") or ""),
                "created_at": str(data.get("created_at") or ""),
                "updated_at": str(data.get("updated_at") or ""),
            })
        return rows

    def plan(self, regression_dir: Path | None = None) -> Plan:
        protected_refs = self.referenced(regression_dir)
        groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in self._records():
            groups.setdefault((row["ticker"], row["type"]), []).append(row)
        plan = Plan()
        for (ticker, kind), rows in sorted(groups.items()):
            rows.sort(key=lambda r: (r["updated_at"] or r["created_at"], r["created_at"]), reverse=True)
            complete = [r for r in rows if r["status"] == "complete"]
            latest = (complete or rows)[0]
            for row in rows:
                item = {**row, "bytes": _dir_size(self.outputs / row["id"]) + _dir_size(self.uploads / row["id"])}
                reason = None
                if row is latest:
                    plan.keep.append({**item, "reason": "latest run"})
                    continue
                if row["status"] in ACTIVE_STATES:
                    reason = "still running"
                elif row["id"].lower() in protected_refs or row["id"][:8].lower() in protected_refs:
                    reason = "referenced by a certification record or regression case"
                if reason:
                    plan.protected.append({**item, "reason": reason})
                else:
                    plan.delete.append({**item, "reason": f"older than the latest {ticker} {kind} run"})
        return plan

    # ---- applying ---------------------------------------------------------------------------------------------

    def apply(self, plan: Plan) -> list[str]:
        """Delete exactly the planned runs. Returns the ids removed."""
        removed: list[str] = []
        for item in plan.delete:
            analysis_id = validate_analysis_id(item["id"])
            for target in (self.outputs / analysis_id, self.uploads / analysis_id):
                if target.exists():
                    shutil.rmtree(_long(str(target)), ignore_errors=True)
            record = self.analyses / f"{analysis_id}.json"
            if record.exists():
                record.unlink()
            removed.append(analysis_id)
        return removed
