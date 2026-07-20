"""Sprint 5.3 input readiness check. Does not modify analytical engine code."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UNIVERSE = ROOT / "universe"
REPORTS = ROOT / "reports"

_WORKBOOK_EXT = {".xlsx", ".xlsm", ".xls"}
_FILTER_EXT = {".csv", ".xlsx", ".xlsm", ".xls"}


def _find_workbook(case_dir: Path) -> Path | None:
    preferred = (
        list(case_dir.glob("prefilled*.xlsx"))
        + list(case_dir.glob("workbook*.xlsx"))
        + list(case_dir.glob("*.xlsx"))
        + list(case_dir.glob("*.xlsm"))
        + list(case_dir.glob("*.xls"))
    )
    for path in preferred:
        if path.name.lower().startswith("custom_run"):
            continue
        if path.suffix.lower() in _WORKBOOK_EXT:
            return path
    return None


def _find_custom_run(case_dir: Path) -> Path | None:
    candidates = (
        list(case_dir.glob("custom_run_filter.*"))
        + list(case_dir.glob("custom_run.*"))
        + list(case_dir.glob("*custom_run*"))
    )
    for path in candidates:
        if path.is_file() and path.suffix.lower() in _FILTER_EXT:
            return path
    return None


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, str]] = []
    ready = 0
    incomplete = 0

    for case_dir in sorted(UNIVERSE.iterdir(), key=lambda p: p.name):
        if not case_dir.is_dir() or case_dir.name.startswith("."):
            continue
        manifest_path = case_dir / "manifest.json"
        company = case_dir.name
        ticker = case_dir.name
        sector = ""
        tier = ""
        if manifest_path.exists():
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
            company = str(payload.get("company") or company)
            ticker = str(payload.get("ticker") or ticker)
            sector = str(payload.get("sector") or payload.get("industry") or "")
            tier = str(payload.get("sampling_quality_tier") or "")

        workbook = _find_workbook(case_dir)
        custom_run = _find_custom_run(case_dir)
        missing: list[str] = []
        if workbook is None:
            missing.append("workbook")
        if custom_run is None:
            missing.append("custom_run_filter")
        if not manifest_path.exists():
            missing.append("manifest.json")

        status = "READY" if not missing else "INCOMPLETE"
        if status == "READY":
            ready += 1
        else:
            incomplete += 1

        rows.append(
            {
                "Ticker": ticker,
                "Company": company,
                "Sector": sector,
                "Sampling_Quality_Tier": tier,
                "Status": status,
                "Has_Workbook": "yes" if workbook else "no",
                "Has_Custom_Run_Filter": "yes" if custom_run else "no",
                "Has_Manifest": "yes" if manifest_path.exists() else "no",
                "Missing_Inputs": ";".join(missing),
                "Workbook_Path": str(workbook) if workbook else "",
                "Custom_Run_Path": str(custom_run) if custom_run else "",
            }
        )

    csv_path = REPORTS / "INPUT_READINESS.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()) if rows else ["Ticker"])
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Input Readiness Report — Sprint 5.3",
        "",
        "Generated before validation harness execution.",
        "",
        f"- **Total packages:** {len(rows)}",
        f"- **READY (workbook + custom_run_filter present):** {ready}",
        f"- **INCOMPLETE:** {incomplete}",
        "",
        "## Required inputs per company package",
        "",
        "Each `validation_campaign/universe/<TICKER>/` directory must contain:",
        "",
        "1. `workbook.xlsx` (or `prefilled*.xlsx` / other `.xlsx`/`.xlsm`/`.xls`)",
        "2. `custom_run_filter.csv` (or `.xlsx` custom_run filter)",
        "3. `manifest.json` (company / ticker / sector metadata)",
        "",
        "## Incomplete packages",
        "",
        "| Ticker | Company | Sector | Missing |",
        "|--------|---------|--------|---------|",
    ]
    for row in rows:
        if row["Status"] != "READY":
            lines.append(
                f"| {row['Ticker']} | {row['Company']} | {row['Sector']} | {row['Missing_Inputs']} |"
            )

    lines.extend(
        [
            "",
            "## Execution gate",
            "",
            (
                "**Harness execution against analytical outputs cannot proceed for incomplete packages.**"
                if ready == 0
                else f"**{ready} package(s) are READY for harness execution.**"
            ),
            "",
            f"Detail CSV: `{csv_path.as_posix()}`",
            "",
        ]
    )
    md_path = REPORTS / "INPUT_READINESS_REPORT.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"ready={ready} incomplete={incomplete}")
    print(f"wrote {csv_path}")
    print(f"wrote {md_path}")


if __name__ == "__main__":
    main()
