"""Keep the analyst's lease and R&D assumptions when a company is UPDATED (annual or quarterly).

Leases   the previous file shows the Estimated Long-Term Rate typed in by hand (a constant, not the template formula): that
         number is the analyst's assumption and is continued. The newly computed rate is kept only when it looks reasonable
         (inside 1%-10% and within 2 points of the analyst's number); the lease row service applies that test.
R&D      the useful life and the earlier R&D expenses the amortization needs come from the PREVIOUS file. Only when the
         previous file has a blank, a placeholder zero or a value that disagrees with the filings does HAP go to the 10-Ks
         (SEC structured data, then the R&D note in the 10-K text) as the source of truth, and each such change is recorded.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from services.annual_period_service import detect_year_columns

log = logging.getLogger(__name__)

RATE_MIN, RATE_MAX = 0.01, 0.10
RD_TOLERANCE = 0.10                   # a previous-file R&D value this far from the 10-K is treated as inaccurate
_RATE_LABELS = ("estimated long-term rate", "long-term rate", "long term rate")
_RD_TAGS = ("ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost")


def _num(value: Any) -> float | None:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _is_formula(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("=")


def previous_manual_lease_rate(previous_workbook_path: Path | str | None) -> float | None:
    """The rate the analyst typed in the previous file's newest year (a constant), or None when that year used the formula."""
    if not previous_workbook_path or not Path(previous_workbook_path).exists():
        return None
    wb = load_workbook(previous_workbook_path, data_only=False)
    try:
        if "Leases" not in wb.sheetnames:
            return None
        ws = wb["Leases"]
        row = next((r for r in range(1, min(ws.max_row or 1, 40) + 1)
                    if any(name in str(ws.cell(r, 1).value or "").strip().lower() for name in _RATE_LABELS)), 18)
        cols = {k: c for k, c in detect_year_columns(ws, wb).items() if str(k).startswith("FY")}
        if not cols:
            return None
        newest_col = max(cols.values())
        value = _num(ws.cell(row, newest_col).value)
        if value is None or _is_formula(ws.cell(row, newest_col).value):
            return None
        value = value / 100.0 if abs(value) > 1.5 else value
        return value if RATE_MIN <= value <= RATE_MAX else None
    finally:
        wb.close()


@dataclass
class RdFix:
    cell: str
    fiscal_year: str
    original: Any
    new: float
    why: str
    source: str


@dataclass
class RdHistoryReport:
    life: float | None = None
    life_note: str | None = None
    fixes: list[RdFix] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.fixes)

    def summary(self) -> str:
        return (f"R&D assumptions: life={self.life}; {len(self.fixes)} history cells set (previous file by year, or 10-K where it was blank or wrong); "
                f"{len(self.unresolved)} unresolved" + (f"; {self.life_note}" if self.life_note else ""))


def _sec_rd(company_facts: dict[str, Any] | None, year: int) -> float | None:
    """R&D expense for a fiscal year from the SEC structured data, in millions (None when absent)."""
    if not company_facts:
        return None
    from services.sec_service import SecService

    sec = SecService()
    for tag in _RD_TAGS:
        try:
            fact = sec.find_fact(company_facts, "rd_expense", f"FY{year}", xbrl_tag_hint=tag)
        except Exception:  # noqa: BLE001 - a missing fact is not an error here
            fact = None
        if fact is not None and fact.value is not None:
            value = float(fact.value)
            return value / 1_000_000.0 if abs(value) >= 10_000 else value
    return None


def _prewindow_is_blank(value: Any) -> bool:
    if value in (None, ""):
        return True
    if _is_formula(value):
        text = str(value).replace(" ", "")
        return ',0,' in text and '=""' in text           # template formula that turns missing history into zero
    return False


def _previous_rd_by_year(previous_workbook_path: Path | str | None) -> dict[int, float]:
    """R&D expense per fiscal year as the previous file holds it (R&D tab, row 2). Placeholder zeros (template formula on a blank
    Inputs cell) and blanks are left out, so they are never mistaken for a reported zero."""
    out: dict[int, float] = {}
    if not previous_workbook_path or not Path(previous_workbook_path).exists():
        return out
    cached = load_workbook(previous_workbook_path, data_only=True)
    formulas = load_workbook(previous_workbook_path, data_only=False)
    try:
        if "R&D" not in cached.sheetnames:
            return out
        cws, fws = cached["R&D"], formulas["R&D"]
        for col in range(2, min(cws.max_column or 1, 40) + 1):
            header = str(cws.cell(1, col).value or "")
            digits = "".join(ch for ch in header if ch.isdigit())
            value = _num(cws.cell(2, col).value)
            if len(digits) != 4 or value is None:
                continue
            if fws.cell(2, col).value in (None, "") or (value == 0 and _is_formula(fws.cell(2, col).value)):
                continue          # blank, or the template formula returning its zero placeholder
            out[int(digits)] = value
        return out
    finally:
        cached.close()
        formulas.close()


