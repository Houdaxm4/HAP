"""CLI: build Workbook Manifest + docs for Industrial Template suite.

Usage (from backend/):

  python -m workbook_mapping
  python -m workbook_mapping --ticker AAPL
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
UNIVERSE = ROOT / "validation_campaign" / "universe"
OUT_DIR = ROOT / "docs" / "workbook_mapping"
MANIFEST_COPY = Path(__file__).resolve().parent / "manifests"


def _find_template(ticker: str) -> Path:
    folder = UNIVERSE / ticker
    matches = sorted(
        p
        for p in folder.glob("*.xlsx")
        if "Industrial Template" in p.name and not p.name.startswith("~$")
    )
    if not matches:
        raise FileNotFoundError(f"No Industrial Template for {ticker} in {folder}")
    return matches[0]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="M1.5 Workbook Classification Engine")
    parser.add_argument("--ticker", default="AAPL", help="Baseline ticker (default AAPL)")
    parser.add_argument(
        "--suite",
        default="AAPL,MSFT,AMZN,TJX",
        help="Comma-separated tickers for suite fingerprints",
    )
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="Docs output directory")
    args = parser.parse_args(argv)

    # Ensure backend root on path when executed as module
    backend = Path(__file__).resolve().parents[1]
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))

    from workbook_mapping.docs_writer import (
        write_architecture_md,
        write_classification_md,
        write_statistics_md,
    )
    from workbook_mapping.manifest_builder import ManifestBuilder

    suite_tickers = [t.strip().upper() for t in args.suite.split(",") if t.strip()]
    baseline = args.ticker.upper()
    baseline_path = _find_template(baseline)
    suite_paths = {t: _find_template(t) for t in suite_tickers}

    print(f"Building manifest baseline={baseline} path={baseline_path.name}")
    manifest = ManifestBuilder().build(
        baseline_path,
        baseline_ticker=baseline,
        suite_paths=suite_paths,
    )

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    MANIFEST_COPY.mkdir(parents=True, exist_ok=True)

    manifest_path = out / "Workbook_Manifest.json"
    payload = manifest.model_dump(mode="json")
    text = json.dumps(payload, indent=2)
    manifest_path.write_text(text, encoding="utf-8")
    (MANIFEST_COPY / "Workbook_Manifest.json").write_text(text, encoding="utf-8")

    write_classification_md(manifest, out / "Workbook_Classification.md")
    write_statistics_md(manifest, out / "Workbook_Statistics.md")
    write_architecture_md(out / "Workbook_Architecture.md")

    st = manifest.statistics
    print(f"Wrote {manifest_path} ({manifest_path.stat().st_size} bytes)")
    print(f"Sheets={st.worksheets} nonblank={st.used_cells_nonblank} writable={st.writable_cells}")
    print(f"Suite structure identical={manifest.suite_structure_identical}")
    print("Docs: Workbook_Classification.md, Workbook_Statistics.md, Workbook_Architecture.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
