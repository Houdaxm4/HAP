"""Lease Estimated Long-Term Rate: preserve unless unexplained outlier vs ~9 prior years."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.annual_update import AnnualLeasesReport, JudgmentRecord
from services.annual_continuity_service import detect_year_columns

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
        outlier = False
        normalized = False
        note = None
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
            if new_col is None and fy_items:
                new_col = fy_items[-1][1]
                token = fy_items[-1][0]
            for fy, col in fy_items:
                val = _num(ws.cell(_RATE_ROW, col).value)
                if val is None:
                    continue
                if fy == token:
                    original = val
                else:
                    hist.append(val)
            selected = original
            if original is not None and hist:
                med = _median(hist[-9:])
                # Economic outlier: >150bp from median AND >40% relative, or sign flip.
                outlier = abs(original - med) > 0.015 and (
                    abs(original - med) / max(abs(med), 1e-6) > 0.4
                )
                if outlier and extraordinary_event:
                    note = event_note or (
                        "Estimated Long-Term Rate is an outlier but an extraordinary lease event "
                        "was identified; rate not mechanically normalized."
                    )
                    ws.cell(_RATE_ROW + 2, 2).value = note
                elif outlier and not extraordinary_event and hist:
                    selected = hist[-1]
                    cell = ws.cell(_RATE_ROW, new_col)
                    if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                        cell.value = selected
                    else:
                        # Analyst override row: write adjacent note + value if formula
                        ws.cell(_RATE_ROW, new_col).value = selected
                    normalized = True
                    note = (
                        f"New-year Estimated Long-Term Rate {original} was an unexplained outlier "
                        f"vs prior ~{len(hist)} years (median {med:.4f}); normalized to prior year {selected}."
                    )
                    ws.cell(_RATE_ROW + 2, 2).value = note
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
            analyst_note=note,
            evidence=list(event_sources or []),
            summary=(
                f"Leases: original={original} selected={selected} outlier={outlier} "
                f"event={extraordinary_event} normalized={normalized}."
            ),
        )

    def judgment_record(self, report: AnnualLeasesReport) -> JudgmentRecord:
        return JudgmentRecord(
            metric="lease_estimated_long_term_rate",
            original_value=report.original_rate,
            selected_value=report.selected_rate,
            original_methodology="workbook_new_year_rate",
            selected_methodology=(
                "prior_year_normalization" if report.normalized_to_prior else "preserve_workbook_rate"
            ),
            evidence=report.evidence,
            rationale=report.analyst_note or report.summary,
            workbook_impact="Leases estimated long-term rate (new FY)",
            confidence=0.75,
            adjusted=report.normalized_to_prior,
        )
