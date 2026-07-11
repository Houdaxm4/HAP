"""Stage: populate workbook cells from SEC facts with full provenance."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from models.analysis import Analysis
from models.custom_run import CustomRunMapping
from models.pipeline import DecisionLogEntry
from models.provenance import (
    CellProvenance,
    CellTransformation,
    ConfidenceBand,
    PeriodClassification,
    ProvenanceReport,
)
from models.workbook_schema import WorkbookStructure
from services.output_service import OutputService
from services.sec_service import SecService, XbrlFact
from services.workbook_service import WorkbookService

logger = logging.getLogger(__name__)


class FillWorkbookStage:
    """Fill only custom_run cells and record explainability metadata."""

    def __init__(
        self,
        workbook_service: WorkbookService | None = None,
        sec_service: SecService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.workbook_service = workbook_service or WorkbookService()
        self.sec_service = sec_service or SecService()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        source_workbook_path: Path,
        custom_run_mapping: CustomRunMapping,
        workbook_structure: WorkbookStructure,
        company_facts: dict,
        filings_manifest: dict,
    ) -> tuple[ProvenanceReport, str, str, DecisionLogEntry]:
        workbook_filename = (
            analysis.files.prefilled_workbook.filename
            if analysis.files.prefilled_workbook
            else source_workbook_path.name
        )
        provenance_entries: list[CellProvenance] = []

        for mapping in custom_run_mapping.entries:
            cell_ref = self.workbook_service.make_cell_ref(mapping.worksheet, mapping.cell)
            original_value = self.workbook_service.get_structure_cell_value(
                workbook_structure, mapping.worksheet, mapping.cell
            )
            entry = CellProvenance(
                analysis_id=analysis.analysis_id,
                ticker=analysis.ticker,
                workbook_filename=workbook_filename,
                cell_ref=cell_ref,
                worksheet=mapping.worksheet,
                cell=mapping.cell,
                field_name=mapping.concept,
                concept=mapping.concept,
                period=mapping.period,
                original_workbook_value=original_value,
                workbook_unit=mapping.unit,
                custom_run_value=mapping.value,
                period_classification=self._classify_period(mapping.period),
            )

            # Rule: never overwrite a formula cell.
            if self.workbook_service.cell_contains_formula(
                workbook_structure, mapping.worksheet, mapping.cell
            ):
                entry.status = "skipped_formula"
                entry.source_type = "workbook formula"
                entry.failure_reason = "Cell contains a formula and was not overwritten."
                entry.confidence = 1.0
                entry.confidence_band = "high"
                entry.reasoning = "Formula cells are preserved; HAP never overwrites formulas."
                provenance_entries.append(entry)
                continue

            fact = self.sec_service.find_fact(
                company_facts,
                mapping.concept,
                mapping.period,
                mapping.xbrl_tag,
            )

            # Uncertain / missing mapping → unresolved, do not populate.
            if fact is None and mapping.value is None:
                entry.status = "unresolved"
                entry.source_type = "unresolved"
                entry.confidence = 0.2
                entry.confidence_band = "low"
                entry.failure_reason = (
                    f"No SEC XBRL fact found for concept '{mapping.concept}' "
                    f"and period '{mapping.period}', and no custom_run value provided."
                )
                entry.reasoning = (
                    "Mapping is uncertain; cell left unresolved rather than fabricating a value."
                )
                provenance_entries.append(entry)
                continue

            # Filing controls over custom_run_filter when both exist and conflict.
            if fact is not None:
                filing_meta = self._resolve_filing(filings_manifest, fact)
                source_value = float(fact.value)
                write_value, transforms = self._apply_unit_transforms(
                    source_value,
                    source_unit=fact.unit,
                    workbook_unit=mapping.unit,
                )

                entry.original_source_value = source_value
                entry.source_unit = fact.unit
                entry.xbrl_tag = f"{fact.taxonomy}:{fact.tag}"
                entry.source_document = filing_meta.get("document_url")
                entry.source_url = filing_meta.get("document_url")
                entry.filing_type = fact.form or filing_meta.get("filing_type")
                entry.filing_year = fact.fiscal_year or filing_meta.get("fiscal_year")
                entry.filing_date = fact.filed or filing_meta.get("filing_date")
                entry.fiscal_period = fact.fiscal_period
                entry.accession_number = fact.accession_number or filing_meta.get(
                    "accession_number"
                )
                entry.statement_name = self._guess_statement(mapping.concept, mapping.worksheet)
                entry.source_type = self._source_type_for_form(entry.filing_type)
                entry.transformations = transforms
                entry.period_classification = self._classify_period_from_fact(
                    mapping.period, fact
                )
                entry.confidence = self._confidence_score(fact, mapping.period)
                entry.confidence_band = self._band(entry.confidence)
                entry.proposed_value = write_value
                entry.reasoning = (
                    f"Mapped '{mapping.concept}' ({mapping.period}) to XBRL tag "
                    f"{fact.taxonomy}:{fact.tag} from {entry.filing_type} filed "
                    f"{entry.filing_date}."
                )

                # Conflict: custom_run differs from filing → filing wins, warn via provenance.
                if mapping.value is not None and not self._values_close(mapping.value, write_value):
                    entry.conflict_with_custom_run = True
                    entry.custom_run_value = mapping.value
                    entry.reasoning += (
                        f" custom_run_filter value {mapping.value} conflicts with filing "
                        f"value {write_value}; filing controls."
                    )
                    entry.transformations.append(
                        CellTransformation(
                            type="source_priority",
                            description=(
                                "Filing/SEC XBRL value preferred over conflicting "
                                "custom_run_filter value."
                            ),
                            input_value=mapping.value,
                            output_value=write_value,
                        )
                    )

                # Rule: never silently overwrite a populated manual-input cell.
                if self.workbook_service.cell_is_populated(
                    workbook_structure, mapping.worksheet, mapping.cell
                ):
                    if not self._values_close(original_value, write_value):
                        entry.status = "preserved_existing"
                        entry.value = None
                        entry.proposed_value = write_value
                        entry.failure_reason = (
                            "Existing populated workbook value preserved; "
                            "filing value recorded as proposed (not silently overwritten)."
                        )
                        entry.reasoning += (
                            f" Original workbook value {original_value} retained; "
                            f"proposed filing value {write_value}."
                        )
                        provenance_entries.append(entry)
                        continue

                entry.status = "filled"
                entry.value = write_value
                provenance_entries.append(entry)
                continue

            # No filing fact — use custom_run only when explicitly provided (lower confidence).
            write_value = float(mapping.value)  # type: ignore[arg-type]
            entry.status = "filled"
            entry.value = write_value
            entry.proposed_value = write_value
            entry.original_source_value = write_value
            entry.source_type = "custom_run_filter"
            entry.confidence = 0.45
            entry.confidence_band = "low"
            entry.reasoning = (
                f"No SEC fact for '{mapping.concept}' ({mapping.period}); "
                "used custom_run_filter value with low confidence."
            )
            if self.workbook_service.cell_is_populated(
                workbook_structure, mapping.worksheet, mapping.cell
            ):
                if not self._values_close(original_value, write_value):
                    entry.status = "preserved_existing"
                    entry.value = None
                    entry.proposed_value = write_value
                    entry.failure_reason = (
                        "Existing populated workbook value preserved; "
                        "custom_run value not silently written."
                    )
            provenance_entries.append(entry)

        provenance_report = ProvenanceReport(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            workbook_filename=workbook_filename,
            entries=provenance_entries,
        )

        completed_workbook_path = self.output_service.artifact_path(
            analysis.analysis_id,
            "completed_workbook.xlsx",
        )
        filled_count, blank_count, skipped_formula_count = self.workbook_service.write_values(
            source_workbook_path,
            completed_workbook_path,
            provenance_entries,
        )
        preserved_existing_count = sum(
            1 for e in provenance_entries if e.status == "preserved_existing"
        )
        unresolved_count = sum(
            1 for e in provenance_entries if e.status in {"unfilled", "unresolved"}
        )
        conflict_count = sum(
            1
            for e in provenance_entries
            if e.conflict_with_custom_run or e.status == "preserved_existing"
        )
        provenance_report.filled_count = filled_count
        provenance_report.blank_count = blank_count
        provenance_report.skipped_formula_count = skipped_formula_count
        provenance_report.preserved_existing_count = preserved_existing_count
        provenance_report.unresolved_count = unresolved_count
        provenance_report.conflict_count = conflict_count

        provenance_path = self.output_service.write_json(
            analysis.analysis_id,
            "provenance_report.json",
            provenance_report,
        )
        workbook_path = self.output_service.relative_path(
            analysis.analysis_id,
            "completed_workbook.xlsx",
        )

        log_entry = DecisionLogEntry(
            agent="Workbook Completion Agent",
            action="fill_workbook",
            detail=(
                f"Filled {filled_count} cells, left {blank_count} blank, "
                f"preserved {skipped_formula_count} formula cells, "
                f"preserved {preserved_existing_count} existing values, "
                f"{unresolved_count} unresolved."
            ),
            confidence=round(filled_count / max(len(custom_run_mapping.entries), 1), 2),
            citations=[workbook_path, provenance_path],
        )
        logger.info(
            "Fill complete for %s: filled=%s blank=%s formulas=%s preserved=%s unresolved=%s",
            analysis.analysis_id,
            filled_count,
            blank_count,
            skipped_formula_count,
            preserved_existing_count,
            unresolved_count,
        )
        return provenance_report, workbook_path, provenance_path, log_entry

    @staticmethod
    def _resolve_filing(filings_manifest: dict, fact: XbrlFact) -> dict:
        selected = filings_manifest.get("selected_filings", [])
        if fact.accession_number:
            for filing in selected:
                if filing.get("accession_number") == fact.accession_number:
                    return filing
        for filing in selected:
            if filing.get("filing_type") == fact.form:
                return filing
        return selected[0] if selected else {}

    @staticmethod
    def _confidence_score(fact: XbrlFact, period: str) -> float:
        score = 0.75
        if fact.fiscal_year and str(fact.fiscal_year) in period:
            score += 0.1
        if fact.fiscal_period and fact.fiscal_period in period.upper():
            score += 0.1
        if fact.form in {"10-K", "10-Q"}:
            score += 0.05
        return min(score, 0.99)

    @staticmethod
    def _band(score: float) -> ConfidenceBand:
        if score >= 0.8:
            return "high"
        if score >= 0.55:
            return "medium"
        return "low"

    @staticmethod
    def _source_type_for_form(filing_type: str | None) -> Any:
        if filing_type == "10-K":
            return "10-K"
        if filing_type == "10-Q":
            return "10-Q"
        return "SEC XBRL"

    @staticmethod
    def _classify_period(period: str) -> PeriodClassification:
        text = period.strip().upper()
        if "TTM" in text or "TRAILING" in text:
            return "trailing_twelve_months"
        if "YTD" in text or "YEAR-TO-DATE" in text or "YEAR TO DATE" in text:
            return "year_to_date"
        if "FY" in text or re.fullmatch(r"20\d{2}|19\d{2}", text):
            return "annual"
        if re.search(r"Q[1-4]", text):
            return "standalone_quarter"
        return "unknown"

    @classmethod
    def _classify_period_from_fact(cls, period: str, fact: XbrlFact) -> PeriodClassification:
        base = cls._classify_period(period)
        if base != "unknown":
            return base
        fp = (fact.fiscal_period or "").upper()
        if fp == "FY":
            return "annual"
        if fp in {"Q1", "Q2", "Q3", "Q4"}:
            # SEC company facts for quarters are often YTD for income statement;
            # without explicit frame info we mark unknown rather than guess wrong.
            if fact.frame and "YTD" in str(fact.frame).upper():
                return "year_to_date"
            return "standalone_quarter"
        return "unknown"

    @staticmethod
    def _guess_statement(concept: str, worksheet: str) -> str | None:
        ws = worksheet.lower()
        if "balance" in ws:
            return "Balance Sheet"
        if "income" in ws or "p&l" in ws:
            return "Income Statement"
        if "cash" in ws:
            return "Cash Flow"
        concept_l = concept.lower()
        if any(t in concept_l for t in ("asset", "liabilit", "equity", "cash and")):
            return "Balance Sheet"
        if any(t in concept_l for t in ("revenue", "income", "eps", "margin")):
            return "Income Statement"
        if "cash flow" in concept_l or "capex" in concept_l:
            return "Cash Flow"
        return None

    @staticmethod
    def _apply_unit_transforms(
        source_value: float,
        source_unit: str | None,
        workbook_unit: str | None,
    ) -> tuple[float, list[CellTransformation]]:
        """
        Apply documented unit/scale conversions. Never invent values.

        Assumption: SEC USD facts are in whole dollars; workbook units may be
        thousands or millions when explicitly declared on the mapping.
        """
        transforms: list[CellTransformation] = []
        value = source_value
        wb = (workbook_unit or "").strip().lower()
        src = (source_unit or "").strip().lower()

        if wb in {"thousands", "000s", "usd thousands", "in thousands"} and src in {
            "usd",
            "",
        }:
            converted = value / 1000.0
            transforms.append(
                CellTransformation(
                    type="unit_conversion",
                    description="Converted source USD (dollars) to workbook thousands.",
                    input_value=value,
                    output_value=converted,
                )
            )
            value = converted
        elif wb in {"millions", "usd millions", "in millions"} and src in {"usd", ""}:
            converted = value / 1_000_000.0
            transforms.append(
                CellTransformation(
                    type="unit_conversion",
                    description="Converted source USD (dollars) to workbook millions.",
                    input_value=value,
                    output_value=converted,
                )
            )
            value = converted

        return value, transforms

    @staticmethod
    def _values_close(a: Any, b: Any) -> bool:
        if a is None and b is None:
            return True
        if a is None or b is None:
            return False
        try:
            return abs(float(a) - float(b)) <= max(1.0, abs(float(a)) * 0.0001)
        except (TypeError, ValueError):
            return str(a).strip() == str(b).strip()
