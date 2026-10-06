"""Primary quarterly deliverables: period-named Excel + Quarterly Update.docx."""

from __future__ import annotations

import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from openpyxl import load_workbook

from models.quarterly_update import (
    QuarterlyDeliverablesReport,
    QuarterlyProjectionReport,
    QuarterlyResearchReport,
    QuarterlyReviewReport,
    QuarterlyValuationReport,
)
from services.deliverable_naming import email_deliverable_name
from services.email_draft_service import EmailDraftService, file_name
from services.workbook_values import ensure_calculated


def deliverable_excel_name(fiscal_year: int, fiscal_quarter: int, ticker: str) -> str:
    from services.deliverable_naming import excel_deliverable_name

    return excel_deliverable_name(
        fiscal_year=fiscal_year,
        ticker=ticker.upper(),
        analysis_type="Quarterly Update",
        fiscal_quarter=fiscal_quarter,
    )


def _pct(a: float | None, b: float | None) -> str:
    if a is None or b is None or b == 0:
        return "n/a"
    return f"{(a / b - 1.0) * 100:+.1f}%"


def _fmt_num(v: float | None, *, money: bool = False, pct: bool = False) -> str:
    if v is None:
        return "n/a"
    if pct:
        return f"{v * 100:.2f}%"
    if money:
        return f"${v:,.1f}M"  # workbook statements are in millions; always say so
    return f"{v:,.2f}"


def _is_blank_pair(comp) -> bool:
    """Both sides missing or both exactly zero: nothing to report."""
    a, b = comp.compare_value, comp.baseline_value
    return (a is None and b is None) or (a == 0 and b == 0)


def _is_suspect_identical(comp) -> bool:
    """A flow metric identical to the cent in both periods almost always means the prior column was not populated."""
    a, b = comp.compare_value, comp.baseline_value
    return a is not None and b is not None and a != 0 and a == b


def _find_comp(review: QuarterlyReviewReport | None, statement: str, metric: str, ctype: str):
    if review is None:
        return None
    for c in review.comparisons:
        if c.statement == statement and c.metric.lower() == metric.lower() and c.comparison_type == ctype:
            return c
    return None


class QuarterlyDeliverablesService:
    """Copy completed workbook to FA name and generate Word quarterly update."""

    def produce(
        self,
        *,
        analysis_id: str,
        ticker: str,
        completed_workbook_path: Path,
        output_dir: Path,
        fiscal_year: int | None,
        fiscal_quarter: int | None,
        projection: QuarterlyProjectionReport | None = None,
        review: QuarterlyReviewReport | None = None,
        research: QuarterlyResearchReport | None = None,
        valuation: QuarterlyValuationReport | None = None,
        judgment: Any = None,
        authorized: bool = True,
    ) -> QuarterlyDeliverablesReport:
        fy = fiscal_year or (projection.fiscal_year if projection else None) or 0
        q = fiscal_quarter or (projection.fiscal_quarter if projection else None) or 0
        if not fy or not q:
            fy, q = self._infer_fy_q(completed_workbook_path)
        excel_name = deliverable_excel_name(fy, q, ticker)
        output_dir.mkdir(parents=True, exist_ok=True)
        excel_path = output_dir / excel_name

        shutil.copy2(completed_workbook_path, excel_path)
        ensure_calculated(excel_path, analysis_id=analysis_id, ticker=ticker, fiscal_year=fy)
        email = EmailDraftService().produce_safe(
            analysis_type="quarterly_update",
            ticker=ticker,
            workbook_path=excel_path,
            output_dir=output_dir,
            projection=self._email_projection(projection),
            base_name=email_deliverable_name(fiscal_year=fy, ticker=ticker, fiscal_quarter=q),
            fiscal_year=fy,
            fiscal_quarter=q,
        )
        return QuarterlyDeliverablesReport(
            analysis_id=analysis_id,
            ticker=ticker,
            fiscal_year=fy,
            fiscal_quarter=q,
            excel_filename=excel_name,
            excel_path=str(excel_path),
            email_filename=file_name(email["text_path"]),
            email_path=email["text_path"],
            eml_path=email["eml_path"],
            summary=f"Deliverables: {excel_name}; {file_name(email['text_path'])}"
            + ("" if authorized else " (NOT AUTHORIZED: review the HAP Adjustments tab and the gate report)"),
        )

    @staticmethod
    def _email_projection(projection: QuarterlyProjectionReport | None) -> dict[str, Any] | None:
        if projection is None or projection.status == "NOT_APPLICABLE" or projection.projected_roic_wacc is None:
            return None
        year = projection.fiscal_year or ((projection.next_fiscal_year - 1) if projection.next_fiscal_year else None)   # the year being projected
        prior = None
        if projection.prior_fy_roic is not None and projection.prior_fy_wacc is not None:
            prior = projection.prior_fy_roic - projection.prior_fy_wacc
        return {
            "next_fy": str(year) if year else "Next year",
            "fy": f"FY{year - 1}" if year else "last year",
            "roic_wacc": projection.projected_roic_wacc,
            "prior_spread": prior,
            "roce": projection.projected_roce,
            "prior_roce": projection.prior_fy_roce,
        }

    def _infer_fy_q(self, path: Path) -> tuple[int, int]:
        wb = load_workbook(path, data_only=False)
        try:
            from services.quarterly_review_service import _detect_fiscal_quarter

            q = 3
            fy = 2026
            if "Last Quarter IS Standardized" in wb.sheetnames:
                ws = wb["Last Quarter IS Standardized"]
                q = _detect_fiscal_quarter(ws) or 3
                for r in range(1, 10):
                    for c in range(1, 8):
                        v = ws.cell(r, c).value
                        if isinstance(v, str):
                            for tok in v.replace("-", " ").split():
                                if tok.isdigit() and len(tok) == 4:
                                    fy = int(tok)
            return fy, q
        finally:
            wb.close()

def _num_cell(v: Any) -> float | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
