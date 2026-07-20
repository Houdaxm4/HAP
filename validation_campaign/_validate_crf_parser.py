"""Validate CustomRunService against production Custom_Run_Filter workbooks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(r"C:\Users\G\HAP\backend")
sys.path.insert(0, str(BACKEND))

from services.custom_run_service import CustomRunService  # noqa: E402
from services.custom_run_validation import CustomRunValidationService  # noqa: E402

ROOT = Path(r"C:\Users\G\HAP\validation_campaign\universe")
TICKERS = ["AAPL", "MSFT", "AMZN", "TJX"]
OUT = Path(r"C:\Users\G\HAP\validation_campaign\reports\CRF_PARSER_VALIDATION.json")

# Evidence anchors from CRF_REVERSE_ENGINEERING.md
EXPECTED = {
    "date_row": 15,
    "fiscal_quarter_row": 16,
    "fiscal_year_row": 146,
    "period_width": 102,
    "summary_fields": 111,
    "scalar_start": 158,
    "trailer_start": 265,
}


def find_crf(ticker: str) -> Path:
    hits = [
        p
        for p in (ROOT / ticker).glob("Custom_Run_Filter*.xlsx")
        if not p.name.startswith("~$")
    ]
    return hits[0]


def main() -> int:
    parser = CustomRunService()
    validator = CustomRunValidationService()
    results = []
    all_ok = True

    for ticker in TICKERS:
        path = find_crf(ticker)
        data = parser.parse(path, path.name)
        report = validator.validate(f"validate-{ticker}", data)
        fails = [c for c in report.checks if c.status == "fail"]
        warns = [c for c in report.checks if c.status == "warn"]

        checks = {
            "ticker_matches": data.ticker == ticker,
            "sheet_is_ticker": data.ticker_sheet_name == ticker,
            "summary_field_count_111": data.summary_field_count == EXPECTED["summary_fields"],
            "period_count_102": data.period_count == EXPECTED["period_width"],
            "has_company": bool(data.company),
            "has_live_price": data.summary.get("Current Price (Live Price)") is not None,
            "series_count_gt_10": data.series_count >= 10,
            "no_validation_fails": len(fails) == 0,
        }
        ok = all(checks.values())
        all_ok = all_ok and ok

        results.append(
            {
                "ticker": ticker,
                "source": path.name,
                "ok": ok,
                "checks": checks,
                "parsed": {
                    "ticker": data.ticker,
                    "company": data.company,
                    "ticker_sheet_name": data.ticker_sheet_name,
                    "period_count": data.period_count,
                    "series_count": data.series_count,
                    "summary_field_count": data.summary_field_count,
                    "meta_keys": sorted(data.metadata.keys()),
                    "scalar_count": len(data.scalars),
                    "market_keys": sorted(data.market_data.keys()),
                    "valuation_keys": sorted(data.valuation_metrics.keys()),
                    "quality_keys": sorted(data.quality_metrics.keys()),
                    "live_price": data.summary.get("Current Price (Live Price)"),
                    "wacc_assumption": data.assumptions.get("wacc"),
                    "first_fq": data.periods.fiscal_quarters[0] if data.periods.fiscal_quarters else None,
                    "last_fq": data.periods.fiscal_quarters[-1] if data.periods.fiscal_quarters else None,
                },
                "validation": {
                    "fail_count": report.fail_count,
                    "warn_count": report.warn_count,
                    "pass_count": report.pass_count,
                    "fails": [c.message for c in fails],
                    "warns": [c.message for c in warns],
                },
            }
        )
        print(
            f"{ticker}: ok={ok} periods={data.period_count} series={data.series_count} "
            f"summary={data.summary_field_count} "
            f"pass={report.pass_count} fails={report.fail_count} warns={report.warn_count}"
        )

    OUT.write_text(json.dumps({"expected_anchors": EXPECTED, "results": results}, indent=2), encoding="utf-8")
    print(f"Wrote {OUT}")
    print("ALL_OK" if all_ok else "FAILURES")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
