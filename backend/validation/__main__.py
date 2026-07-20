"""CLI entry point: python -m validation --input DIR --output DIR."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="HAP validation harness — batch-run company workbooks through the pipeline.",
    )
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        type=Path,
        help="Directory of company packages (each with workbook + custom_run filter).",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        type=Path,
        help="Directory for validation_results.csv, validation_summary.md, and failure log.",
    )
    parser.add_argument(
        "--analysis-type",
        default="Validation",
        help="analysis_type stored on each created analysis (default: Validation).",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Console log level (default: INFO).",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    # Ensure backend package imports resolve when launched as ``python -m validation``.
    backend_root = Path(__file__).resolve().parent.parent
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    from validation.report import write_reports
    from validation.runner import run_validation

    result = run_validation(
        args.input,
        args.output,
        analysis_type=args.analysis_type,
    )
    csv_path, md_path = write_reports(result)

    successes = sum(1 for row in result.rows if row.status == "success")
    failures = sum(1 for row in result.rows if row.status != "success")
    logging.getLogger(__name__).info(
        "Validation complete: %s success, %s failed. Wrote %s and %s",
        successes,
        failures,
        csv_path,
        md_path,
    )
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
