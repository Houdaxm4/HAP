"""CLI:  python -m retention            (show the plan, delete nothing)
        python -m retention --apply    (delete exactly the planned runs)"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from retention.service import RetentionService
from settings import BACKEND_ROOT, storage_root


def _mb(size: int) -> str:
    return f"{size / 1_048_576:,.0f} MB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m retention", description="Keep only the latest run per company and analysis type")
    parser.add_argument("--apply", action="store_true", help="delete the planned runs (default: only show the plan)")
    args = parser.parse_args(argv)

    service = RetentionService(storage_root())
    plan = service.plan(regression_dir=Path(BACKEND_ROOT) / "regression" / "cases")
    print(f"KEEP ({len(plan.keep)}): the latest run of each company and analysis type")
    for item in plan.keep:
        print(f"  {item['ticker']:6} {item['type']:15} {item['id'][:8]}  {item['status']:10} {_mb(item['bytes']):>9}")
    print(f"\nPROTECTED ({len(plan.protected)}): older runs kept because something refers to them")
    for item in plan.protected:
        print(f"  {item['ticker']:6} {item['type']:15} {item['id'][:8]}  {_mb(item['bytes']):>9}  ({item['reason']})")
    print(f"\nDELETE ({len(plan.delete)}): frees {_mb(plan.bytes_freed)}")
    for item in plan.delete:
        print(f"  {item['ticker']:6} {item['type']:15} {item['id'][:8]}  {item['status']:10} {item['created_at'][:10]}  {_mb(item['bytes']):>9}")
    if not args.apply:
        print("\nNothing was deleted. Re-run with --apply to delete the runs listed under DELETE.")
        return 0
    removed = service.apply(plan)
    print(f"\nDeleted {len(removed)} run(s), freed about {_mb(plan.bytes_freed)}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
