"""CLI for M2 mapping specification.

  cd backend
  python -m workbook_mapping.m2_cli
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "docs" / "workbook_mapping" / "Workbook_Manifest.json"
DEFAULT_OUT = ROOT / "docs" / "workbook_mapping"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M2 CFM↔Workbook mapping specification")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)

    backend = Path(__file__).resolve().parents[1]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from workbook_mapping.mapping_builder import MappingSpecError, build_mapping_specification, write_mapping_docs

    if not args.manifest.exists():
        print(f"Manifest not found: {args.manifest}", file=sys.stderr)
        return 1
    try:
        spec = build_mapping_specification(args.manifest)
    except MappingSpecError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    write_mapping_docs(spec, args.out)
    c = spec.coverage
    print(f"Mappings: {len(spec.mappings)}")
    print(
        f"CFM coverage: {c.mapped_cfm_metrics}/{c.total_cfm_metrics} ({c.cfm_coverage_pct}%)"
    )
    print(
        f"Writable cells: {c.total_writable_workbook_cells} "
        f"(mapped={c.mapped_writable_cells}, empty={c.intentionally_empty_writable_cells}, "
        f"unsupported={c.unsupported_writable_cells}, future={c.future_feature_writable_cells}, "
        f"unexplained={c.unexplained_writable_cells})"
    )
    print(f"Wrote docs under {args.out}")
    return 0 if c.unexplained_writable_cells == 0 else 3


if __name__ == "__main__":
    raise SystemExit(main())
