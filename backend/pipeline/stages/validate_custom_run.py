"""Stage: validate custom_run_filter against the parsed workbook structure."""

from __future__ import annotations

from pathlib import Path

from models.analysis import Analysis
from models.custom_run import CustomRunMapping
from models.pipeline import DecisionLogEntry
from models.workbook_schema import WorkbookStructure
from services.custom_run_service import CustomRunParseError, CustomRunService
from services.output_service import OutputService


class ValidateCustomRunStage:
    """Parse and validate the custom_run filter against workbook worksheets."""

    def __init__(
        self,
        custom_run_service: CustomRunService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.custom_run_service = custom_run_service or CustomRunService()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        custom_run_path: Path,
        structure: WorkbookStructure,
    ) -> tuple[CustomRunMapping, str, DecisionLogEntry]:
        if analysis.files.custom_run_filter is None:
            raise CustomRunParseError("custom_run_filter is required to run the HAP pipeline.")

        original_filename = analysis.files.custom_run_filter.filename
        mapping = self.custom_run_service.parse(custom_run_path, original_filename)
        self.custom_run_service.validate_against_workbook(mapping, structure)

        artifact_path = self.output_service.write_json(
            analysis.analysis_id,
            "custom_run_mapping.json",
            mapping,
        )
        log_entry = DecisionLogEntry(
            agent="Workbook Completion Agent",
            action="validate_custom_run_filter",
            detail=(
                f"Validated {mapping.entry_count} mappings from {original_filename} "
                f"against {len(structure.worksheet_names)} worksheets."
            ),
            confidence=1.0,
            citations=[artifact_path],
        )
        return mapping, artifact_path, log_entry
