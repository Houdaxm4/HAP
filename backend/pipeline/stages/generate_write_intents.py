"""Stage: M3 write-intent generation (no Excel mutation)."""

from __future__ import annotations

from typing import Any

from canonical_model import build_company_financial_model
from models.analysis import Analysis
from models.custom_run import CustomRunData
from models.pipeline import DecisionLogEntry
from models.provenance import ProvenanceReport
from models.validation import DiscrepancyReport
from services.output_service import OutputService
from workbook_mapping.engine import (
    WriteIntentReport,
    load_manifest_index,
    load_mapping_specification,
    map_model_to_write_intents,
    validate_write_intents,
)


class GenerateWriteIntentsStage:
    """
    Build CFM from SEC + Custom Run, emit validated write_intents.json.

    Does not open or modify any Excel workbook. FillWorkbookStage does not
    consume these intents until M4.
    """

    def __init__(self, output_service: OutputService | None = None) -> None:
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        custom_run: CustomRunData,
        company_facts: dict[str, Any],
        workbook_path: Any | None = None,
    ) -> tuple[WriteIntentReport, str, DecisionLogEntry]:
        seed_provenance = ProvenanceReport(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
        )
        empty_discrepancy = DiscrepancyReport(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
        )
        model = build_company_financial_model(
            analysis_id=analysis.analysis_id,
            ticker=analysis.ticker,
            company=analysis.company or custom_run.company,
            analysis_type=analysis.analysis_type,
            provenance_report=seed_provenance,
            discrepancy_report=empty_discrepancy,
            company_facts=company_facts,
            custom_run=custom_run,
            metadata={
                "ingestion": "hap_v1_sec_plus_custom_run",
                "custom_run_source": custom_run.source_filename,
            },
        )

        mapping = load_mapping_specification(workbook_path=workbook_path)
        manifest_index = load_manifest_index()
        report = map_model_to_write_intents(
            model,
            mapping,
            manifest_index=manifest_index,
            source_document=custom_run.source_filename,
        )
        # Validate batch (conflicts hard-fail); WRITE list reserved for M4.
        validate_write_intents(report)

        intents_path = self.output_service.write_json(
            analysis.analysis_id,
            "write_intents.json",
            report,
        )
        log_entry = DecisionLogEntry(
            agent="Write Intent Engine",
            action="generate_write_intents",
            detail=(
                f"M3 write intents for {analysis.ticker}: "
                f"WRITE={report.write_count}, SKIP={report.skip_count}, "
                f"BLOCK={report.block_count} (Excel not modified)."
            ),
            confidence=0.95,
            citations=[intents_path],
        )
        return report, intents_path, log_entry
