"""New Company Word investment-analysis report."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from services.business_doc_service import BusinessDocService
from services.email_draft_service import EmailDraftService, file_name
from services.workbook_values import ensure_calculated
from models.annual_update import AnnualValuationOutputs
from models.new_company import (
    LeaseRateReview,
    NewCompanyBuybackReport,
    NewCompanyDeliverablesReport,
    NewCompanyLeaseReport,
    NewCompanyOutputGateReport,
    NewCompanyPe10Report,
    NewCompanyProjectionReport,
    NewCompanyRdReport,
    NewCompanyTaxReport,
    NewCompanyValuationReport,
    RdUsefulLifeDecision,
    SeasonalityProjectionReport,
    TenYearPeriodReport,
)


def _fmt(v: Any, *, pct: bool = False) -> str:
    if v is None:
        return "unavailable"
    if pct:
        x = float(v)
        if abs(x) <= 1.5:
            x *= 100.0
        return f"{x:.2f}%"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


class NewCompanyDeliverablesService:
    def produce(
        self,
        *,
        analysis_id: str,
        ticker: str,
        company: str,
        fiscal_year: int,
        completed_workbook_path: Path,
        output_dir: Path,
        periods: TenYearPeriodReport | None,
        tax: NewCompanyTaxReport | None,
        pe10: NewCompanyPe10Report | None,
        rd_decision: RdUsefulLifeDecision | None,
        rd: NewCompanyRdReport | None,
        leases: NewCompanyLeaseReport | None,
        lease_review: LeaseRateReview | None,
        buybacks: NewCompanyBuybackReport | None,
        projection: NewCompanyProjectionReport | None,
        seasonality: SeasonalityProjectionReport | None,
        valuation: AnnualValuationOutputs | None,
        gate: NewCompanyOutputGateReport | None,
        authorized: bool,
        statement_summary: str | None = None,
        fiscal_quarter: int | None = None,
        judgment: Any = None,
        valuation_report: NewCompanyValuationReport | None = None,
    ) -> NewCompanyDeliverablesReport:
        from services.deliverable_naming import business_deliverable_name, email_deliverable_name, excel_deliverable_name

        output_dir.mkdir(parents=True, exist_ok=True)
        excel_name = excel_deliverable_name(
            fiscal_year=fiscal_year,
            ticker=ticker,
            analysis_type="New Company",
            fiscal_quarter=fiscal_quarter,
        )
        excel_path = output_dir / excel_name
        shutil.copy2(completed_workbook_path, excel_path)
        ensure_calculated(excel_path, analysis_id=analysis_id, ticker=ticker, fiscal_year=fiscal_year)
        business = BusinessDocService().produce_safe(
            ticker=ticker,
            company=company,
            workbook_path=excel_path,
            output_dir=output_dir,
            base_name=business_deliverable_name(fiscal_year=fiscal_year, ticker=ticker, fiscal_quarter=fiscal_quarter),
            search_dir=output_dir,
        )
        email = EmailDraftService().produce_safe(
            analysis_type="new_company",
            ticker=ticker,
            company=company,
            workbook_path=excel_path,
            output_dir=output_dir,
            base_name=email_deliverable_name(fiscal_year=fiscal_year, ticker=ticker, fiscal_quarter=fiscal_quarter),
            fiscal_year=fiscal_year,
            fiscal_quarter=fiscal_quarter,
            attachments=[excel_path] + ([Path(business["path"])] if business.get("path") else []),
        )
        return NewCompanyDeliverablesReport(
            analysis_id=analysis_id,
            ticker=ticker,
            fiscal_year=fiscal_year,
            excel_filename=excel_name,
            excel_path=str(excel_path),
            email_filename=file_name(email["text_path"]),
            email_path=email["text_path"],
            eml_path=email["eml_path"],
            business_doc_path=business.get("path"),
            authorized=authorized,
            summary=(
                f"Deliverables: {excel_name}"
                + f"; {file_name(email['text_path'])}"
                + ("" if authorized else " (NOT AUTHORIZED: review the HAP Adjustments tab and the gate report)")
            ),
        )
