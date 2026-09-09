"""Calculate quarterly Gross / Operating / Net margins from LQ Income Statement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.quarterly_presentation import STATEMENT_SHEETS, QuarterlyStatementKind
from models.quarterly_update import QuarterlyMarginEntry, QuarterlyMarginReport

LQ_IS = STATEMENT_SHEETS[QuarterlyStatementKind.INCOME]

# House presentation: first empty block after the statement body.
_MARGIN_START_ROW = 77
_MARGIN_SPECS = (
    ("gross_margin", "Gross Margin", "gross profit"),
    ("operating_margin", "Operating Margin", "operating income"),
    ("net_margin", "Net Margin", "net income"),
)


def compute_margin(numerator: float | None, revenue: float | None) -> float | None:
    """Gross/Operating/Net margin = numerator / revenue. None if revenue is 0/missing."""
    if numerator is None or revenue is None or revenue == 0:
        return None
    return float(numerator) / float(revenue)


def _norm(label: Any) -> str:
    return " ".join(str(label or "").lower().split())


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str) and v.startswith("="):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _is_formula(v: Any) -> bool:
    return isinstance(v, str) and v.startswith("=")


def _find_row(ws, needle: str, *, prefer_unindented: bool = True) -> int | None:
    """Locate a labeled body row; prefer the unindented total over nested lines."""
    hits: list[tuple[int, str]] = []
    for r in range(11, 76):
        label = ws.cell(r, 1).value
        if label is None:
            continue
        n = _norm(label)
        if needle in n:
            hits.append((r, str(label)))
    if not hits:
        return None
    if prefer_unindented:
        for r, lab in hits:
            if not lab.startswith(" "):
                return r
    return hits[0][0]


class QuarterlyMarginService:
    """Write Gross/Operating/Net margin formulas (or values) onto LQ IS."""

    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
    ) -> QuarterlyMarginReport:
        wb = load_workbook(workbook_path)
        entries: list[QuarterlyMarginEntry] = []
        try:
            if LQ_IS not in wb.sheetnames:
                return QuarterlyMarginReport(
                    analysis_id=analysis_id,
                    ticker=ticker,
                    summary="LQ IS sheet missing; margins not calculated.",
                )
            ws = wb[LQ_IS]
            rev_row = _find_row(ws, "revenue")
            gp_row = _find_row(ws, "gross profit")
            oi_row = _find_row(ws, "operating income")
            ni_row = _find_row(ws, "net income")
            # Net income: prefer GAAP total
            if ni_row is None:
                ni_row = _find_row(ws, "net income, gaap")

            row_map = {
                "gross_margin": gp_row,
                "operating_margin": oi_row,
                "net_margin": ni_row,
            }

            # Period columns: C/D = FQ vs prior-year FQ; G/H = YTD vs prior-year YTD
            period_cols = (
                ("yoy_quarter", 3, 4),
                ("ytd", 7, 8),
            )

            for idx, (metric, label, _needle) in enumerate(_MARGIN_SPECS):
                dest_row = _MARGIN_START_ROW + idx
                num_row = row_map[metric]
                existing_label = ws.cell(dest_row, 1).value
                if existing_label and _is_formula(existing_label):
                    continue
                # Keep an existing house formula in C if present
                if not _is_formula(ws.cell(dest_row, 1).value):
                    ws.cell(dest_row, 1).value = label

                for period_kind, curr_col, prior_col in period_cols:
                    for col in (curr_col, prior_col):
                        cell = ws.cell(dest_row, col)
                        addr = f"{get_column_letter(col)}{dest_row}"
                        if _is_formula(cell.value):
                            entries.append(
                                QuarterlyMarginEntry(
                                    metric=metric,
                                    period_kind=period_kind,
                                    cell=f"{LQ_IS}!{addr}",
                                    formula=str(cell.value),
                                    margin=None,
                                )
                            )
                            continue
                        if rev_row and num_row:
                            formula = (
                                f'=IF(OR({get_column_letter(col)}{rev_row}="",'
                                f'{get_column_letter(col)}{rev_row}=0),"",'
                                f'{get_column_letter(col)}{num_row}/'
                                f'{get_column_letter(col)}{rev_row})'
                            )
                            cell.value = formula
                            rev = _num(ws.cell(rev_row, col).value)
                            num = _num(ws.cell(num_row, col).value)
                            entries.append(
                                QuarterlyMarginEntry(
                                    metric=metric,
                                    period_kind=period_kind,
                                    revenue=rev,
                                    numerator=num,
                                    margin=compute_margin(num, rev),
                                    cell=f"{LQ_IS}!{addr}",
                                    formula=formula,
                                )
                            )
                        else:
                            entries.append(
                                QuarterlyMarginEntry(
                                    metric=metric,
                                    period_kind=period_kind,
                                    cell=f"{LQ_IS}!{addr}",
                                )
                            )

            wb.save(workbook_path)
        finally:
            wb.close()

        n = len({e.metric for e in entries})
        return QuarterlyMarginReport(
            analysis_id=analysis_id,
            ticker=ticker,
            entries=entries,
            summary=f"Quarterly margins written for {n} metrics (Gross/Operating/Net) on FQ and YTD columns.",
        )
