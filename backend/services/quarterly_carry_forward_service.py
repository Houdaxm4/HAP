"""Carry analyst-maintained values from previous completed workbook into new quarter template.

Never converts new-template formulas into static values.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.quarterly_update import (
    CarryForwardDecision,
    CarryForwardEntry,
    QuarterlyCarryForwardReport,
)

# Persistent Inputs regions (values only). Current-data B63:B75 is refresh, not carry.
_INPUTS_CARRY_ROWS = {
    # PE10 / E10 / growth history
    *range(57, 62),
    # Lease unit flag + rental expense (manual when present)
    92,  # unit flag lives in E92 — handled specially
    93,
    # R&D previous-year manual row
    104,
    # Tax table
    *range(106, 113),
}
_INPUTS_CARRY_COLS = list(range(3, 13))  # C-L
_INPUTS_REFRESH_CELLS = {f"B{r}" for r in range(63, 76)}

# Sheet-level analyst constants (non-formula value cells)
_SHEET_VALUE_CELLS = {
    "R&D": ["B8"],  # R&D Life
    "Leases": [],  # B18:K18 handled as mixed formula/manual overrides
}

_LEASES_RATE_ROW = 18
_LEASES_RATE_COLS = list(range(2, 12))  # B-K
_INPUTS_REF_RE = re.compile(r"Inputs!\$?([A-Z]+)\$?(\d+)", re.I)


def _cell_type(value: Any) -> str:
    if value is None or value == "":
        return "blank"
    if isinstance(value, str) and value.startswith("="):
        return "formula"
    return "value"


def _is_formula(value: Any) -> bool:
    return isinstance(value, str) and value.startswith("=")


class QuarterlyCarryForwardService:
    """Copy persistent analyst values from previous completed workbook."""

    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        new_template_path: Path,
        previous_workbook_path: Path | None,
        destination_path: Path,
    ) -> QuarterlyCarryForwardReport:
        if previous_workbook_path is None or not Path(previous_workbook_path).exists():
            return QuarterlyCarryForwardReport(
                analysis_id=analysis_id,
                ticker=ticker,
                previous_workbook=str(previous_workbook_path) if previous_workbook_path else None,
                new_template=str(new_template_path),
                status="MISSING_PREVIOUS_WORKBOOK",
                summary="MISSING_PREVIOUS_WORKBOOK: quarterly_update requires a previous completed workbook.",
            )

        prev_path = Path(previous_workbook_path)
        new_path = Path(new_template_path)
        dest = Path(destination_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(new_path, dest)

        prev_wb = load_workbook(prev_path, data_only=False)
        new_wb = load_workbook(dest, data_only=False)
        entries: list[CarryForwardEntry] = []

        # --- Inputs carry / refresh classification ---
        if "Inputs" in prev_wb.sheetnames and "Inputs" in new_wb.sheetnames:
            prev_inp = prev_wb["Inputs"]
            new_inp = new_wb["Inputs"]
            # Current-data refresh markers (do not carry stale price)
            for addr in sorted(_INPUTS_REFRESH_CELLS):
                entries.append(
                    CarryForwardEntry(
                        sheet="Inputs",
                        cell=addr,
                        previous_value=prev_inp[addr].value,
                        previous_type=_cell_type(prev_inp[addr].value),
                        new_template_value=new_inp[addr].value,
                        new_template_type=_cell_type(new_inp[addr].value),
                        final_action=CarryForwardDecision.REFRESH_CURRENT_DATA,
                        reason="Current-data field — refresh from CRF/live market, do not carry stale price.",
                        source_workbook=str(prev_path),
                    )
                )
            # E92 / E106 unit flags
            for addr in ("E92", "E106"):
                entries.extend(
                    self._maybe_carry(
                        sheet="Inputs",
                        addr=addr,
                        prev_cell=prev_inp[addr],
                        new_cell=new_inp[addr],
                        source=str(prev_path),
                    )
                )
            for row in _INPUTS_CARRY_ROWS:
                if row in {92, 106}:
                    continue  # flags handled above
                for col in _INPUTS_CARRY_COLS:
                    addr = f"{get_column_letter(col)}{row}"
                    if addr in _INPUTS_REFRESH_CELLS:
                        continue
                    entries.extend(
                        self._maybe_carry(
                            sheet="Inputs",
                            addr=addr,
                            prev_cell=prev_inp[addr],
                            new_cell=new_inp[addr],
                            source=str(prev_path),
                        )
                    )

        # --- Leases!B18:K18 Estimated Long-Term Rate (mixed formula / analyst override) ---
        if "Leases" in prev_wb.sheetnames and "Leases" in new_wb.sheetnames:
            prev_ls = prev_wb["Leases"]
            new_ls = new_wb["Leases"]
            for col in _LEASES_RATE_COLS:
                addr = f"{get_column_letter(col)}{_LEASES_RATE_ROW}"
                entries.extend(
                    self._maybe_carry_lease_rate(
                        addr=addr,
                        prev_cell=prev_ls[addr],
                        new_cell=new_ls[addr],
                        source=str(prev_path),
                    )
                )

        # --- R&D / Leases explicit + scanned value cells ---
        for sheet_name, addrs in _SHEET_VALUE_CELLS.items():
            if sheet_name not in prev_wb.sheetnames or sheet_name not in new_wb.sheetnames:
                continue
            prev_ws = prev_wb[sheet_name]
            new_ws = new_wb[sheet_name]
            for addr in addrs:
                entries.extend(
                    self._maybe_carry(
                        sheet=sheet_name,
                        addr=addr,
                        prev_cell=prev_ws[addr],
                        new_cell=new_ws[addr],
                        source=str(prev_path),
                    )
                )
            # Scan used range for additional non-formula numeric constants (labels in col A skipped)
            for row in prev_ws.iter_rows(min_row=1, max_row=min(prev_ws.max_row or 1, 80), max_col=12):
                for cell in row:
                    if cell.column == 1:
                        continue
                    addr = cell.coordinate
                    if any(e.sheet == sheet_name and e.cell == addr for e in entries):
                        continue
                    if _cell_type(cell.value) != "value":
                        continue
                    if not isinstance(cell.value, (int, float)):
                        continue
                    new_cell = new_ws[addr]
                    if sheet_name == "R&D":
                        entries.extend(
                            self._maybe_carry_rd(
                                addr=addr,
                                prev_cell=cell,
                                new_cell=new_cell,
                                new_inputs=new_wb["Inputs"] if "Inputs" in new_wb.sheetnames else None,
                                source=str(prev_path),
                            )
                        )
                    else:
                        entries.extend(
                            self._maybe_carry(
                                sheet=sheet_name,
                                addr=addr,
                                prev_cell=cell,
                                new_cell=new_cell,
                                source=str(prev_path),
                            )
                        )

        new_wb.save(dest)
        prev_wb.close()
        new_wb.close()

        carry_n = sum(1 for e in entries if e.final_action == CarryForwardDecision.CARRY_FORWARD)
        keep_n = sum(1 for e in entries if e.final_action == CarryForwardDecision.KEEP_NEW_FORMULA)
        refresh_n = sum(
            1 for e in entries if e.final_action == CarryForwardDecision.REFRESH_CURRENT_DATA
        )
        return QuarterlyCarryForwardReport(
            analysis_id=analysis_id,
            ticker=ticker,
            previous_workbook=str(prev_path),
            new_template=str(new_path),
            entries=entries,
            carry_forward_count=carry_n,
            keep_formula_count=keep_n,
            refresh_current_count=refresh_n,
            status="ok",
            summary=(
                f"Carry-forward complete: {carry_n} values copied, {keep_n} formulas preserved, "
                f"{refresh_n} current-data cells marked for refresh."
            ),
        )

    def _entry(
        self,
        *,
        sheet: str,
        addr: str,
        prev_v: Any,
        prev_t: str,
        new_v: Any,
        new_t: str,
        action: CarryForwardDecision,
        reason: str,
        source: str,
        final_cell=None,
    ) -> CarryForwardEntry:
        final_v = final_cell.value if final_cell is not None else new_v
        return CarryForwardEntry(
            sheet=sheet,
            cell=addr,
            previous_value=prev_v if prev_t != "formula" else "(formula)",
            previous_type=prev_t,
            new_template_value="(formula)" if new_t == "formula" else new_v,
            new_template_type=new_t,
            final_value="(formula)" if _is_formula(final_v) else final_v,
            final_type=_cell_type(final_v),
            final_action=action,
            reason=reason,
            source_workbook=source,
        )

    def _maybe_carry_lease_rate(self, *, addr: str, prev_cell, new_cell, source: str) -> list[CarryForwardEntry]:
        """B18:K18 — analyst numeric override wins; otherwise keep new formula."""
        prev_v, new_v = prev_cell.value, new_cell.value
        prev_t, new_t = _cell_type(prev_v), _cell_type(new_v)
        if prev_t == "value":
            new_cell.value = prev_v
            return [
                self._entry(
                    sheet="Leases",
                    addr=addr,
                    prev_v=prev_v,
                    prev_t=prev_t,
                    new_v=new_v,
                    new_t=new_t,
                    action=CarryForwardDecision.CARRY_FORWARD,
                    reason=(
                        "Previous completed workbook has a manual Estimated Long-Term Rate "
                        "override; carried forward (exception to formula preservation)."
                    ),
                    source=source,
                    final_cell=new_cell,
                )
            ]
        if new_t == "formula":
            return [
                self._entry(
                    sheet="Leases",
                    addr=addr,
                    prev_v=prev_v,
                    prev_t=prev_t,
                    new_v=new_v,
                    new_t=new_t,
                    action=CarryForwardDecision.KEEP_NEW_FORMULA,
                    reason="New template Estimated Long-Term Rate formula preserved.",
                    source=source,
                    final_cell=new_cell,
                )
            ]
        return self._maybe_carry(sheet="Leases", addr=addr, prev_cell=prev_cell, new_cell=new_cell, source=source)

    def _maybe_carry_rd(
        self, *, addr: str, prev_cell, new_cell, new_inputs, source: str
    ) -> list[CarryForwardEntry]:
        """R&D: keep new formulas; park previous analyst values in Inputs sinks when referenced."""
        prev_v, new_v = prev_cell.value, new_cell.value
        prev_t, new_t = _cell_type(prev_v), _cell_type(new_v)
        if new_t == "formula" and prev_t == "value":
            sink = None
            m = _INPUTS_REF_RE.search(str(new_v or ""))
            if m:
                sink = f"{m.group(1).upper()}{m.group(2)}"
            if sink and new_inputs is not None:
                sink_cell = new_inputs[sink]
                if _cell_type(sink_cell.value) != "formula" and (
                    sink_cell.value is None or sink_cell.value == ""
                ):
                    sink_cell.value = prev_v
                    return [
                        self._entry(
                            sheet="R&D",
                            addr=addr,
                            prev_v=prev_v,
                            prev_t=prev_t,
                            new_v=new_v,
                            new_t=new_t,
                            action=CarryForwardDecision.KEEP_NEW_FORMULA,
                            reason=(
                                f"R&D formula preserved; analyst value {prev_v} written to "
                                f"Inputs!{sink} so historical capitalization stays consistent."
                            ),
                            source=source,
                            final_cell=new_cell,
                        ),
                        self._entry(
                            sheet="Inputs",
                            addr=sink,
                            prev_v=prev_v,
                            prev_t="value",
                            new_v=None,
                            new_t="blank",
                            action=CarryForwardDecision.CARRY_FORWARD,
                            reason=f"R&D {addr} historical value redirected to Inputs!{sink}.",
                            source=source,
                            final_cell=sink_cell,
                        ),
                    ]
            return [
                self._entry(
                    sheet="R&D",
                    addr=addr,
                    prev_v=prev_v,
                    prev_t=prev_t,
                    new_v=new_v,
                    new_t=new_t,
                    action=CarryForwardDecision.KEEP_NEW_FORMULA,
                    reason="New R&D formula preserved — never overwrite with static value.",
                    source=source,
                    final_cell=new_cell,
                )
            ]
        return self._maybe_carry(sheet="R&D", addr=addr, prev_cell=prev_cell, new_cell=new_cell, source=source)

    def _maybe_carry(self, *, sheet: str, addr: str, prev_cell, new_cell, source: str) -> list[CarryForwardEntry]:
        prev_v = prev_cell.value
        new_v = new_cell.value
        prev_t = _cell_type(prev_v)
        new_t = _cell_type(new_v)

        if new_t == "formula":
            return [
                self._entry(
                    sheet=sheet,
                    addr=addr,
                    prev_v=prev_v,
                    prev_t=prev_t,
                    new_v=new_v,
                    new_t=new_t,
                    action=CarryForwardDecision.KEEP_NEW_FORMULA,
                    reason="New template formula preserved — never overwrite with value.",
                    source=source,
                    final_cell=new_cell,
                )
            ]

        if prev_t != "value":
            return [
                self._entry(
                    sheet=sheet,
                    addr=addr,
                    prev_v=prev_v,
                    prev_t=prev_t,
                    new_v=new_v,
                    new_t=new_t,
                    action=CarryForwardDecision.LEAVE_AS_IS,
                    reason="No previous analyst value to carry.",
                    source=source,
                    final_cell=new_cell,
                )
            ]

        if new_t == "blank" or new_v is None or new_v == "":
            new_cell.value = prev_v
            return [
                self._entry(
                    sheet=sheet,
                    addr=addr,
                    prev_v=prev_v,
                    prev_t=prev_t,
                    new_v=None,
                    new_t="blank",
                    action=CarryForwardDecision.CARRY_FORWARD,
                    reason="Analyst-entered historical value carried from previous completed workbook.",
                    source=source,
                    final_cell=new_cell,
                )
            ]

        if new_t == "value" and prev_v == new_v:
            return [
                self._entry(
                    sheet=sheet,
                    addr=addr,
                    prev_v=prev_v,
                    prev_t=prev_t,
                    new_v=new_v,
                    new_t=new_t,
                    action=CarryForwardDecision.LEAVE_AS_IS,
                    reason="New template already matches previous value.",
                    source=source,
                    final_cell=new_cell,
                )
            ]

        if new_t == "value" and prev_v != new_v:
            new_cell.value = prev_v
            return [
                self._entry(
                    sheet=sheet,
                    addr=addr,
                    prev_v=prev_v,
                    prev_t=prev_t,
                    new_v=new_v,
                    new_t=new_t,
                    action=CarryForwardDecision.CARRY_FORWARD,
                    reason="Replaced new-template seed value with previous completed analyst value.",
                    source=source,
                    final_cell=new_cell,
                )
            ]

        return [
            self._entry(
                sheet=sheet,
                addr=addr,
                prev_v=prev_v,
                prev_t=prev_t,
                new_v=new_v,
                new_t=new_t,
                action=CarryForwardDecision.REVIEW_REQUIRED,
                reason="Unhandled cell state for carry-forward.",
                source=source,
                final_cell=new_cell,
            )
        ]
