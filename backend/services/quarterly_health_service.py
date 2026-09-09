"""Deterministic Bloomberg quarterly statement health assessment."""

from __future__ import annotations

from typing import Any

from openpyxl.workbook.workbook import Workbook

from models.quarterly_presentation import (
    STATEMENT_SHEETS,
    BloombergHealthAssessment,
    PresentationDecision,
    QuarterlyStatementKind,
)

BODY_START = 11
BODY_END = 130  # LQ BS totals (Total Liabilities/Equity) sit past row 80
LABEL_COL = 1
VALUE_COL = 3

# Flexible label needles for major totals / anchors.
_MAJOR_TOTALS: dict[QuarterlyStatementKind, tuple[str, ...]] = {
    QuarterlyStatementKind.INCOME: (
        "revenue",
        "gross profit",
        "net income",
        "operating income",
    ),
    QuarterlyStatementKind.BALANCE_SHEET: (
        "total assets",
        "total liabilities",
        "total equity",
        "cash",
        "inventor",
        "receiv",
        "total current assets",
        "property, plant",
        "accounts payable",
        "st debt",
        "lt debt",
        "total current liabilities",
    ),
    QuarterlyStatementKind.CASH_FLOW: (
        "cash from operating",
        "operating activities",
        "cash from investing",
        "investing activities",
        "cash from financing",
        "financing activities",
    ),
}

# Column G on LQ IS holds YTD; missing YTD while FQ is present → SEC presentation.
YTD_COL = 7

# Structural failure if missingness this high among expected labeled rows.
STRUCTURAL_MISSING_RATIO = 0.55
# Isolated gaps: at most this missing ratio AND majors present.
ISOLATED_GAP_RATIO = 0.18
# Minimum expected labeled line items for a usable Bloomberg statement.
MIN_EXPECTED_ROWS = 8


def _norm(label: Any) -> str:
    return " ".join(str(label or "").lower().split())


