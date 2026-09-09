"""Reconcile persistent analyst/model tabs against the previous completed workbook."""

from __future__ import annotations

from copy import copy
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.quarterly_update import (
    CarryForwardDecision,
    ModelContinuityEntry,
    QuarterlyModelContinuityApplyReport,
    QuarterlyModelContinuityReport,
)
from workbook_mapping.sheet_policies import (
    IGNORED_TEMPLATE_SHEETS,
    LQ_STANDARDIZED_SHEETS,
)

# Persistent tabs reconciled for model continuity (not quarter-refresh regions).
_PERSISTENT_SHEETS = (
    "Inputs",
    "Leases",
    "R&D",
    "Tax",
    "IC & NOPAT & ROIC ",
    "Income - GAAP",
    "Balance Sheet - Standardized",
    "Cash Flow - Standardized",
    "All Ratios",
    "Final Metrics",
    "Expected Returns & Buybacks",
    "Enterprise Value",
    "BS%",
    "IS%",
    "CF%",
    "FCF",
)

_INPUTS_REFRESH = {f"B{r}" for r in range(63, 76)}
# Q2/Q3 projection columns written later — do not carry from prior workbook.
_IC_PROJECTION_COLS = {13, 14}  # M, N


def _cell_type(value: Any) -> str:
    if value is None or value == "":
        return "blank"
    if isinstance(value, str) and value.startswith("="):
        return "formula"
    if hasattr(value, "text"):
        return "formula"
    return "value"


def _formula_text(value: Any) -> str | None:
    if isinstance(value, str) and value.startswith("="):
        return value
    if hasattr(value, "text"):
        return str(value.text)
    return None


def _cell_values_equal(a: Any, b: Any) -> bool:
    """Compare cell values including openpyxl ArrayFormula objects by text/ref."""
    fa, fb = _formula_text(a), _formula_text(b)
    if fa is not None or fb is not None:
        if fa is None or fb is None:
            return False
        return fa == fb
    return a == b


def _style_sig(cell) -> str | None:
    if not cell.has_style:
        return None
    parts = [
        str(cell.font.color) if cell.font and cell.font.color else "",
        str(cell.fill.fgColor) if cell.fill and cell.fill.fgColor else "",
        cell.number_format or "",
    ]
    return "|".join(parts)


def _copy_style(src, dst) -> bool:
    if not src.has_style:
        return False
    dst.font = copy(src.font)
    dst.border = copy(src.border)
    dst.fill = copy(src.fill)
    dst.number_format = copy(src.number_format)
    dst.protection = copy(src.protection)
    dst.alignment = copy(src.alignment)
    return True


