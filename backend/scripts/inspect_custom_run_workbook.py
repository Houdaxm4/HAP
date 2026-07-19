#!/usr/bin/env python3
"""Inspect a production Bloomberg Custom_Run_Filter workbook and emit structure JSON."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from ingestion.production_workbook_profile import (  # noqa: E402
    PRODUCTION_AAPL_PROFILE,
    PRODUCTION_AAPL_WORKBOOK,
)
from ingestion.workbook_introspector import WorkbookIntrospector  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Reverse-engineer a Bloomberg Custom_Run_Filter workbook by dumping "
            "worksheet names, dimensions, and preview rows."
        )
    )
    parser.add_argument(
        "workbook",
        nargs="?",
        default=str(PRODUCTION_AAPL_WORKBOOK),
        help=(
            "Path to the production workbook (.xlsx). "
            f"Defaults to {PRODUCTION_AAPL_WORKBOOK}"
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        default=str(PRODUCTION_AAPL_PROFILE.with_suffix(".introspection.json")),
        help="Where to write the introspection JSON report.",
    )
    parser.add_argument(
        "--rows",
        type=int,
        default=25,
        help="Number of preview rows per worksheet.",
    )
    parser.add_argument(
        "--cols",
        type=int,
        default=12,
        help="Number of preview columns per worksheet.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    workbook_path = Path(args.workbook)
    output_path = Path(args.output)

    if not workbook_path.exists():
        print(
            "Production workbook not found.\n"
            f"Expected: {workbook_path}\n\n"
            "Commit the real AAPL Custom_Run_Filter workbook to that path, "
            "then rerun this script.",
            file=sys.stderr,
        )
        return 1

    introspector = WorkbookIntrospector(preview_rows=args.rows, preview_cols=args.cols)
    report = introspector.inspect_to_file(workbook_path, output_path)

    print(f"Workbook: {workbook_path}")
    print(f"Worksheets ({len(report.worksheets)}):")
    for sheet in report.worksheets:
        print(
            f"  - {sheet.name!r}: rows={sheet.max_row}, cols={sheet.max_column}, "
            f"non_empty_preview_rows={sheet.non_empty_row_count}"
        )
    print(f"\nWrote introspection report to: {output_path}")
    print(
        "\nNext step: translate this evidence into "
        f"{PRODUCTION_AAPL_PROFILE.name} and implement the parser against that profile."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
