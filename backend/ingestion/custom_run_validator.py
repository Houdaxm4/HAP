"""Validate Bloomberg Custom_Run_Filter workbooks per HAP v1 specification."""

from __future__ import annotations

from ingestion.custom_run_schema import (
    REQUIRED_MARKET_DATA_FIELDS,
    REQUIRED_METADATA_FIELDS,
    REQUIRED_WORKSHEETS,
)
from ingestion.models.custom_run_data import (
    CustomRunData,
    CustomRunValidationIssue,
    CustomRunValidationReport,
)


class CustomRunValidationError(Exception):
    """Raised when Custom_Run validation fails with blocking errors."""


class CustomRunValidator:
    """Validate parsed CustomRunData against the HAP v1 ingestion specification."""

    def validate(
        self,
        data: CustomRunData,
        *,
        expected_ticker: str | None = None,
    ) -> CustomRunValidationReport:
        checks: list[CustomRunValidationIssue] = []

        checks.extend(self._check_worksheets(data))
        checks.extend(self._check_metadata(data, expected_ticker))
        checks.extend(self._check_market_data(data))
        checks.extend(self._check_historical_metrics(data))
        checks.extend(self._check_metric_sections(data))
        checks.extend(self._check_assumptions(data))

        pass_count = sum(1 for c in checks if c.status == "pass")
        warn_count = sum(1 for c in checks if c.status == "warn")
        fail_count = sum(1 for c in checks if c.status == "fail")
        is_valid = fail_count == 0

        if fail_count:
            summary = f"Custom_Run validation failed: {fail_count} errors, {warn_count} warnings."
        elif warn_count:
            summary = f"Custom_Run validation passed with {warn_count} warnings."
        else:
            summary = f"Custom_Run validation passed ({pass_count} checks)."

        return CustomRunValidationReport(
            source_filename=data.source_filename,
            ticker=data.ticker or expected_ticker or "",
            is_valid=is_valid,
            checks=checks,
            pass_count=pass_count,
            warn_count=warn_count,
            fail_count=fail_count,
            summary=summary,
        )

    def validate_or_raise(
        self,
        data: CustomRunData,
        *,
        expected_ticker: str | None = None,
    ) -> CustomRunValidationReport:
        report = self.validate(data, expected_ticker=expected_ticker)
        if not report.is_valid:
            failures = [c.message for c in report.checks if c.status == "fail"]
            raise CustomRunValidationError("; ".join(failures[:3]))
        return report

    def _check_worksheets(self, data: CustomRunData) -> list[CustomRunValidationIssue]:
        checks: list[CustomRunValidationIssue] = []
        found = {name.strip().lower() for name in data.worksheets_found}
        for required in REQUIRED_WORKSHEETS:
            if required.lower() not in found and not any(
                required.lower() in sheet.lower() for sheet in data.worksheets_found
            ):
                checks.append(
                    CustomRunValidationIssue(
                        check="required_worksheet",
                        status="fail",
                        message=f"Missing required worksheet '{required}'.",
                        worksheet=required,
                    )
                )
            else:
                checks.append(
                    CustomRunValidationIssue(
                        check="required_worksheet",
                        status="pass",
                        message=f"Worksheet '{required}' present.",
                        worksheet=required,
                    )
                )
        return checks

    def _check_metadata(
        self,
        data: CustomRunData,
        expected_ticker: str | None,
    ) -> list[CustomRunValidationIssue]:
        checks: list[CustomRunValidationIssue] = []
        for field in REQUIRED_METADATA_FIELDS:
            value = data.metadata.get(field)
            if not value:
                checks.append(
                    CustomRunValidationIssue(
                        check="metadata_field",
                        status="fail",
                        message=f"Missing required metadata field '{field}'.",
                        worksheet="Metadata",
                        field=field,
                    )
                )
            else:
                checks.append(
                    CustomRunValidationIssue(
                        check="metadata_field",
                        status="pass",
                        message=f"Metadata field '{field}' present.",
                        worksheet="Metadata",
                        field=field,
                    )
                )

        if expected_ticker and data.ticker and data.ticker != expected_ticker.upper():
            checks.append(
                CustomRunValidationIssue(
                    check="ticker_consistency",
                    status="fail",
                    message=(
                        f"Custom_Run ticker '{data.ticker}' does not match "
                        f"analysis ticker '{expected_ticker.upper()}'."
                    ),
                    worksheet="Metadata",
                    field="Ticker",
                )
            )
        elif data.ticker:
            checks.append(
                CustomRunValidationIssue(
                    check="ticker_consistency",
                    status="pass",
                    message=f"Ticker '{data.ticker}' is consistent.",
                    worksheet="Metadata",
                    field="Ticker",
                )
            )
        return checks

    def _check_market_data(self, data: CustomRunData) -> list[CustomRunValidationIssue]:
        checks: list[CustomRunValidationIssue] = []
        for field in REQUIRED_MARKET_DATA_FIELDS:
            value = data.market_data.get(field)
            if value is None:
                checks.append(
                    CustomRunValidationIssue(
                        check="market_data_field",
                        status="warn",
                        message=f"Market data field '{field}' is missing.",
                        worksheet="Market Data",
                        field=field,
                    )
                )
            elif isinstance(value, str):
                checks.append(
                    CustomRunValidationIssue(
                        check="market_data_field",
                        status="warn",
                        message=f"Market data field '{field}' is not numeric.",
                        worksheet="Market Data",
                        field=field,
                    )
                )
            else:
                checks.append(
                    CustomRunValidationIssue(
                        check="market_data_field",
                        status="pass",
                        message=f"Market data field '{field}' present.",
                        worksheet="Market Data",
                        field=field,
                    )
                )
        return checks

    def _check_historical_metrics(self, data: CustomRunData) -> list[CustomRunValidationIssue]:
        checks: list[CustomRunValidationIssue] = []
        if not data.historical_metrics:
            checks.append(
                CustomRunValidationIssue(
                    check="historical_metrics",
                    status="fail",
                    message="Historical Metrics section contains no data rows.",
                    worksheet="Historical Metrics",
                )
            )
            return checks

        populated_periods: set[str] = set()
        for series in data.historical_metrics:
            populated_periods.update(
                period for period, value in series.values.items() if value is not None
            )

        if len(populated_periods) < 1:
            checks.append(
                CustomRunValidationIssue(
                    check="historical_metrics",
                    status="fail",
                    message="Historical Metrics has no populated period values.",
                    worksheet="Historical Metrics",
                )
            )
        else:
            checks.append(
                CustomRunValidationIssue(
                    check="historical_metrics",
                    status="pass",
                    message=f"Historical Metrics covers {len(populated_periods)} period(s).",
                    worksheet="Historical Metrics",
                )
            )
        return checks

    def _check_metric_sections(self, data: CustomRunData) -> list[CustomRunValidationIssue]:
        checks: list[CustomRunValidationIssue] = []
        if not data.proprietary_metrics:
            checks.append(
                CustomRunValidationIssue(
                    check="proprietary_metrics",
                    status="warn",
                    message="Proprietary Metrics section is empty.",
                    worksheet="Proprietary Metrics",
                )
            )
        else:
            checks.append(
                CustomRunValidationIssue(
                    check="proprietary_metrics",
                    status="pass",
                    message=f"{len(data.proprietary_metrics)} proprietary metrics loaded.",
                    worksheet="Proprietary Metrics",
                )
            )

        if not data.valuation_metrics:
            checks.append(
                CustomRunValidationIssue(
                    check="valuation_metrics",
                    status="warn",
                    message="Valuation Metrics section is empty.",
                    worksheet="Valuation Metrics",
                )
            )
        else:
            checks.append(
                CustomRunValidationIssue(
                    check="valuation_metrics",
                    status="pass",
                    message=f"{len(data.valuation_metrics)} valuation metrics loaded.",
                    worksheet="Valuation Metrics",
                )
            )
        return checks

    def _check_assumptions(self, data: CustomRunData) -> list[CustomRunValidationIssue]:
        if not data.assumptions:
            return [
                CustomRunValidationIssue(
                    check="assumptions",
                    status="warn",
                    message="Assumptions section is empty.",
                    worksheet="Assumptions",
                )
            ]
        return [
            CustomRunValidationIssue(
                check="assumptions",
                status="pass",
                message=f"{len(data.assumptions)} assumptions loaded.",
                worksheet="Assumptions",
            )
        ]
