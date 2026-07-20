"""Discover validation cases from a workbook directory."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_WORKBOOK_EXTENSIONS = {".xlsx", ".xlsm", ".xls"}
_FILTER_EXTENSIONS = {".csv", ".xlsx", ".xlsm", ".xls"}


@dataclass(frozen=True)
class ValidationCase:
    """One company package ready for pipeline execution."""

    company: str
    ticker: str
    workbook_path: Path
    custom_run_path: Path
    case_dir: Path


def discover_cases(input_dir: Path) -> list[ValidationCase]:
    """
    Discover company packages under ``input_dir``.

    Expected layout (one subdirectory per company)::

        input_dir/
          AAPL/
            *Template*.xlsx                 # prefilled Industrial Template
            Custom_Run_Filter_*-AAPL.xlsx   # Bloomberg proprietary workbook
            manifest.json                   # optional {\"company\", \"ticker\"}
          MSFT/
            ...

    Subdirectories missing a workbook or Custom_Run_Filter are skipped with a log.
    """
    root = Path(input_dir).resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"Validation input directory not found: {root}")

    cases: list[ValidationCase] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        case = _parse_case_dir(child)
        if case is None:
            continue
        cases.append(case)

    logger.info("Discovered %s validation case(s) in %s", len(cases), root)
    return cases


def _parse_case_dir(case_dir: Path) -> ValidationCase | None:
    workbook = _find_workbook(case_dir)
    custom_run = _find_custom_run(case_dir)
    if workbook is None:
        logger.warning("Skipping %s: no workbook (.xlsx/.xlsm/.xls) found.", case_dir.name)
        return None
    if custom_run is None:
        logger.warning(
            "Skipping %s: no custom_run filter (.csv/.xlsx) found.",
            case_dir.name,
        )
        return None

    company = case_dir.name
    ticker = case_dir.name.upper()
    manifest_path = case_dir / "manifest.json"
    if manifest_path.exists():
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            company = str(payload.get("company") or company)
            ticker = str(payload.get("ticker") or ticker).upper()
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("Invalid manifest in %s (%s); using folder name.", case_dir, exc)

    return ValidationCase(
        company=company,
        ticker=ticker,
        workbook_path=workbook,
        custom_run_path=custom_run,
        case_dir=case_dir,
    )


def _find_workbook(case_dir: Path) -> Path | None:
    preferred = (
        list(case_dir.glob("prefilled*.xlsx"))
        + list(case_dir.glob("workbook*.xlsx"))
        + list(case_dir.glob("*.xlsx"))
        + list(case_dir.glob("*.xlsm"))
        + list(case_dir.glob("*.xls"))
    )
    for path in preferred:
        if path.name.startswith("~$"):
            continue
        if path.name.lower().startswith("custom_run"):
            continue
        if path.suffix.lower() in _WORKBOOK_EXTENSIONS:
            return path
    return None


def _find_custom_run(case_dir: Path) -> Path | None:
    candidates = (
        list(case_dir.glob("Custom_Run_Filter*"))
        + list(case_dir.glob("custom_run_filter.*"))
        + list(case_dir.glob("custom_run.*"))
        + list(case_dir.glob("*custom_run*"))
    )
    for path in candidates:
        if path.name.startswith("~$"):
            continue
        if path.is_file() and path.suffix.lower() in _FILTER_EXTENSIONS:
            return path
    return None
