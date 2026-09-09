"""Stage: parse workbook structure without modifying the file."""

from __future__ import annotations

from pathlib import Path

from models.analysis import Analysis
from models.pipeline import DecisionLogEntry
from models.workbook_schema import WorkbookStructure
from services.output_service import OutputService
from services.workbook_service import PARSER_SCHEMA_VERSION, WorkbookService


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
        timings = getattr(self.workbook_service, "last_parse_timings", {}) or {}
        artifact_path = self.output_service.write_json(
            analysis.analysis_id,
            "workbook_structure.json",
            structure,
        )
        # Compact timing artifact for performance triage (not the multi-GB cell dump).
        self.output_service.write_json(
            analysis.analysis_id,
            "parse_workbook_timings.json",
            {
                "parser_schema_version": PARSER_SCHEMA_VERSION,
                "timings": timings,
                "formula_count": structure.formula_count,
                "non_empty_cell_count": structure.non_empty_cell_count,
                "sheet_count": len(structure.worksheet_names),
            },
        )
        cache_note = timings.get("cache", "n/a")
        total_ms = timings.get("total_ms", "n/a")
        log_entry = DecisionLogEntry(
            agent="Workbook Completion Agent",
            action="parse_workbook",
            detail=(
                f"Parsed {len(structure.worksheet_names)} worksheets, "
                f"{structure.formula_count} formulas, "
                f"{len(structure.named_ranges)} named ranges "
                f"(cache={cache_note}, total_ms={total_ms})."
            ),
            confidence=1.0,
            citations=[artifact_path],
        )
        return structure, artifact_path, log_entry
