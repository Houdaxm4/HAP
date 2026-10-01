"""CLI:  python -m regression [check | list | snapshot | approve]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from regression import cases
from settings import outputs_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m regression", description="HAP golden-case regression checks")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="replay every golden case and compare with its baseline")
    sub.add_parser("list", help="list golden cases")
    snap = sub.add_parser("snapshot", help="freeze a stored analysis as a golden case")
    snap.add_argument("--analysis-id", required=True)
    snap.add_argument("--name", required=True)
    snap.add_argument("--ticker", required=True)
    snap.add_argument("--type", dest="analysis_type", required=True)
    snap.add_argument("--note", required=True, help="why this analysis is a good baseline")
    appr = sub.add_parser("approve", help="record that the analyst accepts this baseline as correct")
    appr.add_argument("name")
    appr.add_argument("--note", required=True)
    args = parser.parse_args(argv)

    if args.command == "list":
        for case_dir in cases.list_cases():
            meta = cases.read_case_meta(case_dir)
            print(f"{meta['name']:<22} {meta['ticker']:<6} {meta['analysis_type']:<16} approved={meta['approved']}")
        return 0
    if args.command == "snapshot":
        meta = cases.snapshot(
            storage_outputs=Path(outputs_dir()), analysis_id=args.analysis_id, name=args.name,
            ticker=args.ticker, analysis_type=args.analysis_type, note=args.note,
        )
        print(f"Saved {meta['name']} (replay reproduces stored outputs: {meta['replay_reproduces_stored_outputs']}). "
              "Not approved until you run: python -m regression approve NAME --note ...")
        return 0
    if args.command == "approve":
        meta = cases.approve(args.name, args.note)
        print(f"Approved {meta['name']}.")
        return 0

    results = cases.check_all()
    failed = [r for r in results if not r.passed]
    for r in results:
        flag = "PASS" if r.passed else "FAIL"
        suffix = "" if r.approved else "  (baseline not yet approved by the analyst)"
        print(f"{flag}  {r.name}{suffix}")
        for line in r.diffs[:12] + ([r.error] if r.error else []):
            print(f"      {line}")
    print(f"\n{len(results) - len(failed)}/{len(results)} cases unchanged.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
