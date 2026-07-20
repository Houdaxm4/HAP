"""HAP validation harness — batch-run real company workbooks through the pipeline.

Does not modify analytical methodology. Uses the same services and orchestrator
as the API (create → upload → run → collect).

Usage::

    cd backend
    python -m validation --input path/to/companies --output path/to/results

Company package layout::

    companies/
      AAPL/
        workbook.xlsx
        custom_run_filter.csv
        manifest.json   # optional: {"company": "Apple Inc.", "ticker": "AAPL"}
"""

from __future__ import annotations

# Defined before submodule imports so validation.runner can import it safely.
ENGINE_VERSION = "0.3.0"

from validation.discovery import ValidationCase, discover_cases
from validation.report import write_reports, write_results_csv, write_summary_md
from validation.runner import ValidationBatchResult, ValidationRow, run_validation

__all__ = [
    "ENGINE_VERSION",
    "ValidationBatchResult",
    "ValidationCase",
    "ValidationRow",
    "discover_cases",
    "run_validation",
    "write_reports",
    "write_results_csv",
    "write_summary_md",
]
