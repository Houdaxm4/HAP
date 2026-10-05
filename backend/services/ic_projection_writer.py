"""IC, NOPAT & ROIC tab: projected ROIC (column M) and ROCE (column N) for the current year, from the latest quarter.

The method is the house method (same formulas as the previous quarterly files), written as live Excel formulas:

Invested capital (M3:M7)
  Operating assets and liabilities = the same Balance Sheet lines the annual column uses (the Inputs formulas, including any adjusted
  lines), taken from the Last Quarter BS Standardized tab (column C). Capitalized leases and capitalized R&D = previous year.
  Invested capital = operating assets - operating liabilities + capitalized leases + capitalized R&D.

NOPAT (M11:M20)
  Revenue and operating income = the Last Quarter IS cumulative values (column G) x 2 for Q2, x 4/3 for Q3 (x 4 for Q1).
  Lease expense, lease depreciation, R&D expense and R&D amortization = previous year. Adjusted EBITA = operating income.
  Operating taxes = previous-year taxes x projected operating income / previous-year operating income.
  NOPAT = operating income + lease expense - lease depreciation + R&D expense - R&D amortization - operating taxes.
  ROIC (M23) = NOPAT / invested capital. M24 = WACC, M25 = ROIC - WACC.

ROCE (N4) = Last Quarter CF cash from operations (C27) x 2 (Q2) or x 4/3 (Q3), divided by Last Quarter BS total assets (C61).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from services.adjustment_ledger_service import AdjustmentLedger

IC = "IC & NOPAT & ROIC "
INPUTS = "Inputs"
BS = "Balance Sheet - Standardized"
LQ_BS = "Last Quarter BS Standardized"
LQ_IS = "Last Quarter IS Standardized"
LQ_CF = "Last Quarter CF Standardized"
FACTOR = {1: "*4", 2: "*2", 3: "*4/3"}
BS_REF = re.compile(rf"'{re.escape(BS)}'!(?P<col>[A-Z]+)(?P<row>\d+)")


@dataclass
class IcProjectionReport:
    written: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    unmapped_rows: list[int] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.written)


def _label(ws, row: int) -> str:
    return str(ws.cell(row, 1).value or "").strip().lower().lstrip("+- ").strip()


def build_row_map(src, dst, rows: set[int]) -> dict[int, int]:
    """Annual Balance Sheet row -> Last Quarter BS row, matched by label and by which occurrence of that label it is."""
    def occurrences(ws) -> dict[tuple[str, int], int]:
        seen: dict[str, int] = {}
        out: dict[tuple[str, int], int] = {}
        for row in range(1, min(ws.max_row or 1, 200) + 1):
            label = _label(ws, row)
            if not label:
                continue
            seen[label] = seen.get(label, 0) + 1
            out[(label, seen[label])] = row
        return out

    src_occ, dst_occ = occurrences(src), occurrences(dst)
    inverse = {row: key for key, row in src_occ.items()}
    return {row: dst_occ[inverse[row]] for row in rows if row in inverse and inverse[row] in dst_occ}


def translate_to_last_quarter(formula: str, row_map: dict[int, int], unmapped: list[int]) -> str:
    """Rewrite a Balance Sheet annual formula so it reads the Last Quarter BS tab (column C)."""
    def repl(match: re.Match) -> str:
        row = int(match.group("row"))
        if row not in row_map:
            unmapped.append(row)
            return match.group(0)
        return f"'{LQ_BS}'!C{row_map[row]}"

    return BS_REF.sub(repl, formula.lstrip("="))


class IcProjectionWriter:
    def apply(self, *, workbook_path: Path, latest_quarter: int | None) -> IcProjectionReport:
        report = IcProjectionReport()
        if latest_quarter not in FACTOR:
            report.skipped.append("Full fiscal year or unidentified quarter: no projection columns.")
            return report
        path = Path(workbook_path)
        wb = load_workbook(path, data_only=False)
        try:
            need = (IC, INPUTS, BS, LQ_BS, LQ_IS, LQ_CF)
            if any(name not in wb.sheetnames for name in need):
                report.skipped.append("A required tab is missing: " + ", ".join(n for n in need if n not in wb.sheetnames))
                return report
            ws = wb[IC]
            last = self._last_annual_column(ws)
            if last is None:
                report.skipped.append("No annual columns found on the IC tab.")
                return report
            L, M, N = get_column_letter(last), get_column_letter(last + 1), get_column_letter(last + 2)
            factor = FACTOR[latest_quarter]

            inputs = wb[INPUTS]
            row_map = self._row_map_for_inputs(wb, inputs, L)
            unmapped: list[int] = []

            def lq_formula(row: int) -> str | None:
                value = inputs[f"{L}{row}"].value
                if not isinstance(value, str) or not value.startswith("="):
                    return None
                return translate_to_last_quarter(value, row_map, unmapped)

            assets = [lq_formula(81), lq_formula(82)]
            liabilities = [lq_formula(84), lq_formula(85)]
            if not all(assets) or not all(liabilities):
                report.skipped.append("Inputs operating asset/liability formulas not found; M3 and M4 not written.")
            formulas: dict[str, str] = {
                f"{M}1": "Projected ROIC",
                f"{N}1": "ROCE",
                f"{M}5": f"={L}5",
                f"{M}6": f"={L}6",
                f"{M}7": f"={M}3-{M}4+{M}5+{M}6",
                f"{M}11": f"='{LQ_IS}'!G11{factor}",
                f"{M}12": f"={M}11-{M}13",
                f"{M}13": f"='{LQ_IS}'!G32{factor}",
                f"{M}14": f"={L}14",
                f"{M}15": f"={L}15",
                f"{M}16": f"={L}16",
                f"{M}17": f"={L}17",
                f"{M}18": f"={M}13",
                f"{M}19": f'=IF(OR({L}13="",{L}13=0),"",{M}13/{L}13*{L}19)',
                f"{M}20": f"={M}13+{M}14-{M}15+{M}16-{M}17-{M}19",
                f"{M}23": f"={M}20/{M}7",
                f"{M}24": f"='Final Metrics'!{L}7" if "Final Metrics" in wb.sheetnames else None,
                f"{M}25": f"={M}23-{M}24" if "Final Metrics" in wb.sheetnames else None,
                f"{N}4": f"='{LQ_CF}'!C27{factor}/'{LQ_BS}'!C61",
            }
            if all(assets):
                formulas[f"{M}3"] = "=(" + assets[0] + ")+(" + assets[1] + ")"
            if all(liabilities):
                formulas[f"{M}4"] = "=(" + liabilities[0] + ")+(" + liabilities[1] + ")"
            report.unmapped_rows = sorted(set(unmapped))
            for addr, formula in formulas.items():
                if formula is None:
                    continue
                cell = ws[addr]
                if cell.value not in (None, ""):
                    report.skipped.append(f"{IC}!{addr} already holds a value; left as is.")
                    continue
                cell.value = formula
                report.written.append(f"{IC}!{addr}")
            self._format(ws, last)
            if report.changed:
                quarter_word = {1: "x 4", 2: "x 2", 3: "x 4/3"}[latest_quarter]
                AdjustmentLedger(wb).record(
                    sheet=IC, cell=f"{M}23", fiscal_year=None, category="Projection",
                    what=f"Projected ROIC (column {M}) and ROCE (column {N})", original="blank", new=f"=NOPAT/Invested capital (column {M})",
                    amount=None,
                    reason=(f"Q{latest_quarter}: revenue and operating income = Last Quarter IS cumulative {quarter_word}; ROCE = cash from operations "
                            f"{quarter_word} / total assets. Capitalized leases and R&D, lease and R&D expenses and amortization = previous year; "
                            "operating taxes scale with operating income."),
                    source="Last Quarter IS / CF / BS Standardized tabs", method="house_projection_method", confidence="high", mark_cell=False,
                )
                from services.tab_notes import add_notes, note

                add_notes(
                    ws,
                    [
                        note(
                            f"Projected ROIC (column {M}) and ROCE (column {N}) were calculated for the current year",
                            f"the year is not finished; revenue, operating income and cash from operations from the latest quarter were scaled up ({quarter_word})",
                            "the Last Quarter income statement, cash flow and balance sheet tabs",
                        ),
                        note(
                            "Capitalized leases, capitalized R&D, lease and R&D expenses and amortization are kept at last year's level, and operating taxes move with operating income",
                            "they do not change within the year",
                            "the previous annual column of this tab",
                        ),
                    ],
                    replace_containing=("Projected ROIC (column", "Capitalized leases, capitalized R&D, lease and R&D"),
                )
            wb.save(path)
        finally:
            wb.close()
        return report

    @staticmethod
    def _format(ws, last: int) -> None:
        """Projection columns M and N are coloured; ROIC, WACC, ROIC - WACC and ROCE are shown as percentages."""
        m, n = last + 1, last + 2
        for col, color in ((m, "DDEBF7"), (n, "FCE4D6")):
            for row in range(1, 26):
                ws.cell(row, col).fill = PatternFill("solid", fgColor=color)
        for col in (m, n):
            ws.cell(1, col).font = Font(bold=True)
            ws.column_dimensions[get_column_letter(col)].width = max(ws.column_dimensions[get_column_letter(col)].width or 0, 16)
        for col in range(2, m + 1):
            ws.cell(23, col).number_format = "0.0%"          # ROIC
        for row in (24, 25):                                  # WACC and ROIC - WACC
            ws.cell(row, m).number_format = "0.0%"
        ws.cell(4, n).number_format = "0.0%"                  # ROCE

    @staticmethod
    def _last_annual_column(ws) -> int | None:
        """Rightmost column whose Operating Assets cell is the annual link =Inputs!X80 (projection columns are not links)."""
        for col in range((ws.max_column or 1), 1, -1):
            value = ws.cell(3, col).value
            if isinstance(value, str) and re.fullmatch(r"=Inputs!\$?[A-Z]+\$?80", value.strip()):
                return col
        return None

    @staticmethod
    def _row_map_for_inputs(wb, inputs, col_letter: str) -> dict[int, int]:
        rows: set[int] = set()
        for r in (81, 82, 84, 85):
            value = inputs[f"{col_letter}{r}"].value
            if isinstance(value, str):
                rows |= {int(m.group("row")) for m in BS_REF.finditer(value)}
        return build_row_map(wb[BS], wb[LQ_BS], rows)
