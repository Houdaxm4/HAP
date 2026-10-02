"""Golden cases: saved inputs + an expected fingerprint, stored under regression/cases/<name>/."""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from models.common import utc_now_iso
from regression.compare import diff
from regression.fingerprint import full_fingerprint
from regression.replay import INPUT_FILES, replay

CASES_DIR = Path(__file__).resolve().parent / "cases"


@dataclass
class CaseResult:
    name: str
    passed: bool
    approved: bool
    diffs: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "approved": self.approved, "diffs": self.diffs[:25], "error": self.error}


def _read(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def read_case_meta(case_dir: Path) -> dict[str, Any]:
    return _read(case_dir / "case.json")


def list_cases(cases_dir: Path | None = None) -> list[Path]:
    base = cases_dir or CASES_DIR
    return sorted(p.parent for p in base.glob("*/case.json"))


def check_case(case_dir: Path) -> CaseResult:
    meta = _read(case_dir / "case.json")
    try:
        engine, final = replay(case_dir / "inputs")
    except Exception as exc:  # noqa: BLE001 - a crash is a failed case, reported not raised
        return CaseResult(meta["name"], False, bool(meta.get("approved")), error=f"{type(exc).__name__}: {exc}")
    differences = diff(_read(case_dir / "expected.json"), full_fingerprint(engine, final))
    return CaseResult(meta["name"], not differences, bool(meta.get("approved")), diffs=differences)


def check_all(cases_dir: Path | None = None) -> list[CaseResult]:
    return [check_case(case) for case in list_cases(cases_dir)]


def snapshot(
    *, storage_outputs: Path, analysis_id: str, name: str, ticker: str, analysis_type: str, note: str,
    cases_dir: Path | None = None,
) -> dict[str, Any]:
    """Freeze a stored analysis as a golden case (a baseline of CURRENT behaviour; approval is separate)."""
    source = storage_outputs / analysis_id
    case_dir = (cases_dir or CASES_DIR) / name
    inputs = case_dir / "inputs"
    inputs.mkdir(parents=True, exist_ok=True)
    copied = []
    for filename in INPUT_FILES:
        if (source / filename).exists():
            shutil.copyfile(source / filename, inputs / filename)
            copied.append(filename)
    engine, final = replay(inputs)
    fingerprint = full_fingerprint(engine, final)

    stored_final_path = source / "final_recommendation_report.json"
    stored_final = _read(stored_final_path) if stored_final_path.exists() else None
    stored_engine = _read(source / "analysis_engine_result.json")
    reproduced = not diff(full_fingerprint(stored_engine, stored_final), fingerprint)

    meta = {
        "name": name, "ticker": ticker, "analysis_type": analysis_type, "source_analysis_id": analysis_id,
        "created_at": utc_now_iso(), "inputs": copied, "note": note,
        "approved": False, "approval_note": None,
        "replay_reproduces_stored_outputs": reproduced,
    }
    _write(case_dir / "expected.json", fingerprint)
    _write(case_dir / "case.json", meta)
    return meta


def approve(name: str, note: str, cases_dir: Path | None = None) -> dict[str, Any]:
    path = (cases_dir or CASES_DIR) / name / "case.json"
    if not path.exists():
        raise FileNotFoundError(f"No such case: {name}")
    meta = _read(path)
    meta["approved"] = True
    meta["approval_note"] = note
    meta["approved_at"] = utc_now_iso()
    _write(path, meta)
    return meta
