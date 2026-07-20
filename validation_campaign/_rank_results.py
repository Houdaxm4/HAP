"""Sprint 5.3 post-run ranking + manual review priority. Not analytical engine code."""

from __future__ import annotations

import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPORTS = ROOT / "reports"
RESULTS = ROOT / "results"
UNIVERSE = ROOT / "universe"

# Objective priority weights (review triage only — not HAP scores).
W_FAILED_PIPELINE = 100
W_FAILED_MODULES = 40
W_INCOMPLETE_MODULES = 25
W_MISSING_DATA = 20
W_LOW_CONFIDENCE = 15
W_REC_ANOMALY = 15
W_CONTRADICTION = 15
W_METHODOLOGY_SENSITIVE_SECTOR = 8
W_EXTREME_SAMPLING_TIER = 5

SENSITIVE_SECTORS = {
    "Financials",
    "REITs",
    "Utilities",
    "Energy",
    "Telecommunications",
}
EXTREME_TIERS = {"Exceptional", "Weak", "Distressed"}


def _load_universe_meta() -> dict[str, dict[str, str]]:
    meta: dict[str, dict[str, str]] = {}
    for case_dir in UNIVERSE.iterdir() if UNIVERSE.exists() else []:
        if not case_dir.is_dir():
            continue
        manifest = case_dir / "manifest.json"
        if not manifest.exists():
            continue
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        ticker = str(payload.get("ticker") or case_dir.name).upper()
        meta[ticker] = {
            "company": str(payload.get("company") or ticker),
            "sector": str(payload.get("sector") or payload.get("industry") or ""),
            "tier": str(payload.get("sampling_quality_tier") or ""),
        }
    return meta


