"""Everything the analyst must know before reading a report, collected from the analysis artifacts.

Read-only. Categories, most important first:
  attention  - data a metric needs but no source has, material differences, blocked gates, workbook problems
  filled     - blanks HAP filled from SEC (shaded in the workbook)
  corrected  - values HAP changed from SEC evidence (original kept in the cell comment)
  judgments  - decisions the agent made that the analyst may override
  notes      - informational
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CATEGORIES = ("attention", "filled", "corrected", "judgments", "notes")
SUMMARY_LABELS = {
    "attention": "need your attention",
    "filled": "filled from online sources",
    "corrected": "corrected from SEC evidence",
    "judgments": "agent decisions you can override",
    "notes": "notes",
}
TITLES = {
    "attention": "Needs your attention",
    "filled": "Filled by HAP from online sources",
    "corrected": "Corrected from SEC evidence",
    "judgments": "Decisions the agent made (you can override)",
    "notes": "Notes",
}
MAX_ROWS = {"attention": 25, "filled": 80, "corrected": 40, "judgments": 10, "notes": 10}


def _read(directory: Path, name: str) -> dict[str, Any] | None:
    path = directory / name
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


CONCEPT_NAMES = {
    "cfo": "Cash from operations", "cfi": "Cash from investing", "cff": "Cash from financing",
    "capex": "Capital expenditures", "pretax_income": "Pre-tax income", "diluted_eps": "Diluted EPS",
    "income_tax_expense": "Income tax expense", "diluted_shares": "Diluted shares",
}


def _concept(raw: Any) -> str:
    key = str(raw or "")
    return CONCEPT_NAMES.get(key) or key.replace("_", " ").title()


def _flag(category: str, title: str, detail: str = "", source: str = "") -> dict[str, str]:
    return {"category": category, "title": title, "detail": detail, "source": source}


def _fmt(value: Any) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:,.1f}" if abs(value) >= 100 else f"{value:,.3f}".rstrip("0").rstrip(".")
    return str(value)


def collect_flags(output_dir: Path, authorized: bool | None = None) -> dict[str, Any]:
    flags: dict[str, list[dict[str, str]]] = {c: [] for c in CATEGORIES}

    gate = _read(output_dir, "new_company_output_gate_report.json") or _read(output_dir, "annual_output_gate_report.json")
    status = (gate or {}).get("status")
    if authorized is None:
        authorized = bool((gate or {}).get("report_authorized", status in (None, "ok", "OK", "pass")))

    # ---- annual statements: filled / unavailable / differences -------------------------------------------------
    statements = _read(output_dir, "new_company_statement_validation_report.json")
    if statements:
        for item in statements.get("filled_missing", []):
            flags["filled"].append(_flag(
                "filled", f"{_concept(item.get('concept'))} {item.get('fiscal_year', '')}",
                f"{_fmt(item.get('new_value'))} at {item.get('cell', '')}", item.get("source") or "SEC 10-K",
            ))
        for text in statements.get("flagged_missing", []):
            flags["attention"].append(_flag(
                "attention", "Data not available online and needed by a metric",
                f"{text}. Metrics that depend on this cell are incomplete.", "SEC EDGAR: not found",
            ))
        for item in statements.get("corrections", []):
            flags["attention"].append(_flag(
                "attention", f"{_concept(item.get('concept'))} {item.get('fiscal_year', '')}: workbook differs from SEC",
                f"Workbook {_fmt(item.get('old_value'))} vs SEC {_fmt(item.get('new_value'))} at {item.get('cell', '')}. "
                "The supplied value was kept and flagged.", item.get("source") or "SEC 10-K",
            ))

    # ---- quarterly statements ---------------------------------------------------------------------------------
    quarterly = _read(output_dir, "quarterly_presentation_report.json")
    if quarterly:
        for item in quarterly.get("filled_from_sec", []):
            flags["filled"].append(_flag(
                "filled", f"{item.get('label', '')} (latest quarter)", f"{_fmt(item.get('value'))} at {item.get('cell', '')}",
                item.get("source") or "SEC 10-Q",
            ))
        for text in quarterly.get("flagged_missing", []):
            flags["attention"].append(_flag(
                "attention", "Quarterly data not available online and needed by a metric", text, "SEC 10-Q: not found",
            ))
        totals_only = [i for i in quarterly.get("filled_from_sec", []) if "Cash Flow" in str(i.get("cell", "")) or "CF " in str(i.get("cell", ""))]
        if totals_only:
            flags["notes"].append(_flag(
                "notes", "Quarterly cash-flow check rows show differences",
                f"{len(totals_only)} cash-flow total(s) were filled from the 10-Q while their breakdown lines were blank in the "
                "supplied workbook; the template's check rows on those blocks are expected to differ (explained in each cell comment).",
                "Workbook",
            ))
        for statement in quarterly.get("statements", []):
            for item in statement.get("source_discrepancies", []):
                flags["attention"].append(_flag(
                    "attention", f"Quarterly value differs from SEC: {item.get('label', '')}",
                    f"Workbook {_fmt(item.get('workbook_value'))} vs SEC {_fmt(item.get('sec_value'))} at {item.get('cell', '')}.",
                    "SEC 10-Q",
                ))

    # ---- material differences found by the analyst-review pass --------------------------------------------------
    review = _read(output_dir, "analyst_review_report.json")
    if review and review.get("material_count"):
        material = [f for f in review.get("findings", []) if f.get("severity") == "MATERIAL"]
        flags["attention"].append(_flag(
            "attention", f"{review['material_count']} material difference(s) between the supplied workbook and SEC",
            "Largest: " + "; ".join(str(f.get("observation", ""))[:110] for f in material[:3]),
            "Analyst-review pass",
        ))

    # ---- corrections ---------------------------------------------------------------------------------------------
    buybacks = _read(output_dir, "new_company_buyback_report.json")
    if buybacks:
        for year in buybacks.get("years", []):
            if year.get("write_action") in {"corrected_from_sec", "filled"}:
                flags["corrected"].append(_flag(
                    "corrected", f"Buyback dollars {year.get('fiscal_year', '')}",
                    f"{_fmt(year.get('workbook_dollars'))} -> {_fmt(year.get('dollars'))} ($M)", year.get("dollars_source") or "SEC",
                ))
    recast = _read(output_dir, "new_company_cost_recast_report.json")
    if recast:
        for year in recast.get("years", []):
            if year.get("status") == "written":
                flags["corrected"].append(_flag(
                    "corrected", f"Cost of revenue {year.get('fiscal_year', '')} recast to the company's '{str(recast.get('label', '')).title()}' line",
                    f"{len(year.get('cells', []))} cells moved between cost and operating expenses; total costs and operating income unchanged.",
                    year.get("source") or "10-K income statement",
                ))

    # ---- agent decisions -----------------------------------------------------------------------------------------
    lease = _read(output_dir, "lease_rate_review.json")
    if lease and lease.get("selected_rate") is not None:
        flags["judgments"].append(_flag(
            "judgments", f"Lease discount rate {float(lease['selected_rate']) * 100:.1f}% selected by the agent",
            str(lease.get("summary", "")), "Lease note in the 10-K" if lease.get("classification") == "disclosed" else "Estimated",
        ))
    rd = _read(output_dir, "rd_useful_life_decision.json")
    if rd and rd.get("selected_useful_life"):
        confidence = rd.get("confidence")
        flags["judgments"].append(_flag(
            "judgments", f"R&D useful life {rd['selected_useful_life']} years selected by the agent"
            + (f" (confidence {confidence:.1f})" if isinstance(confidence, (int, float)) else ""),
            str(rd.get("rationale", ""))[:300], "Agent decision",
        ))

    _annual_and_quarterly_sources(output_dir, flags)

    # ---- workbook health + gate -----------------------------------------------------------------------------------
    try:
        from services.workbook_health import health_report

        health = health_report(output_dir)
        for text in health.get("findings", []):
            flags["attention"].append(_flag("attention", "Workbook check", text, "Workbook"))
        for text in health.get("notes", []):
            flags["notes"].append(_flag("notes", "Workbook note", text, "Workbook"))
    except Exception:  # noqa: BLE001 - a failed check must not stop the report
        pass
    if gate:
        for blocker in gate.get("blockers", []):
            if blocker == "NEW_COMPANY_REPORT_NOT_AUTHORIZED":
                continue
            flags["attention"].append(_flag("attention", "Report gate", str(blocker), "Output gate"))
        # Already shown above as agent decisions.
        handled = {"RD_USEFUL_LIFE_AGENT_SELECTED", "RD_USEFUL_LIFE_EVIDENCE_WEAK", "LEASE_RATE_AUTONOMOUS_AGENT_DECISION"}
        for warning in gate.get("warnings", []):
            text = str(warning)
            if text in handled or text.startswith("DATA_UNAVAILABLE"):
                continue
            code, _, rest = text.partition(":")
            flags["notes"].append(_flag("notes", code.replace("_", " ").capitalize().replace("Pe10", "PE10") if rest else text, rest.strip() or "", "Output gate"))

    yahoo = [f for f in flags["filled"] if "yahoo" in f["source"].lower()]
    if yahoo:
        flags["notes"].append(_flag(
            "notes", f"{len(yahoo)} value(s) came from Yahoo Finance, not SEC",
            "Yahoo's free data is unofficial and indicative only. It was used only where SEC had nothing for that year and "
            "Yahoo's revenue or net income for the same period matched your workbook. Verify these against the filing.",
            "Yahoo Finance",
        ))
    counts = {category: len(items) for category, items in flags.items()}
    return {"authorized": authorized, "gate_status": status, "flags": flags, "counts": counts}


def _annual_and_quarterly_sources(output_dir: Path, flags: dict[str, list[dict[str, str]]]) -> None:
    """Artifacts of Annual and Quarterly updates. Each reader is tolerant: a missing file simply adds nothing."""
    annual = _read(output_dir, "annual_statement_validation_report.json")
    for item in (annual or {}).get("items", []):
        status = str(item.get("status", "")).upper()
        if status in {"FILLED_FROM_SEC", "FILLED_FROM_YAHOO"}:
            flags["filled"].append(_flag(
                "filled", f"{_concept(item.get('concept'))} {item.get('fiscal_year', '')}",
                f"{_fmt(item.get('filing_value') if status == 'FILLED_FROM_SEC' else item.get('bloomberg_value'))}",
                "SEC 10-K" if status == "FILLED_FROM_SEC" else "Yahoo Finance (indicative)",
            ))
        elif status == "MISSING_IMPORTANT":
            flags["attention"].append(_flag(
                "attention", "Data not available online and needed by a metric",
                f"{str(item.get('concept', '')).replace('_', ' ')} {item.get('fiscal_year', '')}. Metrics that depend on it are incomplete.",
                "SEC EDGAR: not found",
            ))
        elif status in {"DISCREPANCY", "REVIEW_REQUIRED"}:
            flags["attention"].append(_flag(
                "attention", f"{_concept(item.get('concept'))} {item.get('fiscal_year', '')}: workbook differs from the filing",
                f"Workbook {_fmt(item.get('bloomberg_value'))} vs filing {_fmt(item.get('filing_value'))}. {item.get('reason', '')}", "SEC 10-K",
            ))
    quarterly = _read(output_dir, "statement_validation_report.json")
    missing_sec = 0
    for item in (quarterly or {}).get("entries", []):
        status = str(item.get("status", "")).upper()
        if status in {"DISCREPANCY", "REVIEW_REQUIRED"}:
            flags["attention"].append(_flag(
                "attention", f"{item.get('metric', '')} {item.get('fiscal_period', '')}: workbook differs from SEC",
                f"Workbook {_fmt(item.get('workbook_value'))} vs SEC {_fmt(item.get('sec_value'))} at {item.get('workbook_cell', '')}.", "SEC 10-Q",
            ))
        elif status == "SOURCE_MISSING":
            missing_sec += 1
    if missing_sec:
        flags["notes"].append(_flag("notes", f"{missing_sec} statement line(s) could not be compared with SEC", "No matching SEC figure was found.", "SEC"))

    for name in ("annual_restatement_report.json", "restatement_check_report.json"):
        report = _read(output_dir, name)
        for item in (report or {}).get("review_required", []) or (report or {}).get("findings", []):
            text = item if isinstance(item, str) else json.dumps(item, default=str)[:200]
            flags["attention"].append(_flag("attention", "Possible restatement", text, "SEC filings"))

    for name in ("annual_analyst_judgment_report.json", "quarterly_analyst_judgment_report.json"):
        report = _read(output_dir, name)
        cells = (report or {}).get("hap_analysis_cells") or []
        if cells:
            flags["judgments"].append(_flag(
                "judgments", f"HAP wrote {len(cells)} cells of alternative valuation analysis beside your original assumptions",
                "Original cells are preserved; the HAP alternative is shaded and labelled HAP ANALYSIS.", "Valuation judgment",
            ))
    valuation = _read(output_dir, "quarterly_valuation_report.json")
    if valuation:
        decisions = ", ".join(
            f"{key.split('_')[0].upper()} {valuation[key]}" for key in ("er_decision", "oe_decision", "graham_decision") if valuation.get(key)
        )
        if decisions:
            flags["judgments"].append(_flag(
                "judgments", f"Valuation decisions: {decisions}",
                "KEEP_EXISTING means the original assumption stood; ADJUST means a HAP alternative is shown beside it.", "Valuation judgment",
            ))

    for name in ("annual_research_report.json", "quarterly_research_report.json"):
        report = _read(output_dir, name)
        if not report:
            continue
        if str(report.get("earnings_call_status", "")).endswith("UNAVAILABLE"):
            flags["notes"].append(_flag("notes", "Earnings-call transcript not available", "Management commentary comes from filings only.", "Research"))
        for conflict in report.get("source_conflicts", []) or []:
            flags["attention"].append(_flag("attention", "Sources conflict", str(conflict)[:200], "Research"))

