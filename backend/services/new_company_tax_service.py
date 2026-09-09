"""Populate ten years of tax reconciliation into the Industrial Template Inputs tax table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from models.annual_update import AnnualTaxReport
from models.new_company import NewCompanyTaxReport, TaxYearResult
from services.annual_tax_research_service import AnnualTaxResearchService
from services.annual_tax_service import AnnualTaxService


class NewCompanyTaxService:
    """Reuse AnnualTaxService mapping per year; do not treat a lone ETR as resolved."""

    def __init__(self) -> None:
        self.annual_tax = AnnualTaxService()
        self.research = AnnualTaxResearchService()

    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_years: list[str],
        company_facts: dict[str, Any] | None = None,
        year_inputs: dict[str, dict[str, Any]] | None = None,
    ) -> NewCompanyTaxReport:
        years: list[TaxYearResult] = []
        warnings: list[str] = []
        for fy in fiscal_years:
            supplied = dict((year_inputs or {}).get(fy) or {})
            researched: dict[str, Any] = {}
            if company_facts and supplied.get("reported_effective_rate") is None:
                researched, _questions = self.research.extract_tax_inputs(
                    company_facts=company_facts,
                    fiscal_year=fy,
                    ticker=ticker,
                )
            payload = {**researched, **{k: v for k, v in supplied.items() if v is not None}}
            report: AnnualTaxReport = self.annual_tax.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=workbook_path,
                fiscal_year=fy,
                reported_effective_rate=payload.get("reported_effective_rate"),
                filing_components=payload.get("components"),
                source=payload.get("source") or payload.get("etr_source"),
                source_locations=payload.get("locations") or payload.get("source_locations"),
                pretax_income=payload.get("pretax_income"),
                income_tax_expense=payload.get("income_tax_expense"),
            )
            mapped = {c.house_category: c.rate for c in report.mapped_components}
            computed = None
            if report.pretax_income and abs(report.pretax_income) > 1e-9 and report.income_tax_expense is not None:
                computed = report.income_tax_expense / report.pretax_income
            year = TaxYearResult(
                fiscal_year=fy,
                reported_effective_rate=report.reported_effective_tax_rate,
                computed_effective_rate=computed,
                statutory_federal=mapped.get("statutory_federal"),
                state=mapped.get("state"),
                foreign=mapped.get("foreign"),
                rd_credit=mapped.get("credits"),
                other=mapped.get("other"),
                residual_other=report.residual_other,
                component_sum=sum(c.rate or 0.0 for c in report.mapped_components),
                reconciliation_delta=report.reconciliation_delta,
                reconciliation_status=report.reconciliation_status,
                pretax_income=report.pretax_income,
                income_tax_expense=report.income_tax_expense,
                cells_written=report.cells_written,
                schedule_populated=report.schedule_populated,
                raw_filing_lines=payload.get("components") or [],
                source=report.annual_report_source,
                source_locations=report.source_locations,
            )
            if not year.schedule_populated:
                warnings.append(f"TEN_YEAR_TAX_COVERAGE_INCOMPLETE: {fy} schedule not populated")
            if year.reconciliation_status not in {"ok", ""}:
                warnings.append(f"{year.reconciliation_status}: {fy}")
            # Finding ETR alone is not resolution — required cells must be written.
            if year.reported_effective_rate is not None and not year.cells_written:
                warnings.append(
                    f"TEN_YEAR_TAX_COVERAGE_INCOMPLETE: {fy} ETR found but tax table cells not written"
                )
            years.append(year)

        complete = all(y.schedule_populated and y.cells_written for y in years) if years else False
        return NewCompanyTaxReport(
            analysis_id=analysis_id,
            ticker=ticker,
            years=years,
            complete=complete,
            warnings=warnings,
            summary=(
                f"Tax: {sum(1 for y in years if y.schedule_populated)}/{len(years)} years populated; "
                f"warnings={len(warnings)}."
            ),
        )
