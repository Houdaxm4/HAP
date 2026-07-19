"""Facade for Bloomberg Custom_Run_Filter ingestion (replaces mapping-table parser)."""

from __future__ import annotations

from pathlib import Path

from ingestion.custom_run_parser import CustomRunParseError, CustomRunParser
from ingestion.custom_run_validator import CustomRunValidationError, CustomRunValidator
from ingestion.models.custom_run_data import CustomRunData, CustomRunValidationReport

# Re-export for pipeline error handling compatibility.
__all__ = [
    "CustomRunParseError",
    "CustomRunValidationError",
    "CustomRunService",
]


class CustomRunService:
    """
    Parse and validate Bloomberg-derived Custom_Run_Filter workbooks.

    This replaces the previous worksheet/cell mapping table parser, which was
    an engineering artifact and not part of the HAP v1 product specification.
    """

    def __init__(
        self,
        parser: CustomRunParser | None = None,
        validator: CustomRunValidator | None = None,
    ) -> None:
        self.parser = parser or CustomRunParser()
        self.validator = validator or CustomRunValidator()

    def parse(self, file_path: Path, original_filename: str) -> CustomRunData:
        return self.parser.parse(file_path, original_filename)

    def validate(
        self,
        data: CustomRunData,
        *,
        expected_ticker: str | None = None,
    ) -> CustomRunValidationReport:
        return self.validator.validate(data, expected_ticker=expected_ticker)
