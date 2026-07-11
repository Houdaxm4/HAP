"""Workbook validation and discrepancy report models."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from models.common import utc_now_iso

ValidationSeverity = Literal["critical", "warning", "informational"]
ValidationOverallStatus = Literal["passed", "passed_with_warnings", "failed"]


class ValidationIssue(BaseModel):
    """One validation finding with severity and analyst guidance."""

    code: str
    severity: ValidationSeverity
    message: str
    worksheet: str | None = None
    cell: str | None = None
    cell_ref: str | None = None
    field_name: str | None = None
    expected_value: Any | None = None
    actual_value: Any | None = None
    rule: str | None = None
    source_references: list[str] = Field(default_factory=list)
    suggested_analyst_action: str | None = None
    blocks_pipeline: bool = False


class ValidationReport(BaseModel):
    """
    Trusted-model validation report produced after workbook completion.

    Overall status:
    - passed: no critical or warning issues
    - passed_with_warnings: warnings present, no critical issues (analyst review required)
    - failed: one or more critical issues (pipeline must stop before investment analysis)
    """

    analysis_id: str
    ticker: str
    issues: list[ValidationIssue] = Field(default_factory=list)
    total_checks: int = 0
    checks_passed: int = 0
    critical_count: int = 0
    warning_count: int = 0
    informational_count: int = 0
    unresolved_fields: list[str] = Field(default_factory=list)
    overall_status: ValidationOverallStatus = "passed"
    summary: str = ""
    generated_at: str = Field(default_factory=utc_now_iso)
    assumptions: list[str] = Field(
        default_factory=lambda: [
            "Balance-sheet tolerance defaults to 1% of total assets (configurable).",
            "Plausibility thresholds flag extremes; they do not auto-correct values.",
            "Critical issues block investment-analysis and writing stages.",
        ]
    )

    @property
    def blocks_pipeline(self) -> bool:
        return self.overall_status == "failed" or self.critical_count > 0


class ValidationCheck(BaseModel):
    """
    Legacy single-cell validation result.

    Retained for backward compatibility with discrepancy_report.json consumers.
    Prefer ValidationIssue / ValidationReport for new code.
    """

    cell_ref: str
    worksheet: str
    cell: str
    concept: str
    period: str
    check_type: Literal[
        "value_match",
        "missing_value",
        "formula_preserved",
        "impossible_value",
        "inconsistency",
        "unfilled",
    ]
    status: Literal["pass", "warn", "fail"]
    expected_value: Any | None = None
    actual_value: Any | None = None
    message: str
    source_document: str | None = None
    xbrl_tag: str | None = None


class DiscrepancyReport(BaseModel):
    """Legacy cell-level discrepancy report (still written alongside ValidationReport)."""

    analysis_id: str
    ticker: str
    checks: list[ValidationCheck] = Field(default_factory=list)
    pass_count: int = 0
    warn_count: int = 0
    fail_count: int = 0
    summary: str = ""
