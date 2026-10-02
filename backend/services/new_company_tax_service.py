"""Populate ten years of tax reconciliation into the Industrial Template Inputs tax table."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from models.annual_update import AnnualTaxReport
from models.new_company import NewCompanyTaxReport, TaxDisclosureStatus, TaxYearResult
from services.annual_tax_research_service import AnnualTaxResearchService
from services.annual_tax_service import AnnualTaxService
from services.new_company_tax_table_service import NewCompanyTaxTableService


class NewCompanyTaxService:
    """Reuse AnnualTaxService mapping per year; do not treat a lone ETR as resolved."""

    def __init__(self) -> None:
        self.annual_tax = AnnualTaxService()
        self.research = AnnualTaxResearchService()
        self.tables = NewCompanyTaxTableService()

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
            components_present = bool(supplied.get("components"))
            if company_facts and not components_present:
                researched, _questions = self.research.extract_tax_inputs(
                    company_facts=company_facts,
                    fiscal_year=fy,
                    ticker=ticker,
                )
            table_payload: dict[str, Any] = {}
            if supplied.get("candidate_table"):
                table_payload = self.tables.extract(
                    fiscal_year=fy,
                    candidate_table=list(supplied["candidate_table"]),
                    heading=supplied.get("heading"),
                    prior_schema=supplied.get("prior_schema"),
                    accession_number=supplied.get("accession_number"),
                    note_location=supplied.get("note_location") or supplied.get("source"),
                    pretax_income=supplied.get("pretax_income") or researched.get("pretax_income"),
                    income_tax_expense=supplied.get("income_tax_expense")
                    or researched.get("income_tax_expense"),
                    llm_classifier=supplied.get("llm_classifier"),
                )
            payload = {
                **researched,
                **{k: v for k, v in supplied.items() if v is not None and k != "candidate_table"},
            }
            if table_payload:
                payload = {**payload, **{k: v for k, v in table_payload.items() if v is not None}}
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
            computed = payload.get("computed_effective_rate")
            if computed is None and report.pretax_income and abs(report.pretax_income) > 1e-9 and report.income_tax_expense is not None:
                computed = report.income_tax_expense / report.pretax_income
            disclosure = payload.get("disclosure_status") or self._disclosure(mapped)
            statutory = mapped.get("statutory_federal")
            category_complete = statutory is not None and report.reported_effective_tax_rate is not None
            year = TaxYearResult(
                fiscal_year=fy,
                reported_effective_rate=report.reported_effective_tax_rate,
                computed_effective_rate=computed,
                statutory_federal=statutory,
                state=mapped.get("state"),
                foreign=mapped.get("foreign"),
                rd_credit=mapped.get("credits"),
                other=mapped.get("other"),
                residual_other=report.residual_other,
                reported_other=payload.get("reported_other"),
                unmapped_lines=list(payload.get("unmapped_lines") or []),
                category_mappings=list(payload.get("category_mappings") or []),
                disclosure_status=disclosure,
                other_calculation=payload.get("other_calculation")
                or (
                    "Other = Effective tax rate − statutory/federal − state − foreign − R&D tax-credit rate"
                    if report.residual_other is not None
                    else None
                ),
                component_sum=sum(
                    (mapped.get(k) or 0.0)
                    for k in ("statutory_federal", "state", "foreign", "credits", "other")
                ),
                reconciliation_delta=report.reconciliation_delta,
                reconciliation_status=payload.get("reconciliation_status") or report.reconciliation_status,
                pretax_income=report.pretax_income,
                income_tax_expense=report.income_tax_expense,
                units="rate_fraction",
                table_units=payload.get("table_units"),
                signs_normalized=bool(payload.get("signs_normalized")),
                cells_written=report.cells_written,
                schedule_populated=report.schedule_populated and category_complete,
                raw_filing_lines=list(payload.get("raw_filing_lines") or payload.get("components") or []),
                normalized_signed_values={
                    "statutory_federal": statutory,
                    "state": mapped.get("state"),
                    "foreign": mapped.get("foreign"),
                    "credits": mapped.get("credits"),
                    "other": mapped.get("other"),
                    "effective_tax_rate": report.reported_effective_tax_rate,
                },
                source=report.annual_report_source,
                source_locations=report.source_locations,
                accession_number=payload.get("accession_number")
                or next(
                    (
                        c.get("accession")
                        for c in (payload.get("components") or [])
                        if isinstance(c, dict) and c.get("accession")
                    ),
                    None,
                ),
                note_or_table_location=payload.get("note_or_table_location") or payload.get("source"),
                confidence=float(payload.get("confidence") or report.confidence or 0.0),
                category_coverage_complete=category_complete,
            )
            if not year.category_coverage_complete:
                warnings.append(
                    f"TEN_YEAR_TAX_COVERAGE_INCOMPLETE: {fy} missing statutory/federal or ETR "
                    "(ETR-only extraction is not coverage)."
                )
            if not year.schedule_populated:
                warnings.append(f"TEN_YEAR_TAX_COVERAGE_INCOMPLETE: {fy} schedule not populated")
            if year.reconciliation_status not in {"ok", ""}:
                warnings.append(f"{year.reconciliation_status}: {fy}")
            if year.reported_effective_rate is not None and year.statutory_federal is None:
                warnings.append(
                    f"TEN_YEAR_TAX_COVERAGE_INCOMPLETE: {fy} ETR found but statutory/federal not mapped"
                )
            years.append(year)

        complete = all(y.category_coverage_complete and y.cells_written for y in years) if years else False
        return NewCompanyTaxReport(
            analysis_id=analysis_id,
            ticker=ticker,
            years=years,
            complete=complete,
            warnings=warnings,
            summary=(
                f"Tax: {sum(1 for y in years if y.category_coverage_complete)}/{len(years)} years "
                f"with statutory+ETR coverage; warnings={len(warnings)}."
            ),
        )

    @staticmethod
    def _disclosure(mapped: dict[str, float | None]) -> dict[str, str]:
        out: dict[str, str] = {}
        for house in ("statutory_federal", "state", "foreign", "credits", "other"):
            val = mapped.get(house)
            if val is None:
                out[house] = (
                    TaxDisclosureStatus.INCLUDED_IN_OTHER.value
                    if mapped.get("other") is not None
                    else TaxDisclosureStatus.UNRESOLVED.value
                )
            elif val == 0:
                out[house] = TaxDisclosureStatus.REPORTED_ZERO.value
            else:
                out[house] = TaxDisclosureStatus.REPORTED.value
        return out
