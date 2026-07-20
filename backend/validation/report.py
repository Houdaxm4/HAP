"""Write validation_results.csv and validation_summary.md."""

from __future__ import annotations

import csv
from pathlib import Path

from validation.runner import ValidationBatchResult, ValidationRow

CSV_COLUMNS = [
    "Company",
    "Ticker",
    "Engine Version",
    "Business Quality Score",
    "Business Quality Rating",
    "Investment Attractiveness Score",
    "Investment Attractiveness Rating",
    "Recommendation",
    "Fair Value",
    "Current Price",
    "Margin of Safety",
    "Expected Return",
    "Analysis Duration",
    "Status",
    "Failure Reason",
]


def write_results_csv(result: ValidationBatchResult, path: Path | None = None) -> Path:
    """Write ``validation_results.csv`` and return its path."""
    out = path or (result.output_dir / "validation_results.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in result.rows:
            writer.writerow(_row_to_csv(row))
    return out


def write_summary_md(result: ValidationBatchResult, path: Path | None = None) -> Path:
    """Write ``validation_summary.md`` and return its path."""
    out = path or (result.output_dir / "validation_summary.md")
    out.parent.mkdir(parents=True, exist_ok=True)

    total = len(result.rows)
    successes = [r for r in result.rows if r.status == "success"]
    failures = [r for r in result.rows if r.status != "success"]
    durations = [r.analysis_duration_sec for r in result.rows if r.analysis_duration_sec is not None]
    avg_runtime = (sum(durations) / len(durations)) if durations else 0.0

    missing_data = [r for r in result.rows if r.missing_data]
    incomplete = [r for r in result.rows if r.incomplete_module_coverage]

    lines = [
        "# HAP Validation Summary",
        "",
        f"- **Total companies:** {total}",
        f"- **Successful analyses:** {len(successes)}",
        f"- **Failed analyses:** {len(failures)}",
        f"- **Average runtime:** {avg_runtime:.2f}s",
        f"- **Companies missing data:** {len(missing_data)}",
        f"- **Companies with incomplete module coverage:** {len(incomplete)}",
        "",
    ]

    if failures:
        lines.append("## Failures")
        lines.append("")
        for row in failures:
            reason = row.failure_reason or "unknown"
            lines.append(f"- {row.company} ({row.ticker}): {reason}")
        lines.append("")

    if missing_data:
        lines.append("## Companies missing data")
        lines.append("")
        for row in missing_data:
            lines.append(f"- {row.company} ({row.ticker})")
        lines.append("")

    if incomplete:
        lines.append("## Companies with incomplete module coverage")
        lines.append("")
        for row in incomplete:
            modules = ", ".join(row.incomplete_modules) if row.incomplete_modules else "unspecified"
            lines.append(f"- {row.company} ({row.ticker}): {modules}")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def write_reports(result: ValidationBatchResult) -> tuple[Path, Path]:
    """Write CSV and markdown summary into the batch output directory."""
    csv_path = write_results_csv(result)
    md_path = write_summary_md(result)
    return csv_path, md_path


def _row_to_csv(row: ValidationRow) -> dict[str, str]:
    return {
        "Company": row.company,
        "Ticker": row.ticker,
        "Engine Version": row.engine_version,
        "Business Quality Score": _fmt(row.business_quality_score),
        "Business Quality Rating": row.business_quality_rating or "",
        "Investment Attractiveness Score": _fmt(row.investment_attractiveness_score),
        "Investment Attractiveness Rating": row.investment_attractiveness_rating or "",
        "Recommendation": row.recommendation or "",
        "Fair Value": _fmt(row.fair_value),
        "Current Price": _fmt(row.current_price),
        "Margin of Safety": _fmt(row.margin_of_safety),
        "Expected Return": _fmt(row.expected_return),
        "Analysis Duration": _fmt(row.analysis_duration_sec),
        "Status": row.status,
        "Failure Reason": row.failure_reason or "",
    }


def _fmt(value: float | None) -> str:
    if value is None:
        return ""
    return f"{value}"
