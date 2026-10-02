"""Write-intent action classes for Annual Update (and shared fill/analysis)."""

from __future__ import annotations

from enum import Enum


class WriteActionClass(str, Enum):
    SOURCE_FILL = "SOURCE_FILL"
    ALREADY_PRESENT = "ALREADY_PRESENT"
    VALIDATED = "VALIDATED"
    DISCREPANCY = "DISCREPANCY"
    FLAG_FOR_REVIEW = "FLAG_FOR_REVIEW"
    HAP_ANALYSIS = "HAP_ANALYSIS"
    BLOCKING_STRUCTURAL_ERROR = "BLOCKING_STRUCTURAL_ERROR"
    PRIOR_ANALYST_OVERRIDE = "PRIOR_ANALYST_OVERRIDE"
    SUGGESTION_ONLY = "SUGGESTION_ONLY"
