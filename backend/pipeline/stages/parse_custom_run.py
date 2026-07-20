"""Stage: parse the Bloomberg Custom_Run_Filter workbook (HAP v1)."""

from __future__ import annotations

from pathlib import Path

from models.analysis import Analysis
from models.custom_run import CustomRunData
from models.pipeline import DecisionLogEntry
from services.custom_run_service import CustomRunParseError, CustomRunService
from services.output_service import OutputService


class ParseCustomRunStage:
    """Parse Bloomberg proprietary Custom_Run_Filter into CustomRunData."""

    def __init__(
        self,
        custom_run_service: CustomRunService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.custom_run_service = custom_run_service or CustomRunService()
        self.output_service = output_service or OutputService()

    def run(self, analysis: Analysis, custom_run_path: Path) -> tuple[CustomRunData, str, DecisionLogEntry]:
        if analysis.files.custom_run_filter is None:
            raise CustomRunParseError("custom_run_filter is required to run the HAP pipeline.")

        original_filename = analysis.files.custom_run_filter.filename
        data = self.custom_run_service.parse(custom_run_path, original_filename)
        artifact_path = self.output_service.write_json(
            analysis.analysis_id,
            "custom_run_data.json",
            data,
        )
        log_entry = DecisionLogEntry(
            agent="Document Collection Agent",
            action="parse_custom_run",
            detail=(
                f"Imported Custom_Run_Filter for {data.ticker}: "
                f"{data.summary_field_count} summary fields, "
                f"{data.series_count} historical series, "
                f"{data.period_count} periods."
            ),
            confidence=1.0,
            citations=[artifact_path],
        )
        return data, artifact_path, log_entry
