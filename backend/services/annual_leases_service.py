"""Lease Estimated Long-Term Rate: carry reproducible analyst methodology; never guess."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.annual_update import AnnualLeasesReport, JudgmentRecord
from models.write_actions import WriteActionClass
from services.annual_continuity_service import detect_year_columns
from services.formula_utils import is_formula
from services.workbook_flag_service import SUGGESTION_COMMENT, flag_suggestion

_RATE_ROW = 18


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return 0.0
    if n % 2:
        return s[n // 2]
    return 0.5 * (s[n // 2 - 1] + s[n // 2])


def _stdev(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


class AnnualLeasesService:
    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_year: str,
        extraordinary_event: bool = False,
        event_note: str | None = None,
        event_sources: list[str] | None = None,
    ) -> AnnualLeasesReport:
        wb = load_workbook(workbook_path, data_only=False)
        original = selected = None
        hist: list[float] = []
        override_constants: list[float] = []
        formula_years = 0
        outlier = False
        normalized = False
        methodology_carried = False
        suggestion_only = False
        note = None
        action = WriteActionClass.VALIDATED.value
        try:
            if "Leases" not in wb.sheetnames:
                return AnnualLeasesReport(
                    analysis_id=analysis_id,
                    ticker=ticker,
                    summary="Leases sheet missing.",
                )
            ws = wb["Leases"]
            cols = detect_year_columns(ws)
            token = fiscal_year if str(fiscal_year).startswith("FY") else f"FY{fiscal_year}"
            new_col = cols.get(token)
            fy_items = sorted(
                ((k, c) for k, c in cols.items() if k.startswith("FY")),
                key=lambda x: x[0],
            )
            if not fy_items:
                # Fallback: treat B.. as chronological when headers are cross-sheet formulas.
                for col in range(2, 13):
                    val = ws.cell(_RATE_ROW, col).value
                    if val in (None, ""):
                        continue
                    fy_items.append((f"COL{col}", col))
                if fy_items:
                    new_col = fy_items[-1][1]
                    token = fy_items[-1][0]
            if new_col is None and fy_items:
                new_col = fy_items[-1][1]
                token = fy_items[-1][0]
            new_cell = ws.cell(_RATE_ROW, new_col) if new_col else None
            original = _num(new_cell.value) if new_cell else None
            for fy, col in fy_items:
                raw = ws.cell(_RATE_ROW, col).value
                if fy == token or col == new_col:
                    continue
                if is_formula(raw):
                    formula_years += 1
                    continue
                val = _num(raw)
                if val is None:
                    continue
                hist.append(val)
                override_constants.append(val)

            selected = original
            clear_method = (
                len(override_constants) >= 3
                and _stdev(override_constants) <= 0.005
                and (formula_years == 0 or len(override_constants) >= formula_years)
            )
            med = _median(override_constants) if override_constants else None
            if original is not None and med is not None:
                outlier = abs(original - med) > 0.015 and (
                    abs(original - med) / max(abs(med), 1e-6) > 0.4
                )
            elif original is None and med is not None:
                outlier = False

            if clear_method and med is not None and new_cell is not None:
                if extraordinary_event:
                    note = event_note or (
                        "Estimated Long-Term Rate has a prior analyst methodology, but an "
                        "extraordinary lease event was identified; rate not mechanically changed."
                    )
                    action = WriteActionClass.FLAG_FOR_REVIEW.value
                elif new_cell is not None and not is_formula(new_cell.value):
                    if original is None or (outlier and abs((original or 0) - med) > 1e-9):
                        new_cell.value = med
                        selected = med
                        normalized = True
                        methodology_carried = True
                        action = WriteActionClass.PRIOR_ANALYST_OVERRIDE.value
                        note = (
                            f"Reproducible historical Estimated Long-Term Rate methodology "
                            f"(~{med:.4f} across {len(override_constants)} analyst-entered years) "
                            f"applied to the newest year. Provenance: prior analyst override."
                        )
                elif is_formula(new_cell.value) and outlier:
                    # Do not overwrite the template formula; suggest only.
                    suggestion_only = True
                    action = WriteActionClass.SUGGESTION_ONLY.value
                    note = (
                        f"{SUGGESTION_COMMENT} Historical methodology centers on {med:.4f}; "
                        "newest-year cell is formula-driven so HAP did not overwrite it."
                    )
                    flag_suggestion(ws, new_cell.coordinate, suggestion=med, reason=note)
            elif outlier and not extraordinary_event and new_cell is not None:
                suggestion_only = True
                action = WriteActionClass.SUGGESTION_ONLY.value
                suggested = hist[-1] if hist else med
                note = (
                    f"{SUGGESTION_COMMENT} Newest-year Estimated Long-Term Rate {original} "
                    f"may be economically off vs prior constants {override_constants}. "
                    f"Suggested review value: {suggested}. HAP did not change the cell "
                    "because no clear reproducible methodology was identified."
                )
                flag_suggestion(ws, new_cell.coordinate, suggestion=suggested, reason=note)
            elif extraordinary_event:
                note = event_note or (
                    "Extraordinary lease event identified; rate not mechanically changed."
                )

            wb.save(workbook_path)
        finally:
            wb.close()
        return AnnualLeasesReport(
            analysis_id=analysis_id,
            ticker=ticker,
            original_rate=original,
            selected_rate=selected,
            historical_rates=hist,
            outlier=outlier,
            extraordinary_event=extraordinary_event,
            normalized_to_prior=normalized,
            methodology_carried=methodology_carried,
            suggestion_only=suggestion_only,
            action_class=action,
            analyst_note=note,
            evidence=list(event_sources or []),
            summary=(
                f"Leases: original={original} selected={selected} outlier={outlier} "
                f"methodology_carried={methodology_carried} suggestion_only={suggestion_only} "
                f"event={extraordinary_event}."
            ),
        )

    def judgment_record(self, report: AnnualLeasesReport) -> JudgmentRecord:
        return JudgmentRecord(
            metric="lease_estimated_long_term_rate",
            original_value=report.original_rate,
            selected_value=report.selected_rate,
            original_methodology="workbook_new_year_rate",
            selected_methodology=(
                "prior_analyst_methodology"
                if report.methodology_carried
                else "suggestion_only"
                if report.suggestion_only
                else "preserve_workbook_rate"
            ),
            evidence=report.evidence,
            rationale=report.analyst_note or report.summary,
            workbook_impact="Leases estimated long-term rate (new FY)",
            confidence=0.75,
            adjusted=report.normalized_to_prior,
        )