def _is_formula(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("=")


def _is_check_label(label: str) -> bool:
    n = _norm(label)
    return n == "check" or n.startswith("check ")


def _is_section_header(label: str, value: Any) -> bool:
    """Section titles often have no numeric value and no leading indent markers alone."""
    if value is not None and not _is_formula(value) and isinstance(value, (int, float)):
        return False
    n = _norm(label)
    if not n or _is_check_label(n):
        return False
    # Pure section banners
    banners = (
        "condensed consolidated",
        "consolidated statements",
        "income statement",
        "balance sheet",
        "cash flow",
    )
    return any(n.startswith(b) for b in banners)


def iter_statement_rows(ws) -> list[dict[str, Any]]:
    """Return labeled body rows with population flags."""
    rows: list[dict[str, Any]] = []
    for r in range(BODY_START, BODY_END + 1):
        label = ws.cell(row=r, column=LABEL_COL).value
        if label is None or (isinstance(label, str) and label.strip() == ""):
            continue
        if _is_formula(label):
            continue
        label_s = str(label).strip()
        if _is_check_label(label_s):
            continue
        value = ws.cell(row=r, column=VALUE_COL).value
        if _is_section_header(label_s, value):
            continue
        populated = isinstance(value, (int, float))
        formula = _is_formula(value)
        rows.append(
            {
                "row": r,
                "label": label_s,
                "value": value,
                "populated": populated,
                "formula": formula,
                "cell_ref": f"{ws.title}!A{r}",
            }
        )
    return rows


def assess_statement_health(
    workbook: Workbook,
    kind: QuarterlyStatementKind,
) -> BloombergHealthAssessment:
    sheet = STATEMENT_SHEETS[kind]
    if sheet not in workbook.sheetnames:
        return BloombergHealthAssessment(
            statement=kind,
            sheet=sheet,
            present=False,
            structural_failure=True,
            reason=f"Sheet '{sheet}' missing from workbook",
            coherence_notes=["sheet_absent"],
        )

    ws = workbook[sheet]
    rows = iter_statement_rows(ws)
    expected = len(rows)
    # Formula-backed values count as structurally present (Bloomberg layout intact).
    populated = sum(1 for r in rows if r["populated"] or r["formula"])
    missing = max(0, expected - populated)
    missing_ratio = (missing / expected) if expected else 1.0

    majors = _MAJOR_TOTALS[kind]
    found: list[str] = []
    missing_majors: list[str] = []
    labels_joined = " | ".join(_norm(r["label"]) for r in rows)
    for needle in majors:
        # Require at least one matching populated/formula row for the needle family
        hits = [
            r
            for r in rows
            if needle in _norm(r["label"]) and (r["populated"] or r["formula"])
        ]
        if hits:
            found.append(needle)
        else:
            # Only count as required major if a label exists OR it's a primary anchor
            label_exists = any(needle in _norm(r["label"]) for r in rows)
            if label_exists or needle in majors[:2]:
                missing_majors.append(needle)

    # Income: Bloomberg FQ present but cumulative/YTD (col G) missing → treat as incomplete.
    missing_cumulative = False
    if kind == QuarterlyStatementKind.INCOME and rows:
        has_ytd_axis = False
        for hr in range(1, 11):
            for hc in range(1, 12):
                hv = ws.cell(row=hr, column=hc).value
                if isinstance(hv, str) and "ytd" in hv.lower():
                    has_ytd_axis = True
                    break
        ytd_populated = 0
        fq_populated = 0
        for r in rows:
            if "revenue" in _norm(r["label"]) or "net income" in _norm(r["label"]):
                ytd_v = ws.cell(row=r["row"], column=YTD_COL).value
                if isinstance(ytd_v, (int, float)) or _is_formula(ytd_v):
                    ytd_populated += 1
                if r["populated"] or r["formula"]:
                    fq_populated += 1
        if has_ytd_axis and fq_populated >= 1 and ytd_populated == 0:
            missing_cumulative = True

    # Primary anchors: first two needles are required for coherence
    primary = majors[:2]
    primary_ok = all(
        any(needle in _norm(r["label"]) and (r["populated"] or r["formula"]) for r in rows)
        for needle in primary
    ) if expected >= MIN_EXPECTED_ROWS else False

    major_totals_present = primary_ok and len(missing_majors) <= max(0, len(majors) - 2)

    notes: list[str] = []
    structural = False
    if not expected or expected < MIN_EXPECTED_ROWS:
        structural = True
        notes.append(f"too_few_labeled_rows:{expected}")
    if missing_ratio >= STRUCTURAL_MISSING_RATIO:
        structural = True
        notes.append(f"high_missing_ratio:{missing_ratio:.2%}")
    if not primary_ok and expected >= MIN_EXPECTED_ROWS:
        structural = True
        notes.append(f"primary_totals_missing:{primary}")
    if expected == 0:
        structural = True
        notes.append("empty_statement_body")

    isolated = (
        not structural
        and major_totals_present
        and 0 < missing_ratio <= ISOLATED_GAP_RATIO
    )
    if isolated:
        notes.append("isolated_gaps_only")

    if missing_cumulative:
        structural = True
        notes.append("sec_required_for_missing_ytd")

    if structural:
        reason = (
            f"{sheet}: structural Bloomberg failure "
            f"(expected={expected}, populated={populated}, missing_ratio={missing_ratio:.1%}, "
            f"majors_missing={missing_majors}"
            f"{', missing_ytd' if missing_cumulative else ''})"
        )
    elif isolated:
        reason = (
            f"{sheet}: Bloomberg usable with isolated gaps "
            f"(missing={missing}/{expected}, majors present)"
        )
    elif missing == 0 and major_totals_present:
        reason = f"{sheet}: Bloomberg substantially complete (populated={populated}/{expected})"
    else:
        reason = (
            f"{sheet}: Bloomberg mostly complete "
            f"(populated={populated}/{expected}, missing_ratio={missing_ratio:.1%})"
        )

    return BloombergHealthAssessment(
        statement=kind,
        sheet=sheet,
        present=True,
        expected_mapped_rows=expected,
        populated_rows=populated,
        missing_required_rows=missing,
        missing_ratio=round(missing_ratio, 4),
        major_totals_present=major_totals_present,
        major_totals_missing=missing_majors,
        structural_failure=structural,
        isolated_gaps=isolated,
        coherence_notes=notes + ([f"labels_sample:{labels_joined[:120]}"] if rows else []),
        reason=reason,
    )


def decide_presentation(health: BloombergHealthAssessment) -> PresentationDecision:
    if not health.present:
        return PresentationDecision.BLOCKED
    if health.structural_failure:
        if health.statement in (
            QuarterlyStatementKind.INCOME,
            QuarterlyStatementKind.CASH_FLOW,
        ):
            return PresentationDecision.YAHOO_BASIC_TEMPLATE_REQUIRED
        # BS structural gaps: fill from Yahoo/SEC without layout rewrite
        return PresentationDecision.BLOOMBERG_FILL_GAPS
    if health.isolated_gaps:
        return PresentationDecision.BLOOMBERG_FILL_GAPS
    if health.major_totals_present and health.missing_ratio <= ISOLATED_GAP_RATIO:
        return PresentationDecision.BLOOMBERG_PRESERVE
    if health.missing_ratio < STRUCTURAL_MISSING_RATIO and health.major_totals_present:
        return PresentationDecision.BLOOMBERG_FILL_GAPS
    return PresentationDecision.SEC_10Q_PRESENTATION_REQUIRED


def assess_all_quarterly_statements(workbook: Workbook) -> list[tuple[BloombergHealthAssessment, PresentationDecision]]:
    out: list[tuple[BloombergHealthAssessment, PresentationDecision]] = []
    for kind in QuarterlyStatementKind:
        health = assess_statement_health(workbook, kind)
        out.append((health, decide_presentation(health)))
    return out
