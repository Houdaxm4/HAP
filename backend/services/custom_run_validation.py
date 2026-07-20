"""Validate Bloomberg Custom_Run_Filter workbooks against HAP v1 product rules."""

from __future__ import annotations

from models.custom_run import CustomRunData
from models.validation import DiscrepancyReport, ValidationCheck

REQUIRED_SUMMARY_FIELDS = (
    "Company",
    "Ticker",
    "Current Price (Live Price)",
)

REQUIRED_META_FIELDS = (
    "Company",
    "Ticker",
)

MIN_PERIODS = 20
MIN_SERIES = 10


class CustomRunValidationService:
    """Structural and field-level validation for imported CustomRunData."""

    def validate(self, analysis_id: str, data: CustomRunData) -> DiscrepancyReport:
        checks: list[ValidationCheck] = []

        def _add(
            *,
            check_type: str,
            status: str,
            message: str,
            concept: str,
        ) -> None:
            checks.append(
                ValidationCheck(
                    cell_ref=f"CustomRun!{concept}",
                    worksheet=data.ticker_sheet_name,
                    cell="B",
                    concept=concept,
                    period="n/a",
                    check_type=check_type,  # type: ignore[arg-type]
                    status=status,  # type: ignore[arg-type]
                    message=message,
                )
            )

        # Worksheet / structure
        if not data.ticker_sheet_name:
            _add(
                check_type="missing_value",
                status="fail",
                message="Ticker worksheet name is missing.",
                concept="ticker_sheet",
            )
        else:
            _add(
                check_type="value_match",
                status="pass",
                message=f"Ticker worksheet '{data.ticker_sheet_name}' present.",
                concept="ticker_sheet",
            )

        if data.summary_field_count < 50:
            _add(
                check_type="missing_value",
                status="fail",
                message=f"Summary sheet has only {data.summary_field_count} fields (expected ~111).",
                concept="Summary",
            )
        else:
            _add(
                check_type="value_match",
                status="pass",
                message=f"Summary sheet loaded with {data.summary_field_count} fields.",
                concept="Summary",
            )

        for field in REQUIRED_META_FIELDS:
            if data.metadata.get(field) is None and data.summary.get(field) is None:
                _add(
                    check_type="missing_value",
                    status="fail",
                    message=f"Required metadata field '{field}' is missing.",
                    concept=field,
                )
            else:
                _add(
                    check_type="value_match",
                    status="pass",
                    message=f"Metadata field '{field}' present.",
                    concept=field,
                )

        for field in REQUIRED_SUMMARY_FIELDS:
            value = data.summary.get(field)
            if value is None:
                _add(
                    check_type="missing_value",
                    status="warn" if field == "Current Price (Live Price)" else "fail",
                    message=f"Required summary field '{field}' is missing.",
                    concept=field,
                )
            else:
                _add(
                    check_type="value_match",
                    status="pass",
                    message=f"Summary field '{field}' present.",
                    concept=field,
                )

        if data.period_count < MIN_PERIODS:
            _add(
                check_type="missing_value",
                status="fail",
                message=f"Historical period count is {data.period_count} (minimum {MIN_PERIODS}).",
                concept="periods",
            )
        else:
            _add(
                check_type="value_match",
                status="pass",
                message=f"Historical period count is {data.period_count}.",
                concept="periods",
            )

        if data.series_count < MIN_SERIES:
            _add(
                check_type="missing_value",
                status="fail",
                message=f"Only {data.series_count} historical series found (minimum {MIN_SERIES}).",
                concept="historical_metrics",
            )
        else:
            _add(
                check_type="value_match",
                status="pass",
                message=f"Loaded {data.series_count} historical series.",
                concept="historical_metrics",
            )

        # Malformed numeric checks for key proprietary fields
        for field in ("Current PE10", "WACC", "Final Score", "Current Price (Live Price)"):
            value = data.scalar(field)
            if value is None:
                continue
            if isinstance(value, str):
                _add(
                    check_type="impossible_value",
                    status="warn",
                    message=f"Field '{field}' has non-numeric value {value!r}.",
                    concept=field,
                )
                continue
            try:
                float(value)
                _add(
                    check_type="value_match",
                    status="pass",
                    message=f"Field '{field}' is numeric.",
                    concept=field,
                )
            except (TypeError, ValueError):
                _add(
                    check_type="impossible_value",
                    status="warn",
                    message=f"Field '{field}' could not be interpreted as a number.",
                    concept=field,
                )

        # Metadata consistency
        meta_ticker = str(data.metadata.get("Ticker") or "").upper()
        summary_ticker = str(data.summary.get("Ticker") or "").upper()
        if meta_ticker and summary_ticker and meta_ticker != summary_ticker:
            _add(
                check_type="inconsistency",
                status="fail",
                message=f"Ticker mismatch: metadata={meta_ticker} summary={summary_ticker}.",
                concept="Ticker",
            )
        elif data.ticker and summary_ticker and data.ticker != summary_ticker:
            _add(
                check_type="inconsistency",
                status="warn",
                message=f"Parsed ticker {data.ticker} differs from Summary ticker {summary_ticker}.",
                concept="Ticker",
            )
        else:
            _add(
                check_type="value_match",
                status="pass",
                message="Ticker metadata is consistent.",
                concept="Ticker",
            )

        pass_count = sum(1 for c in checks if c.status == "pass")
        warn_count = sum(1 for c in checks if c.status == "warn")
        fail_count = sum(1 for c in checks if c.status == "fail")
        if fail_count:
            summary = f"{fail_count} failed, {warn_count} warnings, {pass_count} passed."
        elif warn_count:
            summary = f"Custom_Run validation completed with {warn_count} warnings and {pass_count} passed checks."
        else:
            summary = f"All {pass_count} Custom_Run checks passed."

        return DiscrepancyReport(
            analysis_id=analysis_id,
            ticker=data.ticker,
            checks=checks,
            pass_count=pass_count,
            warn_count=warn_count,
            fail_count=fail_count,
            summary=summary,
        )
