"""Analysis-type completion scope — which workbook sections may be filled."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any

from openpyxl.workbook.workbook import Workbook

from workbook_mapping.sheet_policies import (
    ANNUAL_DATA_SHEETS,
    LQ_STANDARDIZED_SHEETS,
    OUTPUT_SHEETS,
)


class AnalysisTypeMode(str, Enum):
    NEW_COMPANY = "new_company"
    ANNUAL_UPDATE = "annual_update"
    QUARTERLY_UPDATE = "quarterly_update"


class WorkbookSection(str, Enum):
    TAX = "tax"
    PE10 = "pe10"
    CURRENT_DATA = "current_data"
    ANNUAL_INCOME = "annual_income_statement"
    ANNUAL_BALANCE_SHEET = "annual_balance_sheet"
    ANNUAL_CASH_FLOW = "annual_cash_flow"
    QUARTERLY_INCOME = "quarterly_income_statement"
    QUARTERLY_BALANCE_SHEET = "quarterly_balance_sheet"
    QUARTERLY_CASH_FLOW = "quarterly_cash_flow"
    CONTROL = "control"
    RATIOS = "ratios"
    ROIC = "roic"
    VALUATION = "valuation"
    EXPECTED_RETURN = "expected_return"
    OTHER = "other"


# Source authority labels (machine-readable).
SOURCE_SEC_10K = "sec_edgar_10k"
SOURCE_SEC_10Q = "sec_edgar_10q"
SOURCE_BLOOMBERG_CRF = "bloomberg_custom_run"
SOURCE_BLOOMBERG_PREFILL = "bloomberg_prefill"
SOURCE_MARKET = "market_internet"
SOURCE_NONE = "none"

_FY_RE = re.compile(r"FY\s*(\d{4})", re.IGNORECASE)
_YEAR_RE = re.compile(r"^(\d{4})$")

# Quarterly Bloomberg population thresholds (decision layer only).
QUARTERLY_MATERIAL_EMPTY_RATIO = 0.20
QUARTERLY_SUBSTANTIAL_RATIO = 0.40


def normalize_analysis_type(raw: str | None) -> AnalysisTypeMode:
    """Map free-form analysis_type strings to the three supported modes."""
    if not raw:
        return AnalysisTypeMode.NEW_COMPANY
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    key = re.sub(r"_+", "_", key)
    aliases = {
        "new_company": AnalysisTypeMode.NEW_COMPANY,
        "newcompany": AnalysisTypeMode.NEW_COMPANY,
        "new": AnalysisTypeMode.NEW_COMPANY,
        "annual_update": AnalysisTypeMode.ANNUAL_UPDATE,
        "annual": AnalysisTypeMode.ANNUAL_UPDATE,
        "annual_update_mode": AnalysisTypeMode.ANNUAL_UPDATE,
        "quarterly_update": AnalysisTypeMode.QUARTERLY_UPDATE,
        "quarterly": AnalysisTypeMode.QUARTERLY_UPDATE,
        "lq_update": AnalysisTypeMode.QUARTERLY_UPDATE,
        "last_quarter": AnalysisTypeMode.QUARTERLY_UPDATE,
    }
    if key in aliases:
        return aliases[key]
    if "quarter" in key:
        return AnalysisTypeMode.QUARTERLY_UPDATE
    if "annual" in key:
        return AnalysisTypeMode.ANNUAL_UPDATE
    if "new" in key and "company" in key:
        return AnalysisTypeMode.NEW_COMPANY
    return AnalysisTypeMode.NEW_COMPANY


def normalize_fy_token(period: str | None) -> str | None:
    if not period:
        return None
    text = str(period).strip()
    m = _FY_RE.search(text)
    if m:
        return f"FY{m.group(1)}"
    m = _YEAR_RE.match(text)
    if m:
        return f"FY{m.group(1)}"
    return text.upper() if text else None


def classify_workbook_section(
    *,
    sheet: str,
    metric: str | None = None,
    cfm_path: str | None = None,
    period: str | None = None,
) -> WorkbookSection:
    """Map a mapped cell / intent to a workbook section for mode scoping."""
    sheet_l = (sheet or "").strip()
    metric_l = (metric or "").strip().lower()
    path_l = (cfm_path or "").strip().lower()
    blob = f"{metric_l} {path_l}"

    if sheet_l == "Inputs":
        if path_l.startswith("inputs.tax") or "tax" in metric_l:
            return WorkbookSection.TAX
        if "pe10" in blob or path_l in {"inputs.pe10", "inputs.e10"} or metric_l in {
            "pe10",
            "e10",
        }:
            return WorkbookSection.PE10
        if path_l.startswith("inputs.current") or path_l.startswith("inputs.max") or path_l.startswith(
            "inputs.exit"
        ) or path_l.startswith("inputs.expected") or path_l.startswith("inputs.pe10_percentile"):
            return WorkbookSection.CURRENT_DATA
        if "current" in metric_l or "price" in metric_l:
            return WorkbookSection.CURRENT_DATA
        return WorkbookSection.OTHER

    if sheet_l == "Tax" or path_l.startswith("tax.") or (
        sheet_l not in ANNUAL_DATA_SHEETS
        and ("effective tax" in blob or metric_l in {"tax", "tax rate", "cash tax"})
    ):
        return WorkbookSection.TAX

    if "pe10" in blob or "pe_10" in blob or sheet_l.upper() == "PE10":
        return WorkbookSection.PE10

    if (
        path_l.startswith("market_data")
        or "share_price" in blob
        or "market_cap" in blob
        or "current price" in blob
        or "shares outstanding" in blob
        or sheet_l.lower() in {"current", "current data", "market"}
    ):
        return WorkbookSection.CURRENT_DATA

    if sheet_l in LQ_STANDARDIZED_SHEETS or sheet_l.startswith("Last Quarter"):
        if "IS" in sheet_l or "Income" in sheet_l:
            return WorkbookSection.QUARTERLY_INCOME
        if "BS" in sheet_l or "Balance" in sheet_l:
            return WorkbookSection.QUARTERLY_BALANCE_SHEET
        if "CF" in sheet_l or "Cash" in sheet_l:
            return WorkbookSection.QUARTERLY_CASH_FLOW
        return WorkbookSection.OTHER

    if sheet_l == "Income - GAAP":
        if metric_l in {"ticker", "start year", "end year"} or path_l.startswith("metadata."):
            return WorkbookSection.CONTROL
        if path_l == "ticker":
            return WorkbookSection.CONTROL
        return WorkbookSection.ANNUAL_INCOME

    if sheet_l == "Balance Sheet - Standardized":
        if metric_l in {"ticker", "start year", "end year"} or path_l in {
            "ticker",
            "metadata.template_start_year",
            "metadata.template_end_year",
        }:
            return WorkbookSection.CONTROL
        return WorkbookSection.ANNUAL_BALANCE_SHEET

    if sheet_l == "Cash Flow - Standardized":
        if metric_l in {"ticker", "start year", "end year"} or path_l in {
            "ticker",
            "metadata.template_start_year",
            "metadata.template_end_year",
        }:
            return WorkbookSection.CONTROL
        return WorkbookSection.ANNUAL_CASH_FLOW

    if "ROIC" in sheet_l or "NOPAT" in sheet_l or "IC &" in sheet_l:
        return WorkbookSection.ROIC

    if sheet_l in {"All Ratios", "Final Metrics", "BS%", "IS%", "CF%", "FCF"}:
        return WorkbookSection.RATIOS

    if sheet_l == "Enterprise Value" or "wacc" in blob:
        return WorkbookSection.VALUATION

    if sheet_l == "Expected Returns & Buybacks":
        return WorkbookSection.EXPECTED_RETURN

    if sheet_l in OUTPUT_SHEETS:
        return WorkbookSection.VALUATION

    return WorkbookSection.OTHER


def source_authority_for(section: WorkbookSection) -> str:
    return {
        WorkbookSection.TAX: SOURCE_SEC_10K,
        WorkbookSection.PE10: SOURCE_BLOOMBERG_CRF,
        WorkbookSection.CURRENT_DATA: SOURCE_BLOOMBERG_CRF,
        WorkbookSection.ANNUAL_INCOME: SOURCE_BLOOMBERG_PREFILL,
        WorkbookSection.ANNUAL_BALANCE_SHEET: SOURCE_BLOOMBERG_PREFILL,
        WorkbookSection.ANNUAL_CASH_FLOW: SOURCE_BLOOMBERG_PREFILL,
        WorkbookSection.QUARTERLY_INCOME: SOURCE_BLOOMBERG_CRF,
        WorkbookSection.QUARTERLY_BALANCE_SHEET: SOURCE_BLOOMBERG_CRF,
        WorkbookSection.QUARTERLY_CASH_FLOW: SOURCE_BLOOMBERG_CRF,
        WorkbookSection.CONTROL: SOURCE_BLOOMBERG_PREFILL,
        WorkbookSection.RATIOS: SOURCE_NONE,
        WorkbookSection.ROIC: SOURCE_NONE,
        WorkbookSection.VALUATION: SOURCE_NONE,
        WorkbookSection.EXPECTED_RETURN: SOURCE_NONE,
        WorkbookSection.OTHER: SOURCE_NONE,
    }.get(section, SOURCE_NONE)


def sections_for_mode(mode: AnalysisTypeMode) -> frozenset[WorkbookSection]:
    """Sections eligible for completion under each analysis type."""
    if mode == AnalysisTypeMode.NEW_COMPANY:
        return frozenset(
            {
                WorkbookSection.TAX,
                WorkbookSection.PE10,
                WorkbookSection.CURRENT_DATA,
            }
        )
    if mode == AnalysisTypeMode.ANNUAL_UPDATE:
        return frozenset(
            {
                WorkbookSection.TAX,
                WorkbookSection.PE10,
                WorkbookSection.CURRENT_DATA,
                WorkbookSection.ANNUAL_INCOME,
                WorkbookSection.ANNUAL_BALANCE_SHEET,
                WorkbookSection.ANNUAL_CASH_FLOW,
                WorkbookSection.CONTROL,
            }
        )
    # quarterly_update
    return frozenset(
        {
            WorkbookSection.CURRENT_DATA,
            WorkbookSection.QUARTERLY_INCOME,
            WorkbookSection.QUARTERLY_BALANCE_SHEET,
            WorkbookSection.QUARTERLY_CASH_FLOW,
        }
    )


def is_required_for_mode(
    mode: AnalysisTypeMode,
    section: WorkbookSection,
    period: str | None,
    *,
    target_fiscal_year: str | None,
) -> bool:
    """Return whether this section/period is a completion target for the mode."""
    if section not in sections_for_mode(mode):
        return False

    if mode == AnalysisTypeMode.ANNUAL_UPDATE:
        annual_sections = {
            WorkbookSection.ANNUAL_INCOME,
            WorkbookSection.ANNUAL_BALANCE_SHEET,
            WorkbookSection.ANNUAL_CASH_FLOW,
            WorkbookSection.TAX,
            WorkbookSection.PE10,
        }
        if section in annual_sections:
            if target_fiscal_year is None:
                return section in {WorkbookSection.CURRENT_DATA, WorkbookSection.CONTROL}
            fy = normalize_fy_token(period)
            if section == WorkbookSection.CONTROL:
                return True
            # Point-in-time tax/PE10/current controls (e.g. tax unit flag, current PE10)
            if fy is None or fy in {"CURRENT", "CONTROL", "N/A", "POINT"}:
                return section in {
                    WorkbookSection.TAX,
                    WorkbookSection.PE10,
                    WorkbookSection.CURRENT_DATA,
                }
            return fy == normalize_fy_token(target_fiscal_year)
        return True

    return True


def infer_target_fiscal_year(
    *,
    workbook: Workbook | None = None,
    periods: list[str] | None = None,
    explicit: str | None = None,
) -> str | None:
    """Resolve the single new fiscal year for annual_update scoping."""
    if explicit:
        return normalize_fy_token(explicit)

    if workbook is not None:
        for sheet in ("Income - GAAP", "Balance Sheet - Standardized", "Cash Flow - Standardized"):
            if sheet not in workbook.sheetnames:
                continue
            end_year = workbook[sheet]["C3"].value
            token = normalize_fy_token(str(end_year) if end_year is not None else None)
            if token:
                return token

    years: list[int] = []
    for p in periods or []:
        token = normalize_fy_token(p)
        if not token:
            continue
        m = _FY_RE.search(token)
        if m:
            years.append(int(m.group(1)))
    if not years:
        return None
    return f"FY{max(years)}"


def assess_quarterly_bloomberg_health(
    workbook: Workbook,
    *,
    empty_ratio: float = QUARTERLY_MATERIAL_EMPTY_RATIO,
    substantial_ratio: float = QUARTERLY_SUBSTANTIAL_RATIO,
) -> dict[str, Any]:
    """
    Aggregate LQ health for completion_service compatibility.

    Prefer per-statement ``quarterly_health_service`` for presentation authority.
    """
    from models.quarterly_presentation import PresentationDecision
    from services.quarterly_health_service import assess_all_quarterly_statements

    del empty_ratio, substantial_ratio  # superseded by structural algorithm
    assessments = assess_all_quarterly_statements(workbook)
    per_sheet: dict[str, dict[str, Any]] = {}
    ratios: list[float] = []
    any_sec = False
    all_preserve = True
    reasons: list[str] = []
    for health, decision in assessments:
        fill = 1.0 - health.missing_ratio if health.present else 0.0
        ratios.append(fill)
        per_sheet[health.sheet] = {
            "present": health.present,
            "expected": health.expected_mapped_rows,
            "populated": health.populated_rows,
            "missing": health.missing_required_rows,
            "ratio": round(fill, 4),
            "decision": decision.value,
            "structural_failure": health.structural_failure,
            "major_totals_present": health.major_totals_present,
        }
        reasons.append(f"{decision.value}: {health.reason}")
        if decision == PresentationDecision.SEC_10Q_PRESENTATION_REQUIRED:
            any_sec = True
            all_preserve = False
        elif decision == PresentationDecision.YAHOO_BASIC_TEMPLATE_REQUIRED:
            any_sec = True  # may still use SEC as secondary
            all_preserve = False
        elif decision != PresentationDecision.BLOOMBERG_PRESERVE:
            all_preserve = False

    min_ratio = min(ratios) if ratios else 0.0
    avg_ratio = (sum(ratios) / len(ratios)) if ratios else 0.0
    return {
        "sec_quarterly_fallback_required": any_sec,
        "substantially_populated": all_preserve and not any_sec,
        "min_fill_ratio": round(min_ratio, 4),
        "avg_fill_ratio": round(avg_ratio, 4),
        "per_sheet": per_sheet,
        "per_statement_decisions": {
            health.statement.value: decision.value for health, decision in assessments
        },
        "reason": " | ".join(reasons),
    }


def scope_summary(mode: AnalysisTypeMode) -> dict[str, list[str]]:
    in_scope = sorted(s.value for s in sections_for_mode(mode))
    all_sections = sorted(s.value for s in WorkbookSection)
    out = [s for s in all_sections if s not in in_scope]
    return {"sections_in_scope": in_scope, "sections_out_of_scope": out}