def ensure_rd_history(
    workbook_path: Path,
    *,
    ticker: str,
    previous_workbook_path: Path | str | None = None,
    company_facts: dict[str, Any] | None = None,
    use_filing_text: bool = True,
) -> RdHistoryReport:
    """R&D useful life and the earlier R&D expenses the amortization needs, taken from the PREVIOUS file and matched by fiscal year
    (the window rolls forward, so the same column holds a different year). A year the previous file has blank, as a placeholder zero,
    or with a value more than 10% away from the 10-K is taken from the 10-K instead, and the change is recorded."""
    from services.annual_rd_service import AnnualRdService

    report = RdHistoryReport()
    previous_by_year = _previous_rd_by_year(previous_workbook_path)
    wb = load_workbook(workbook_path, data_only=False)
    changed = False
    try:
        if "R&D" not in wb.sheetnames or "Inputs" not in wb.sheetnames:
            return report
        ows = wb["R&D"]

        # --- useful life: the previous file's number, whatever the new template says
        previous_life = None
        if previous_workbook_path and Path(previous_workbook_path).exists():
            pw = load_workbook(previous_workbook_path, data_only=False)
            try:
                if "R&D" in pw.sheetnames:
                    previous_life = _num(pw["R&D"]["B8"].value)
            finally:
                pw.close()
        current_life = _num(ows["B8"].value)
        if previous_life is not None and previous_life >= 1:
            if current_life != previous_life and not _is_formula(ows["B8"].value):
                ows["B8"].value = previous_life
                changed = True
            report.life = previous_life
        elif current_life is not None:
            report.life = current_life
        else:
            report.life_note = ("the useful life is blank in the previous file and the 10-K does not state one; it needs the analyst's "
                                "choice (HAP did not guess)")
            report.unresolved.append("R&D!B8 (useful life)")
        life_years = int(report.life) if report.life and report.life >= 1 else 3
        needed = max(life_years - 1, 1)

        # --- pre-window expenses
        pre_cols = AnnualRdService._prewindow_expense_columns(ows)
        inputs_cols = {k: c for k, c in detect_year_columns(wb["Inputs"], wb).items() if str(k).startswith("FY")}
        if pre_cols and inputs_cols:
            first_year = min(int("".join(ch for ch in k if ch.isdigit())) for k in inputs_cols)
            slots = {col: first_year - (len(pre_cols) - i) for i, col in enumerate(pre_cols)}
            from services.adjustment_ledger_service import AdjustmentLedger

            ledger = AdjustmentLedger(wb)
            todo: list[tuple[int, int, Any, float | None, str]] = []      # (col, year, original, wanted value, why)
            for col in pre_cols:
                year = slots[col]
                current = ows.cell(2, col).value
                sec_value = _sec_rd(company_facts, year) if (col in pre_cols[-needed:] or year not in previous_by_year) else None
                if year in previous_by_year:
                    value = previous_by_year[year]
                    if sec_value not in (None, 0) and abs(value - sec_value) / abs(sec_value) > RD_TOLERANCE:
                        todo.append((col, year, current, sec_value,
                                     f"the previous file shows {value:,.1f} for FY{year} but the 10-K reports {sec_value:,.1f}"))
                    elif _num(current) is None or abs(_num(current) - value) > 1e-9 or _is_formula(current):
                        todo.append((col, year, current, value, f"FY{year} R&D expense carried from the previous file by fiscal year"))
                else:
                    todo.append((col, year, current, sec_value, f"the previous file has no R&D expense for FY{year}"))
            filing_values: dict[str, tuple[float, str]] = {}
            missing = [f"FY{y}" for _c, y, _o, v, _w in todo if v is None]
            if missing and use_filing_text:
                try:
                    from services.new_company_rd_service import NewCompanyRdService
                    from services.sec_service import SecService

                    filing_values = NewCompanyRdService._rd_from_filings(SecService(), ticker, missing, {})
                except Exception as exc:  # noqa: BLE001 - the gap is reported below instead
                    log.warning("10-K text lookup for R&D history failed: %s", exc)
            for col, year, original, value, why in todo:
                addr = f"{get_column_letter(col)}2"
                source = "the previous file" if (year in previous_by_year and value == previous_by_year[year]) else "10-K structured data (SEC XBRL)"
                if value is None and f"FY{year}" in filing_values:
                    value, source = filing_values[f"FY{year}"][0], "10-K text: research and development note"
                if value is None:
                    if col in pre_cols[-needed:]:
                        report.unresolved.append(f"R&D!{addr} (FY{year}): {why}; no 10-K figure found")
                    continue
                if _num(original) is not None and abs(_num(original) - float(value)) < 1e-9 and not _is_formula(original):
                    continue
                ows.cell(2, col).value = round(float(value), 3)
                changed = True
                from_filing = source != "the previous file"
                ledger.record(
                    sheet="R&D", cell=addr, fiscal_year=f"FY{year}", category="R&D history",
                    what="R&D expense needed for the amortization", original=original if original is not None else "blank",
                    new=round(float(value), 3), amount=round(float(value), 3),
                    reason=why + ("; the 10-K is the source of truth" if from_filing else ""),
                    source=source, method="filing_value" if from_filing else "previous_file_by_year",
                    confidence="high" if from_filing else "medium",
                )
                report.fixes.append(RdFix(f"R&D!{addr}", f"FY{year}", original, round(float(value), 3), why, source))
        if changed:
            wb.save(workbook_path)
        return report
    finally:
        wb.close()


