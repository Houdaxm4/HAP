"""Stage: parse workbook structure without modifying the file."""

from __future__ import annotations

from pathlib import Path

from models.analysis import Analysis
from models.pipeline import DecisionLogEntry
from models.workbook_schema import WorkbookStructure
from services.output_service import OutputService
from services.workbook_service import WorkbookService


class ParseWorkbookStage:
    """Understand workbook structure before any data collection."""

    def __init__(
        self,
        workbook_service: WorkbookService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.workbook_service = workbook_service or WorkbookService()
        self.output_service = output_service or OutputService()

    def run(self, analysis: Analysis, workbook_path: Path) -> tuple[WorkbookStructure, str, DecisionLogEntry]:
        original_filename = analysis.files.prefilled_workbook.filename  # type: ignore[union-attr]
        structure = self.workbook_service.parse_structure(workbook_path, original_filename)
        artifact_path = self.output_service.write_json(
            analysis.analysis_id,
            "workbook_structure.json",
            structure,
        )
        log_entry = DecisionLogEntry(
            agent="Workbook Completion Agent",
            action="parse_workbook",
            detail=(
                f"Parsed {len(structure.worksheet_names)} worksheets "
                f"({len(structure.hidden_sheets)} hidden), "
                f"{structure.formula_count} formula cells, "
                f"{structure.editable_cell_count} editable cells, "
                f"{len(structure.named_ranges)} named ranges. "
                "Source workbook was not modified; formatting captured in JSON."
            ),
            confidence=1.0,
            citations=[artifact_path],
        )
        return structure, artifact_path, log_entry
