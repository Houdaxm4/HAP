"""Validate parsed Bloomberg Custom_Run_Filter data."""

from __future__ import annotations

from ingestion.custom_run_schema import (
    REQUIRED_MARKET_DATA_FIELDS,
    REQUIRED_METADATA_FIELDS,
    REQUIRED_SECTIONS,
)
from ingestion.models.custom_run_data import (
    CustomRunData,
    CustomRunValidationIssue,
    CustomRunValidationReport,
)


class CustomRunValidationError(Exception):
    """Raised when Custom_Run validation fails with blocking errors."""


class CustomRunValidator:
    """Validate parsed CustomRunData after production-profile parsing."""

    def validate(
        self,
        data: CustomRunData,
        *,
        expected_ticker: str | None = None,
    ) -> CustomRunValidationReport:
        checks: list[CustomRunValidationIssue] = []

        checks.extend(self._check_sections(data))
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

    def _check_sections(self, data: CustomRunData) -> list[CustomRunValidationIssue]:
        checks: list[CustomRunValidationIssue] = []
        for section in REQUIRED_SECTIONS:
            if section not in data.raw_sections:
                checks.append(
                    CustomRunValidationIssue(
                        check="required_section",
                        status="fail",
                        message=f"Missing parsed section '{section}'.",
                        field=section,
                    )
                )
            else:
                checks.append(
                    CustomRunValidationIssue(
                        check="required_section",
                        status="pass",
                        message=f"Section '{section}' parsed.",
                        field=section,
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
                        message=f"Missing metadata field '{field}'.",
                        worksheet="metadata",
                        field=field,
                    )
                )
            else:
                checks.append(
                    CustomRunValidationIssue(
                        check="metadata_field",
                        status="pass",
                        message=f"Metadata field '{field}' present.",
                        worksheet="metadata",
                        field=field,
                    )
                )

        if expected_ticker and data.ticker and data.ticker != expected_ticker.upper():
            checks.append(
                CustomRunValidationIssue(
                    check="ticker_match",
                    status="fail",
                    message=(
                        f"Custom_Run ticker '{data.ticker}' does not match "
                        f"analysis ticker '{expected_ticker.upper()}'."
                    ),
                    worksheet="metadata",
                    field="Ticker",
                )
            )
        elif data.ticker:
            checks.append(
                CustomRunValidationIssue(
                    check="ticker_match",
                    status="pass",
                    message=f"Ticker '{data.ticker}' loaded.",
                    worksheet="metadata",
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
                        message=f"Market data field '{field}' is empty.",
                        worksheet="market_data",
                        field=field,
                    )
                )
            else:
                checks.append(
                    CustomRunValidationIssue(
                        check="market_data_field",
                        status="pass",
                        message=f"Market data field '{field}' present.",
                        worksheet="market_data",
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
                    message="No historical metrics were parsed.",
                    worksheet="historical_metrics",
                )
            )
            return checks

        checks.append(
            CustomRunValidationIssue(
                check="historical_metrics",
                status="pass",
                message=f"{len(data.historical_metrics)} historical metrics loaded.",
                worksheet="historical_metrics",
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
                    message="No proprietary metrics were parsed.",
                    worksheet="proprietary_metrics",
                )
            )
        else:
            checks.append(
                CustomRunValidationIssue(
                    check="proprietary_metrics",
                    status="pass",
                    message=f"{len(data.proprietary_metrics)} proprietary metrics loaded.",
                    worksheet="proprietary_metrics",
                )
            )

        if not data.valuation_metrics:
            checks.append(
                CustomRunValidationIssue(
                    check="valuation_metrics",
                    status="warn",
                    message="No valuation metrics were parsed.",
                    worksheet="valuation_metrics",
                )
            )
        else:
            checks.append(
                CustomRunValidationIssue(
                    check="valuation_metrics",
                    status="pass",
                    message=f"{len(data.valuation_metrics)} valuation metrics loaded.",
                    worksheet="valuation_metrics",
                )
            )

        if not data.quality_metrics:
            checks.append(
                CustomRunValidationIssue(
                    check="quality_metrics",
                    status="warn",
                    message="No quality metrics were parsed.",
                    worksheet="quality_metrics",
                )
            )
        else:
            checks.append(
                CustomRunValidationIssue(
                    check="quality_metrics",
                    status="pass",
                    message=f"{len(data.quality_metrics)} quality metrics loaded.",
                    worksheet="quality_metrics",
                )
            )
        return checks

    def _check_assumptions(self, data: CustomRunData) -> list[CustomRunValidationIssue]:
        checks: list[CustomRunValidationIssue] = []
        if not data.assumptions:
            checks.append(
                CustomRunValidationIssue(
                    check="assumptions",
                    status="warn",
                    message="No assumptions were parsed.",
                    worksheet="assumptions",
                )
            )
        else:
            checks.append(
                CustomRunValidationIssue(
                    check="assumptions",
                    status="pass",
                    message=f"{len(data.assumptions)} assumptions loaded.",
                    worksheet="assumptions",
                )
            )
        return checks
