"""Historical continuity for Annual Update — previous completed workbook is the historical authority."""

from __future__ import annotations

from copy import copy
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.annual_update import AnnualModelContinuityReport, ContinuityAction, ContinuityEntry
from services.annual_period_service import (
    AnnualPeriodAlignment,
    AnnualPeriodAlignmentError,
    align_fiscal_periods,
    detect_year_columns,
)
from services.circular_reference_service import CircularReferenceService
from services.formula_utils import (
    formula_references_column,
    formula_text,
    formula_would_self_reference,
    is_formula,
    shift_formula_columns,
)
from workbook_mapping.sheet_policies import OUTPUT_SHEETS

# Re-export for tests and downstream imports.
__all__ = ["AnnualContinuityService", "detect_year_columns", "align_fiscal_periods"]

_HISTORICAL_SHEETS = (
    "Income - GAAP",
    "Income - GAAP",
    "Balance Sheet - Standardized",
    "Balance Sheet - Standardized",
    "Cash Flow - Standardized",
    "Cash Flow - Standardized",
    "Inputs",
    "Tax",
    "R&D",
    "Leases",
    "IC & NOPAT & ROIC ",
    "IC & NOPAT & ROIC ",
    "Expected Returns & Buybacks",
    "Enterprise Value",
)

_FORMULA_ONLY_SHEETS = OUTPUT_SHEETS | {
    "All Ratios",
    "All Ratios",
    "Final Metrics",
    "Final Metrics",
    "IS%",
    "BS%",
    "CF%",
    "FCF",
}
_CURRENT_DATA_CELLS = {f"B{r}" for r in range(63, 76)}
_MAX_ROW = 140
_MAX_COL = 16


def _cell_kind(value: Any) -> str:
    if value is None or value == "":
        return "blank"
    if isinstance(value, str) and value.startswith("="):
        return "formula"
    if hasattr(value, "text"):
        return "formula"
    return "value"


def _formula_text(value: Any) -> str | None:
    return formula_text(value)


def _values_equal(a: Any, b: Any) -> bool:
    fa, fb = _formula_text(a), _formula_text(b)
    if fa is not None or fb is not None:
        return fa is not None and fb is not None and fa == fb
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-9
    return a == b


def _copy_style(src, dst) -> bool:
    if not src.has_style:
        return False
    dst.font = copy(src.font)
    dst.border = copy(src.border)
    dst.fill = copy(src.fill)
    dst.number_format = src.number_format
    dst.protection = copy(src.protection)
    dst.alignment = copy(src.alignment)
    return True