class QuarterlyModelContinuityService:
    """Carry formulas, values, and formatting for persistent tabs; verify ignored sheets."""

    def restore_ignored_sheets(
        self,
        *,
        new_template_path: Path,
        workbook_path: Path,
    ) -> list[str]:
        """Reset ignored template sheets to byte/logical match with current template."""
        template_wb = load_workbook(new_template_path, data_only=False)
        out_wb = load_workbook(workbook_path, data_only=False)
        restored: list[str] = []
        try:
            for sheet in IGNORED_TEMPLATE_SHEETS:
                if sheet not in template_wb.sheetnames or sheet not in out_wb.sheetnames:
                    continue
                t_ws = template_wb[sheet]
                o_ws = out_wb[sheet]
                max_row = max(t_ws.max_row or 1, 1)
                max_col = max(t_ws.max_column or 1, 1)
                for row in range(1, min(max_row, 200) + 1):
                    for col in range(1, min(max_col, 30) + 1):
                        addr = f"{get_column_letter(col)}{row}"
                        tc, oc = t_ws[addr], o_ws[addr]
                        if not _cell_values_equal(tc.value, oc.value) or _style_sig(tc) != _style_sig(oc):
                            oc.value = tc.value
                            _copy_style(tc, oc)
                restored.append(sheet)
            out_wb.save(workbook_path)
            return restored
        finally:
            template_wb.close()
            out_wb.close()

    def apply_persistent_continuity(
        self,
        *,
        analysis_id: str,
        ticker: str,
        new_template_path: Path,
        previous_workbook_path: Path,
        workbook_path: Path,
    ) -> QuarterlyModelContinuityApplyReport:
        """Early reconciliation of persistent tabs (pre-fill). Skips ignored-sheet verify."""
        template_wb = load_workbook(new_template_path, data_only=False)
        prev_wb = load_workbook(previous_workbook_path, data_only=False)
        out_wb = load_workbook(workbook_path, data_only=False)
        entries: list[ModelContinuityEntry] = []

        try:
            for sheet in _PERSISTENT_SHEETS:
                if sheet not in prev_wb.sheetnames or sheet not in out_wb.sheetnames:
                    continue
                prev_ws = prev_wb[sheet]
                out_ws = out_wb[sheet]
                tmpl_ws = template_wb[sheet] if sheet in template_wb.sheetnames else None
                max_row = min(prev_ws.max_row or 1, 150)
                max_col = min(prev_ws.max_column or 1, 20)
                for row in range(1, max_row + 1):
                    for col in range(1, max_col + 1):
                        addr = f"{get_column_letter(col)}{row}"
                        if sheet == "Inputs" and addr in _INPUTS_REFRESH:
                            continue
                        if sheet == "IC & NOPAT & ROIC " and col in _IC_PROJECTION_COLS:
                            continue
                        entry = self._reconcile_cell(
                            sheet=sheet,
                            addr=addr,
                            prev_cell=prev_ws[addr],
                            out_cell=out_ws[addr],
                            tmpl_cell=tmpl_ws[addr] if tmpl_ws is not None else None,
                        )
                        if entry is not None:
                            entries.append(entry)

            out_wb.save(workbook_path)
            carry_n = sum(
                1 for e in entries if e.final_action == CarryForwardDecision.CARRY_FORWARD
            )
            restore_n = sum(
                1 for e in entries if e.final_action == CarryForwardDecision.RESTORE_FORMULA
            )
            fmt_n = sum(
                1 for e in entries if e.final_action == CarryForwardDecision.CARRY_FORWARD_FORMAT
            )
            return QuarterlyModelContinuityApplyReport(
                analysis_id=analysis_id,
                ticker=ticker,
                entries=entries,
                carry_forward_count=carry_n,
                restore_formula_count=restore_n,
                format_count=fmt_n,
                summary=(
                    f"Apply-phase continuity: {carry_n} values, {restore_n} formulas restored, "
                    f"{fmt_n} formats copied (pre-fill)."
                ),
            )
        finally:
            template_wb.close()
            prev_wb.close()
            out_wb.close()

    def verify_final_deliverable(
        self,
        *,
        analysis_id: str,
        ticker: str,
        new_template_path: Path,
        workbook_path: Path,
    ) -> QuarterlyModelContinuityReport:
        """Final verification vs current template after all workbook operations."""
        # Ensure ignored sheets match template immediately before verify.
        self.restore_ignored_sheets(
            new_template_path=new_template_path,
            workbook_path=workbook_path,
        )
        template_wb = load_workbook(new_template_path, data_only=False)
        out_wb = load_workbook(workbook_path, data_only=False)
        entries: list[ModelContinuityEntry] = []

        try:
            ignored_ok, mismatches = self._verify_ignored_sheets(template_wb, out_wb)
            for sheet in sorted(IGNORED_TEMPLATE_SHEETS):
                if sheet not in template_wb.sheetnames or sheet not in out_wb.sheetnames:
                    continue
                entries.append(
                    ModelContinuityEntry(
                        sheet=sheet,
                        cell="*",
                        previous_type="n/a",
                        current_template_type="n/a",
                        final_type="n/a",
                        final_action=(
                            CarryForwardDecision.IGNORE_TEMPLATE_PRESERVE
                            if sheet in ignored_ok
                            else CarryForwardDecision.REVIEW_REQUIRED
                        ),
                        reason=(
                            "Final deliverable matches current template."
                            if sheet in ignored_ok
                            else "Final deliverable differs from template on ignored sheet."
                        ),
                    )
                )

            status = "ok" if not mismatches else "REVIEW_REQUIRED"
            return QuarterlyModelContinuityReport(
                analysis_id=analysis_id,
                ticker=ticker,
                phase="final",
                entries=entries,
                ignored_sheets_verified=ignored_ok,
                ignored_sheet_mismatches=mismatches,
                status=status,
                summary=(
                    f"Final continuity: ignored verified={len(ignored_ok)}, "
                    f"mismatches={len(mismatches)}."
                ),
            )
        finally:
            template_wb.close()
            out_wb.close()

    def reconcile(
        self,
        *,
        analysis_id: str,
        ticker: str,
        new_template_path: Path,
        previous_workbook_path: Path,
        workbook_path: Path,
    ) -> QuarterlyModelContinuityReport:
        """Backward-compatible alias for apply phase."""
        apply_rep = self.apply_persistent_continuity(
            analysis_id=analysis_id,
            ticker=ticker,
            new_template_path=new_template_path,
            previous_workbook_path=previous_workbook_path,
            workbook_path=workbook_path,
        )
        return QuarterlyModelContinuityReport(
            analysis_id=analysis_id,
            ticker=ticker,
            phase="apply",
            entries=apply_rep.entries,
            summary=apply_rep.summary,
        )

    def _verify_ignored_sheets(self, template_wb, out_wb) -> tuple[list[str], list[str]]:
        ok: list[str] = []
        bad: list[str] = []
        for sheet in IGNORED_TEMPLATE_SHEETS:
            if sheet not in template_wb.sheetnames or sheet not in out_wb.sheetnames:
                continue
            t_ws = template_wb[sheet]
            o_ws = out_wb[sheet]
            mismatch = False
            max_row = max(t_ws.max_row or 1, 1)
            max_col = max(t_ws.max_column or 1, 1)
            for row in range(1, min(max_row, 200) + 1):
                for col in range(1, min(max_col, 30) + 1):
                    addr = f"{get_column_letter(col)}{row}"
                    tc, oc = t_ws[addr], o_ws[addr]
                    if not _cell_values_equal(tc.value, oc.value):
                        bad.append(f"{sheet}!{addr}: value differs from template")
                        mismatch = True
                        break
                    # Style compare only when values match — ignore default/no-fill noise
                    ts, os_ = _style_sig(tc), _style_sig(oc)
                    if ts != os_ and (ts or os_):
                        bad.append(f"{sheet}!{addr}: style differs from template")
                        mismatch = True
                        break
                if mismatch:
                    break
            if not mismatch:
                ok.append(sheet)
        return ok, bad

    def _reconcile_cell(self, *, sheet, addr, prev_cell, out_cell, tmpl_cell) -> ModelContinuityEntry | None:
        prev_v = prev_cell.value
        out_v = out_cell.value
        tmpl_v = tmpl_cell.value if tmpl_cell is not None else None
        prev_t = _cell_type(prev_v)
        out_t = _cell_type(out_v)
        tmpl_t = _cell_type(tmpl_v)

        # Skip entirely blank quadruplets
        if prev_t == "blank" and out_t == "blank" and tmpl_t == "blank":
            return None

        action = CarryForwardDecision.MATCH_ALREADY
        reason = "Already aligned."
        changed = False

        if prev_t == "formula" and out_t in ("blank", "value"):
            out_cell.value = prev_v
            out_t = "formula"
            action = CarryForwardDecision.RESTORE_FORMULA
            reason = "Previous workbook formula restored on persistent tab."
            changed = True
        elif prev_t == "value" and out_t == "blank":
            out_cell.value = prev_v
            out_t = "value"
            action = CarryForwardDecision.CARRY_FORWARD
            reason = "Analyst-entered value carried from previous workbook."
            changed = True
        elif prev_t == "value" and out_t == "value" and prev_v != out_v:
            out_cell.value = prev_v
            action = CarryForwardDecision.CARRY_FORWARD
            reason = "Replaced with previous analyst value for model continuity."
            changed = True
        elif prev_v == out_v and prev_t == out_t:
            action = CarryForwardDecision.MATCH_ALREADY
        elif out_t == "formula":
            action = CarryForwardDecision.KEEP_NEW_FORMULA
            reason = "New-template formula preserved."

        fmt_changed = _copy_style(prev_cell, out_cell)
        if fmt_changed and not changed:
            action = CarryForwardDecision.CARRY_FORWARD_FORMAT
            reason = "Formatting copied from previous workbook."

        if not changed and not fmt_changed and action == CarryForwardDecision.MATCH_ALREADY:
            if prev_t == "blank" and out_t != "blank":
                return None
            if prev_v == out_v and _style_sig(prev_cell) == _style_sig(out_cell):
                return None

        return ModelContinuityEntry(
            sheet=sheet,
            cell=addr,
            previous_value="(formula)" if prev_t == "formula" else prev_v,
            previous_type=prev_t,
            current_template_value="(formula)" if tmpl_t == "formula" else tmpl_v,
            current_template_type=tmpl_t,
            final_value="(formula)" if out_t == "formula" else out_cell.value,
            final_type=_cell_type(out_cell.value),
            previous_formula=_formula_text(prev_v),
            current_formula=_formula_text(tmpl_v),
            formatting_changed=fmt_changed,
            final_action=action,
            reason=reason,
        )
