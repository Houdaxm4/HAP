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


def _label_column(ws, max_row: int = 150) -> list[tuple[int, str]]:
    """(row, label) of every labelled row of a tab, from column A (statement tabs also carry a field code in column B)."""
    out: list[tuple[int, str]] = []
    for row in range(1, max_row + 1):
        label = ws.cell(row, 1).value
        if isinstance(label, str) and label.strip() and not label.startswith("="):
            code = ws.cell(row, 2).value
            out.append((row, label.strip() + ("|" + code if isinstance(code, str) and not code.startswith("=") else "")))
    return out


def layout_matches(prev_ws, tmpl_ws, max_row: int = 150) -> bool:
    """True when the previous workbook's tab has the same rows as the new template's tab.

    A previous workbook built on an older template version has statement rows that moved (for example an inserted
    'Unbilled Revenues' row). Copying its cells by address into the new template then puts values and formulas on
    the wrong rows, so such tabs must not be copied cell by cell."""
    if tmpl_ws is None:
        return True
    return [lab for _r, lab in _label_column(prev_ws, max_row)] == [lab for _r, lab in _label_column(tmpl_ws, max_row)]


def carry_constants_by_label(prev_ws, out_ws, max_row: int = 150, max_col: int = 20) -> int:
    """Layout differs: carry only the previous workbook's numeric analyst constants, matched by row label (not by row number)."""
    wanted: dict[str, list[int]] = {}
    for row, lab in _label_column(out_ws, max_row):
        wanted.setdefault(lab, []).append(row)
    seen: dict[str, int] = {}
    carried = 0
    for row, lab in _label_column(prev_ws, max_row):
        k = seen.get(lab, 0)
        seen[lab] = k + 1
        if lab not in wanted or k >= len(wanted[lab]):
            continue
        dest_row = wanted[lab][k]
        for col in range(3, max_col + 1):
            v = prev_ws.cell(row, col).value
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            dest = out_ws.cell(dest_row, col)
            if _cell_type(dest.value) in ("blank", "value") and dest.value != v:
                dest.value = v
                carried += 1
    return carried


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

    def align_prior_quarter_balance_sheet(
        self,
        *,
        previous_workbook_path: Path,
        workbook_path: Path,
        sheet: str = "Last Quarter BS Standardized",
        min_gap_days: int = 60,
        max_gap_days: int = 125,
    ) -> dict[str, Any]:
        """Make column D of the Last Quarter balance sheet the quarter before column C.

        A template pulled after the period ended can hold a later quarter in column D (for example FQ2 2026 beside FQ1 2025),
        which turns every quarter-over-quarter comparison into nonsense. When the previous workbook's latest quarter is the
        quarter right before this one (60-125 days earlier), its column C is copied into column D by Bloomberg field code.
        Otherwise column D is left as it is and the report says why."""
        prev_wb = load_workbook(previous_workbook_path, data_only=True)
        out_wb = load_workbook(workbook_path, data_only=False)
        try:
            if sheet not in prev_wb.sheetnames or sheet not in out_wb.sheetnames:
                return {"status": "skipped", "reason": f"no {sheet} tab"}
            prev_ws, out_ws = prev_wb[sheet], out_wb[sheet]
            cur_date, d_date, prev_date = out_ws["C4"].value, out_ws["D4"].value, prev_ws["C4"].value
            if not all(hasattr(x, "toordinal") for x in (cur_date, d_date, prev_date)):
                return {"status": "skipped", "reason": "quarter-end dates not readable"}
            if d_date == prev_date:
                return {"status": "ok", "reason": "column D already holds the previous quarter", "copied": 0}
            gap = (cur_date - prev_date).days
            if not (min_gap_days <= gap <= max_gap_days):
                if not (min_gap_days <= (cur_date - d_date).days <= max_gap_days):
                    # column D is not the prior quarter either: clear it so no comparison is made against the wrong quarter
                    for r in range(10, (out_ws.max_row or 1) + 1):
                        code, dest = out_ws.cell(r, 2).value, out_ws.cell(r, 4)
                        if isinstance(code, str) and not code.startswith("=") and _cell_type(dest.value) == "value":
                            dest.value = None
                    out_wb.save(workbook_path)
                    return {
                        "status": "not_aligned",
                        "reason": (f"previous workbook's latest quarter ended {prev_date:%Y-%m-%d}, {gap} days before this quarter, so it is not "
                                   f"the prior quarter; column D held {d_date:%Y-%m-%d} and was cleared (no quarter-over-quarter balance sheet comparison)"),
                        "copied": 0,
                    }
                return {
                    "status": "not_aligned",
                    "reason": (f"previous workbook's latest quarter ended {prev_date:%Y-%m-%d}, {gap} days before this quarter: "
                               f"not the prior quarter; column D keeps {d_date:%Y-%m-%d}"),
                    "copied": 0,
                }
            prev_rows = {}
            for r in range(5, (prev_ws.max_row or 1) + 1):
                code, v = prev_ws.cell(r, 2).value, prev_ws.cell(r, 3).value
                if isinstance(code, str) and code and not code.startswith("=") and isinstance(v, (int, float)) and not isinstance(v, bool):
                    prev_rows.setdefault(code, v)
            copied = 0
            seen: set[str] = set()
            for r in range(10, (out_ws.max_row or 1) + 1):
                code = out_ws.cell(r, 2).value
                if not isinstance(code, str) or code.startswith("=") or code in seen:
                    continue
                seen.add(code)
                dest = out_ws.cell(r, 4)
                if _cell_type(dest.value) == "formula":
                    continue
                if code in prev_rows:
                    dest.value = prev_rows[code]
                    copied += 1
                elif dest.value is not None:
                    dest.value = None
            out_ws["D4"].value = prev_date
            if isinstance(prev_ws["C5"].value, str):
                out_ws["D5"].value = prev_ws["C5"].value
            out_wb.save(workbook_path)
            return {"status": "ok", "reason": f"column D set to the previous quarter ({prev_date:%Y-%m-%d}) from the previous workbook", "copied": copied}
        finally:
            prev_wb.close()
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
                if not layout_matches(prev_ws, tmpl_ws):
                    # previous workbook built on another template version: keep this tab as the new template has it
                    carried = carry_constants_by_label(prev_ws, out_ws)
                    entries.append(
                        ModelContinuityEntry(
                            sheet=sheet,
                            cell="*",
                            previous_type="n/a",
                            current_template_type="n/a",
                            final_type="n/a",
                            final_action=CarryForwardDecision.KEEP_NEW_FORMULA,
                            reason=(
                                "Row layout differs from the previous workbook (older template version): tab kept as in the new "
                                f"template; {carried} numeric analyst constants carried by row label."
                            ),
                        )
                    )
                    continue
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