def _fy_columns_with_first(ws, wb) -> dict[str, int]:
    """FY label -> column. Column B's header is often a formula the detector cannot read, so it is inferred from its neighbour."""
    cols = {str(k): c for k, c in detect_year_columns(ws, wb).items() if str(k).startswith("FY")}
    if cols and 2 not in cols.values():
        first = min(cols.items(), key=lambda kv: kv[1])
        digits = int("".join(ch for ch in first[0] if ch.isdigit()))
        if first[1] == 3:
            cols[f"FY{digits - 1}"] = 2
    return cols


def carry_previous_lease_rates(workbook_path: Path | str, previous_workbook_path: Path | str | None) -> list[str]:
    """Every earlier year whose Estimated Long-Term Rate the analyst typed in the PREVIOUS file keeps that number in the new file,
    matched by fiscal year (the 10-year window rolls, so the column letter changes). The newest year is handled by the lease row
    service. Returns the fiscal years changed; each change is recorded in the HAP Adjustments tab."""
    if not previous_workbook_path or not Path(previous_workbook_path).exists():
        return []
    pw = load_workbook(previous_workbook_path, data_only=False)
    try:
        if "Leases" not in pw.sheetnames:
            return []
        pws = pw["Leases"]
        prow = next((r for r in range(1, min(pws.max_row or 1, 40) + 1)
                     if any(n in str(pws.cell(r, 1).value or "").strip().lower() for n in _RATE_LABELS)), 18)
        previous: dict[str, float] = {}
        for key, col in _fy_columns_with_first(pws, pw).items():
            raw = pws.cell(prow, col).value
            value = _num(raw)
            if value is not None and not _is_formula(raw):
                value = value / 100.0 if abs(value) > 1.5 else value
                if RATE_MIN <= value <= RATE_MAX:
                    previous[str(key)] = value
    finally:
        pw.close()
    if not previous:
        return []
    wb = load_workbook(workbook_path, data_only=False)
    changed: list[str] = []
    try:
        if "Leases" not in wb.sheetnames:
            return []
        ws = wb["Leases"]
        row = next((r for r in range(1, min(ws.max_row or 1, 40) + 1)
                    if any(n in str(ws.cell(r, 1).value or "").strip().lower() for n in _RATE_LABELS)), 18)
        cols = _fy_columns_with_first(ws, wb)
        if not cols:
            return []
        newest = max(cols.values())
        from services.adjustment_ledger_service import AdjustmentLedger

        ledger = AdjustmentLedger(wb)
        for fy, col in sorted(cols.items(), key=lambda kv: kv[1]):
            if col == newest or fy not in previous:
                continue
            current = ws.cell(row, col).value
            if not _is_formula(current) and _num(current) is not None and abs(_num(current) - previous[fy]) < 1e-9:
                continue
            ws.cell(row, col).value = previous[fy]
            ledger.record(
                sheet="Leases", cell=f"{get_column_letter(col)}{row}", fiscal_year=fy, category="Lease rate",
                what="Estimated Long-Term Rate", original=current, new=previous[fy], amount=previous[fy],
                reason=f"the analyst typed {previous[fy]:.2%} for {fy} in the previous file; the same assumption is continued",
                source="the previous file", method="previous_file_by_year", confidence="medium",
            )
            changed.append(fy)
        if changed:
            wb.save(workbook_path)
        return changed
    finally:
        wb.close()