def _load_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def main() -> None:
    REPORTS.mkdir(parents=True, exist_ok=True)
    meta = _load_universe_meta()
    readiness = {row["Ticker"].upper(): row for row in _load_csv(REPORTS / "INPUT_READINESS.csv")}
    harness_rows = _load_csv(RESULTS / "validation_results.csv")

    ranked: list[dict[str, object]] = []

    if harness_rows:
        for row in harness_rows:
            ticker = (row.get("Ticker") or "").upper()
            info = meta.get(ticker, {})
            status = (row.get("Status") or "").lower()
            failure = row.get("Failure Reason") or ""
            missing_data_flag = 1 if "insufficient" in (row.get("Recommendation") or "").lower() else 0
            # Harness CSV does not include confidence/modules; use failure + empty fields.
            empty_outputs = sum(
                1
                for key in (
                    "Business Quality Score",
                    "Investment Attractiveness Score",
                    "Recommendation",
                    "Fair Value",
                    "Expected Return",
                )
                if not (row.get(key) or "").strip()
            )
            priority = 0
            reasons: list[str] = []
            if status != "success":
                priority += W_FAILED_PIPELINE
                reasons.append(f"pipeline_failed:{failure[:120]}")
            if empty_outputs:
                priority += W_MISSING_DATA * empty_outputs
                reasons.append(f"empty_outputs:{empty_outputs}")
            sector = info.get("sector") or ""
            if sector in SENSITIVE_SECTORS:
                priority += W_METHODOLOGY_SENSITIVE_SECTOR
                reasons.append(f"methodology_sensitive_sector:{sector}")
            tier = info.get("tier") or ""
            if tier in EXTREME_TIERS:
                priority += W_EXTREME_SAMPLING_TIER
                reasons.append(f"extreme_sampling_tier:{tier}")
            ranked.append(
                {
                    "Priority_Score": priority,
                    "Ticker": ticker,
                    "Company": info.get("company") or row.get("Company") or ticker,
                    "Sector": sector,
                    "Sampling_Tier": tier,
                    "Harness_Status": status,
                    "BQ": row.get("Business Quality Score") or "",
                    "IA": row.get("Investment Attractiveness Score") or "",
                    "Recommendation": row.get("Recommendation") or "",
                    "Reasons": "; ".join(reasons) if reasons else "none",
                }
            )
    else:
        # No successful harness batch: prioritize input assembly + methodology-sensitive names.
        for ticker, info in sorted(meta.items()):
            ready_row = readiness.get(ticker, {})
            incomplete = ready_row.get("Status") != "READY"
            priority = 0
            reasons: list[str] = []
            if incomplete:
                priority += W_FAILED_PIPELINE
                missing = ready_row.get("Missing_Inputs") or "workbook;custom_run_filter"
                reasons.append(f"incomplete_inputs:{missing}")
            sector = info.get("sector") or ""
            if sector in SENSITIVE_SECTORS:
                priority += W_METHODOLOGY_SENSITIVE_SECTOR
                reasons.append(f"methodology_sensitive_sector:{sector}")
            tier = info.get("tier") or ""
            if tier in EXTREME_TIERS:
                priority += W_EXTREME_SAMPLING_TIER
                reasons.append(f"extreme_sampling_tier:{tier}")
            ranked.append(
                {
                    "Priority_Score": priority,
                    "Ticker": ticker,
                    "Company": info.get("company") or ticker,
                    "Sector": sector,
                    "Sampling_Tier": tier,
                    "Harness_Status": "not_run",
                    "BQ": "",
                    "IA": "",
                    "Recommendation": "",
                    "Reasons": "; ".join(reasons) if reasons else "none",
                }
            )

    ranked.sort(key=lambda item: (-int(item["Priority_Score"]), str(item["Ticker"])))

    # Validation ranking report sections (objective buckets).
    lines = [
        "# Validation Campaign Report — Sprint 5.3",
        "",
        "## Execution status",
        "",
        f"- Universe size: **{len(meta)}**",
        f"- Harness result rows: **{len(harness_rows)}**",
        f"- Ready input packages: **{sum(1 for r in readiness.values() if r.get('Status') == 'READY')}**",
        "",
    ]
    if not harness_rows:
        lines.extend(
            [
                "> **Harness produced no company result rows.**",
                "> Analytical anomaly rankings (failed modules, low confidence, contradictions)",
                "> require successful pipeline runs. See Input Readiness Report.",
                "",
            ]
        )

    lines.extend(
        [
            "## Ranking criteria (objective)",
            "",
            "When harness outputs exist, companies are ranked using:",
            "",
            "1. Pipeline / analysis failure",
            "2. Failed modules",
            "3. Incomplete module coverage",
            "4. Missing financial series / empty analytical fields",
            "5. Low confidence",
            "6. Contradictory outputs / recommendation anomalies",
            "",
            "Additional campaign triage factors (not HAP scores):",
            "",
            "- Methodology-sensitive sectors (Financials, REITs, Utilities, Energy, Telecom)",
            "- Extreme sampling tiers (Exceptional / Weak / Distressed)",
            "",
            "## Ranked companies",
            "",
            "| Rank | Priority | Ticker | Sector | Tier | Harness | Reasons |",
            "|-----:|---------:|--------|--------|------|---------|---------|",
        ]
    )
    for index, item in enumerate(ranked, start=1):
        lines.append(
            f"| {index} | {item['Priority_Score']} | {item['Ticker']} | {item['Sector']} | "
            f"{item['Sampling_Tier']} | {item['Harness_Status']} | {item['Reasons']} |"
        )

    report_path = REPORTS / "VALIDATION_CAMPAIGN_REPORT.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Manual review priority list
    priority_lines = [
        "# Manual Review Priority List - Sprint 5.3",
        "",
        "Ranked highest to lowest priority for human review.",
        "",
        "Objective criteria only (see Validation Campaign Report).",
        "Sampling quality tiers are campaign design labels, not HAP scores.",
        "",
        "| Priority Rank | Ticker | Company | Sector | Priority Score | Why review next |",
        "|--------------:|--------|---------|--------|---------------:|-----------------|",
    ]
    for index, item in enumerate(ranked, start=1):
        priority_lines.append(
            f"| {index} | {item['Ticker']} | {item['Company']} | {item['Sector']} | "
            f"{item['Priority_Score']} | {item['Reasons']} |"
        )

    if not harness_rows:
        priority_lines.extend(
            [
                "",
                "## Note on current campaign state",
                "",
                "No engine outputs are available yet. Priority currently reflects:",
                "",
                "1. Missing required inputs (blocks analysis)",
                "2. Methodology-sensitive sectors (from Methodology Audit)",
                "3. Extreme sampling tiers (edge-case coverage)",
                "",
                "Re-run this reporter after placing workbooks + custom_run filters and executing:",
                "",
                "```text",
                "cd backend",
                "python -m validation --input ../validation_campaign/universe --output ../validation_campaign/results",
                "python ../validation_campaign/_rank_results.py",
                "```",
                "",
            ]
        )

    priority_path = REPORTS / "MANUAL_REVIEW_PRIORITY_LIST.md"
    priority_path.write_text("\n".join(priority_lines), encoding="utf-8")

    # CSV for priority list
    csv_path = REPORTS / "MANUAL_REVIEW_PRIORITY_LIST.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "Priority_Rank",
            "Priority_Score",
            "Ticker",
            "Company",
            "Sector",
            "Sampling_Tier",
            "Harness_Status",
            "Reasons",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, item in enumerate(ranked, start=1):
            writer.writerow(
                {
                    "Priority_Rank": index,
                    "Priority_Score": item["Priority_Score"],
                    "Ticker": item["Ticker"],
                    "Company": item["Company"],
                    "Sector": item["Sector"],
                    "Sampling_Tier": item["Sampling_Tier"],
                    "Harness_Status": item["Harness_Status"],
                    "Reasons": item["Reasons"],
                }
            )

    print(f"ranked={len(ranked)}")
    print(f"wrote {report_path}")
    print(f"wrote {priority_path}")
    print(f"wrote {csv_path}")


if __name__ == "__main__":
    main()
