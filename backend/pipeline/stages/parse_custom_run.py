"""Parse Bloomberg Custom_Run_Filter workbook into CustomRunData."""

from __future__ import annotations

from pathlib import Path

from ingestion.custom_run_parser import CustomRunParseError, CustomRunParser
from ingestion.models.custom_run_data import CustomRunData
from models.analysis import Analysis
from models.pipeline import DecisionLogEntry
from services.output_service import OutputService


class ParseCustomRunStage:
    """Parse the Bloomberg-derived Custom_Run_Filter proprietary analytics workbook."""

    def __init__(
        self,
        parser: CustomRunParser | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.parser = parser or CustomRunParser()
        self.output_service = output_service or OutputService()

    def run(
        self,
        analysis: Analysis,
        custom_run_path: Path,
    ) -> tuple[CustomRunData, str, DecisionLogEntry]:
        if analysis.files.custom_run_filter is None:
            raise CustomRunParseError("custom_run_filter is required to run the HAP pipeline.")

        original_filename = analysis.files.custom_run_filter.filename
        data = self.parser.parse(custom_run_path, original_filename)
        artifact_path = self.output_service.write_json(
            analysis.analysis_id,
            "custom_run_data.json",
            data,
        )
        log_entry = DecisionLogEntry(
            agent="Document Collection Agent",
            action="parse_custom_run",
            detail=(
                f"Parsed Bloomberg Custom_Run_Filter workbook '{original_filename}' "
                f"for {data.ticker or analysis.ticker}: "
                f"{len(data.historical_metrics)} historical, "
                f"{len(data.proprietary_metrics)} proprietary metrics."
            ),
            confidence=1.0,
            citations=[artifact_path],
        )
        return data, artifact_path, log_entry