class AnnualContinuityService:
    """Reconcile persistent historical regions from the previous completed workbook."""

    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        template_path: Path,
        previous_workbook_path: Path,
        workbook_path: Path,
        new_fiscal_year: str | None = None,
        period_alignment: AnnualPeriodAlignment | None = None,
    ) -> AnnualModelContinuityReport:
        if period_alignment is None:
            period_alignment = align_fiscal_periods(template_path, previous_workbook_path)
        detected_new = new_fiscal_year or period_alignment.new_fiscal_year

        prev = load_workbook(previous_workbook_path, data_only=False)
        out = load_workbook(workbook_path, data_only=False)
        entries: list[ContinuityEntry] = []
        try:
            template_fy_cols = self._workbook_fy_columns(out)
            previous_fy_cols = self._workbook_fy_columns(prev)
            sheet_set = list(dict.fromkeys(list(_HISTORICAL_SHEETS) + list(_FORMULA_ONLY_SHEETS)))
            for sheet in sheet_set:
                if sheet not in prev.sheetnames or sheet not in out.sheetnames:
                    continue
                formula_guard = sheet in _FORMULA_ONLY_SHEETS
                pws, ows = prev[sheet], out[sheet]
                cols = detect_year_columns(ows, out)
                prev_cols = detect_year_columns(pws, prev)
                fy_cols = {fy: col for fy, col in cols.items() if fy.startswith("FY")}
                if not fy_cols:
                    fy_cols = {fy: template_fy_cols[fy] for fy in period_alignment.overlap_years if fy in template_fy_cols}
                if not fy_cols:
                    continue
                max_row = min(max(pws.max_row or 1, ows.max_row or 1, 1), _MAX_ROW)

                for row in range(1, max_row + 1):
                    for fy, col in fy_cols.items():
                        addr = f"{get_column_letter(col)}{row}"
                        if sheet == "Inputs" and addr in _CURRENT_DATA_CELLS:
                            entries.append(
                                ContinuityEntry(
                                    sheet=sheet,
                                    cell=addr,
                                    action=ContinuityAction.NEW_FY_REFRESH,
                                    reason="Current-data cell — refresh from live/CRF, do not carry stale market values.",
                                    previous_type=_cell_kind(pws[addr].value),
                                    template_type=_cell_kind(ows[addr].value),
                                )
                            )
                            continue

                        if fy == detected_new:
                            entries.append(
                                ContinuityEntry(
                                    sheet=sheet,
                                    cell=addr,
                                    fiscal_year=fy,
                                    action=ContinuityAction.NEW_FY_REFRESH,
                                    reason="Newly added fiscal year — not carried from previous workbook.",
                                    previous_type=_cell_kind(pws.cell(row, prev_cols.get(fy, col)).value),
                                    template_type=_cell_kind(ows[addr].value),
                                )
                            )
                            continue

                        prev_col = prev_cols.get(fy) or previous_fy_cols.get(fy)
                        if prev_col is None:
                            continue
                        prev_cell = pws.cell(row, prev_col)
                        out_cell = ows.cell(row, col)
                        entry = self._reconcile(
                            sheet=sheet,
                            addr=addr,
                            fy=fy,
                            prev_cell=prev_cell,
                            out_cell=out_cell,
                            formula_guard=formula_guard,
                            new_fiscal_year=detected_new,
                            prev_col=prev_col,
                            out_col=col,
                            pws=pws,
                            fy_cols=fy_cols,
                            row=row,
                            workbook=out,
                        )
                        if entry is not None:
                            entries.append(entry)

                    helper_entries = self._copy_same_address_helpers(
                        sheet=sheet,
                        row=row,
                        pws=pws,
                        ows=ows,
                        fy_cols=fy_cols,
                        detected_new=detected_new,
                        formula_guard=formula_guard,
                        workbook=out,
                    )
                    entries.extend(helper_entries)

            out.save(workbook_path)
        finally:
            prev.close()
            out.close()

        counts: dict[str, int] = {}
        for e in entries:
            counts[e.action.value] = counts.get(e.action.value, 0) + 1
        return AnnualModelContinuityReport(
            analysis_id=analysis_id,
            ticker=ticker,
            phase="apply",
            new_fiscal_year=detected_new,
            entries=[e for e in entries if e.action != ContinuityAction.MATCH_ALREADY][:8000],
            action_counts=counts,
            summary=(
                f"Continuity apply: new_fy={detected_new}; overlap={len(period_alignment.overlap_years)}; "
                + ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
            ),
        )

    def verify_final(
        self,
        *,
        analysis_id: str,
        ticker: str,
        previous_workbook_path: Path,
        workbook_path: Path,
        new_fiscal_year: str | None = None,
    ) -> AnnualModelContinuityReport:
        """Sparse final snapshot: unauthorized historical mismatches only."""
        prev = load_workbook(previous_workbook_path, data_only=False)
        out = load_workbook(workbook_path, data_only=False)
        mismatches: list[ContinuityEntry] = []
        try:
            year_map = {}
            for sheet in _HISTORICAL_SHEETS:
                if sheet in out.sheetnames:
                    year_map = detect_year_columns(out[sheet], out)
                    if any(k.startswith("FY") for k in year_map):
                        break
            fy_keys = [k for k in year_map if k.startswith("FY")]
            detected_new = new_fiscal_year or (max(fy_keys) if fy_keys else None)

            for sheet in _HISTORICAL_SHEETS:
                if sheet not in prev.sheetnames or sheet not in out.sheetnames:
                    continue
                pws, ows = prev[sheet], out[sheet]
                cols = detect_year_columns(ows, out)
                prev_cols = detect_year_columns(pws, prev)
                fy_cols = {fy: col for fy, col in cols.items() if fy.startswith("FY")}
                max_row = min(max(pws.max_row or 1, 1), _MAX_ROW)
                for row in range(1, max_row + 1):
                    for fy, col in fy_cols.items():
                        if fy == detected_new:
                            continue
                        addr = f"{get_column_letter(col)}{row}"
                        if sheet == "Inputs" and addr in _CURRENT_DATA_CELLS:
                            continue
                        prev_col = prev_cols.get(fy, col)
                        pv, ov = pws.cell(row, prev_col).value, ows.cell(row, col).value
                        pk, ok = _cell_kind(pv), _cell_kind(ov)
                        if pk == "blank" and ok == "blank":
                            continue
                        if pk == "formula" and ok == "formula":
                            continue
                        if pk == "formula" and ok != "formula":
                            mismatches.append(
                                ContinuityEntry(
                                    sheet=sheet,
                                    cell=addr,
                                    fiscal_year=fy,
                                    action=ContinuityAction.REVIEW_REQUIRED,
                                    reason="Historical formula flattened in final workbook.",
                                    previous_type=pk,
                                    final_type=ok,
                                )
                            )
                        elif pk == "value" and ok == "value" and not _values_equal(pv, ov):
                            mismatches.append(
                                ContinuityEntry(
                                    sheet=sheet,
                                    cell=addr,
                                    fiscal_year=fy,
                                    action=ContinuityAction.REVIEW_REQUIRED,
                                    reason="Historical value differs from previous workbook without restatement action.",
                                    previous_value=pv,
                                    final_value=ov,
                                    previous_type=pk,
                                    final_type=ok,
                                )
                            )
        finally:
            prev.close()
            out.close()

        status = "ok" if not mismatches else "REVIEW_REQUIRED"
        return AnnualModelContinuityReport(
            analysis_id=analysis_id,
            ticker=ticker,
            phase="final",
            new_fiscal_year=detected_new,
            entries=mismatches[:200],
            unauthorized_historical_rewrites=len(mismatches),
            status=status,
            summary=f"Final continuity: unauthorized_historical_diffs={len(mismatches)}.",
        )

    def _reconcile(
        self,
        *,
        sheet,
        addr,
        fy,
        prev_cell,
        out_cell,
        formula_guard,
        new_fiscal_year: str | None = None,
        prev_col: int | None = None,
        out_col: int | None = None,
        pws=None,
        fy_cols: dict[str, int] | None = None,
        row: int | None = None,
        workbook=None,
    ) -> ContinuityEntry | None:
        if new_fiscal_year and fy == new_fiscal_year:
            return None
        pv, ov = prev_cell.value, out_cell.value
        pk, ok = _cell_kind(pv), _cell_kind(ov)
        if pk == "blank" and ok == "blank":
            return None

        if formula_guard:
            if ok == "formula":
                return ContinuityEntry(
                    sheet=sheet,
                    cell=addr,
                    fiscal_year=fy,
                    action=ContinuityAction.KEEP_NEW_FORMULA,
                    reason="Formula-driven output sheet — formulas left intact.",
                    previous_type=pk,
                    template_type=ok,
                    final_type=ok,
                )
            return ContinuityEntry(
                sheet=sheet,
                cell=addr,
                fiscal_year=fy,
                action=ContinuityAction.BLOCKED,
                reason="Blocked write on formula-driven Ratios/Final Metrics cell.",
                previous_type=pk,
                template_type=ok,
            )

        action = ContinuityAction.MATCH_ALREADY
        reason = "Already aligned."
        fmt = False
        changed = False
        blocked_cycle = False

        if pk == "formula":
            relocatable = prev_col is not None and formula_references_column(
                str(formula_text(pv) or pv), prev_col
            )
            if not relocatable:
                # Helper formula occupying an FY column — do not relocate by year match.
                action = ContinuityAction.KEEP_NEW_FORMULA
                reason = (
                    "Non-year-series helper formula not relocated by FY alignment; "
                    "same-address helper copy handles fixed-layout formulas."
                )
            else:
                shifted = shift_formula_columns(str(formula_text(pv) or pv), prev_col, out_col or prev_col)
                if self._formula_write_unsafe(
                    workbook, sheet, addr, shifted, dest_col=out_col or prev_col, dest_row=row or 0
                ):
                    action = ContinuityAction.BLOCKED
                    reason = "Proposed FY-aligned formula write would create a circular reference; write rejected."
                    blocked_cycle = True
                elif ok != "formula":
                    out_cell.value = shifted
                    action = ContinuityAction.RESTORE_FORMULA
                    reason = "Previous year-series formula carried with column alignment."
                    changed = True
                else:
                    prev_f, out_f = _formula_text(pv), _formula_text(ov)
                    if shift_formula_columns(prev_f or "", prev_col, out_col or prev_col) == out_f:
                        action = ContinuityAction.MATCH_ALREADY
                        reason = "Historical year-series formula already aligned."
                    else:
                        action = ContinuityAction.KEEP_NEW_FORMULA
                        reason = "New-template formula retained (deliberate template update)."
        elif pk == "value" and ok == "formula":
            if pws is not None and fy_cols and row is not None and self._row_is_mixed_override(
                pws, row, fy_cols
            ):
                out_cell.value = pv
                action = ContinuityAction.CARRY_FORWARD_VALUE
                reason = "Analyst override on a hybrid formula/constant row carried from previous workbook."
                changed = True
            else:
                action = ContinuityAction.KEEP_NEW_FORMULA
                reason = "Template formula preserved; not flattened to prior cached value."
        elif pk == "value" and (ok == "blank" or (ok == "value" and not _values_equal(pv, ov))):
            out_cell.value = pv
            action = ContinuityAction.CARRY_FORWARD_VALUE
            reason = "Analyst-entered historical value carried from previous workbook."
            changed = True

        if not blocked_cycle:
            fmt = _copy_style(prev_cell, out_cell)
        if fmt and not changed and action == ContinuityAction.MATCH_ALREADY:
            action = ContinuityAction.CARRY_FORWARD_FORMAT
            reason = "Historical formatting copied from previous workbook."

        if action == ContinuityAction.MATCH_ALREADY and not fmt and not changed:
            return None

        return ContinuityEntry(
            sheet=sheet,
            cell=addr,
            fiscal_year=fy,
            previous_value="(formula)" if pk == "formula" else pv,
            previous_type=pk,
            template_value="(formula)" if ok == "formula" else ov,
            template_type=ok,
            final_value="(formula)" if _cell_kind(out_cell.value) == "formula" else out_cell.value,
            final_type=_cell_kind(out_cell.value),
            action=action,
            reason=reason,
            formatting_copied=fmt,
        )

    def _copy_same_address_helpers(
        self,
        *,
        sheet: str,
        row: int,
        pws,
        ows,
        fy_cols: dict[str, int],
        detected_new: str | None,
        formula_guard: bool,
        workbook,
    ) -> list[ContinuityEntry]:
        """Copy fixed-layout helper formulas/values by address (not FY relocation)."""
        if formula_guard:
            return []
        entries: list[ContinuityEntry] = []
        fy_col_set = set(fy_cols.values())
        new_col = fy_cols.get(detected_new) if detected_new else None
        max_col = min(max(pws.max_column or 1, ows.max_column or 1, 1), _MAX_COL)
        for col in range(1, max_col + 1):
            addr = f"{get_column_letter(col)}{row}"
            if sheet == "Inputs" and addr in _CURRENT_DATA_CELLS:
                continue
            if new_col and col == new_col and col in fy_col_set:
                continue
            prev_cell = pws.cell(row, col)
            out_cell = ows.cell(row, col)
            pv, ov = prev_cell.value, out_cell.value
            pk, ok = _cell_kind(pv), _cell_kind(ov)
            if pk == "blank":
                continue
            if pk == "formula":
                text = formula_text(pv) or str(pv)
                if col in fy_col_set and formula_references_column(text, col):
                    continue  # year-series handled by FY match
                if ok == "formula":
                    continue
                if self._formula_write_unsafe(
                    workbook, sheet, addr, text, dest_col=col, dest_row=row
                ):
                    entries.append(
                        ContinuityEntry(
                            sheet=sheet,
                            cell=addr,
                            action=ContinuityAction.BLOCKED,
                            reason="Same-address helper formula would create a circular reference; write rejected.",
                            previous_type=pk,
                            template_type=ok,
                        )
                    )
                    continue
                out_cell.value = pv
                _copy_style(prev_cell, out_cell)
                entries.append(
                    ContinuityEntry(
                        sheet=sheet,
                        cell=addr,
                        action=ContinuityAction.RESTORE_FORMULA,
                        reason="Fixed-layout helper formula copied by address from previous workbook.",
                        previous_type=pk,
                        template_type=ok,
                        final_type="formula",
                        formatting_copied=True,
                    )
                )
            elif pk == "value" and ok == "blank":
                out_cell.value = pv
                _copy_style(prev_cell, out_cell)
                entries.append(
                    ContinuityEntry(
                        sheet=sheet,
                        cell=addr,
                        action=ContinuityAction.CARRY_FORWARD_VALUE,
                        reason="Fixed-layout helper value copied by address from previous workbook.",
                        previous_type=pk,
                        template_type=ok,
                        final_type="value",
                    )
                )
        return entries

    @staticmethod
    def _row_is_mixed_override(pws, row: int, fy_cols: dict[str, int]) -> bool:
        kinds: set[str] = set()
        for col in fy_cols.values():
            kinds.add(_cell_kind(pws.cell(row, col).value))
        return "formula" in kinds and "value" in kinds

    @staticmethod
    def _formula_write_unsafe(workbook, sheet: str, addr: str, formula: str, *, dest_col: int, dest_row: int) -> bool:
        if formula_would_self_reference(formula, dest_col, dest_row, sheet=sheet):
            return True
        if workbook is None:
            return False
        try:
            cycle = CircularReferenceService().write_would_create_cycle(
                workbook, sheet=sheet, cell=addr, formula=formula
            )
        except Exception:  # noqa: BLE001
            return formula_would_self_reference(formula, dest_col, dest_row, sheet=sheet)
        return cycle is not None

    @staticmethod
    def _workbook_fy_columns(wb) -> dict[str, int]:
        for sheet in (
            "Balance Sheet - Standardized",
            "Income - GAAP",
            "Cash Flow - Standardized",
            "Inputs",
        ):
            if sheet not in wb.sheetnames:
                continue
            cols = detect_year_columns(wb[sheet], wb)
            fy_cols = {fy: col for fy, col in cols.items() if fy.startswith("FY")}
            if fy_cols:
                return fy_cols
        return {}
