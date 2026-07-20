"""One-shot Sprint 5.3 helper: assemble universe folders + manifests. Not analytical code."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UNIVERSE = ROOT / "universe"

COMPANIES: list[tuple[str, str, str, str]] = [
    # Technology
    ("AAPL", "Apple Inc.", "Technology", "Exceptional"),
    ("MSFT", "Microsoft Corporation", "Technology", "Exceptional"),
    ("GOOGL", "Alphabet Inc.", "Technology", "Excellent"),
    ("NVDA", "NVIDIA Corporation", "Technology", "Excellent"),
    ("META", "Meta Platforms Inc.", "Technology", "Excellent"),
    ("ORCL", "Oracle Corporation", "Technology", "Excellent"),
    ("ADBE", "Adobe Inc.", "Technology", "Excellent"),
    ("CRM", "Salesforce Inc.", "Technology", "Average"),
    ("IBM", "International Business Machines", "Technology", "Average"),
    ("INTC", "Intel Corporation", "Technology", "Weak"),
    ("SNAP", "Snap Inc.", "Technology", "Weak"),
    # Financials
    ("JPM", "JPMorgan Chase & Co.", "Financials", "Excellent"),
    ("BAC", "Bank of America Corporation", "Financials", "Average"),
    ("WFC", "Wells Fargo & Company", "Financials", "Average"),
    ("GS", "Goldman Sachs Group Inc.", "Financials", "Excellent"),
    ("MS", "Morgan Stanley", "Financials", "Excellent"),
    ("BLK", "BlackRock Inc.", "Financials", "Excellent"),
    ("SCHW", "Charles Schwab Corporation", "Financials", "Average"),
    ("C", "Citigroup Inc.", "Financials", "Average"),
    ("KEY", "KeyCorp", "Financials", "Weak"),
    ("NYCB", "New York Community Bancorp", "Financials", "Distressed"),
    # Consumer Staples
    ("PG", "Procter & Gamble Co.", "Consumer Staples", "Excellent"),
    ("KO", "Coca-Cola Company", "Consumer Staples", "Excellent"),
    ("PEP", "PepsiCo Inc.", "Consumer Staples", "Excellent"),
    ("WMT", "Walmart Inc.", "Consumer Staples", "Excellent"),
    ("COST", "Costco Wholesale Corporation", "Consumer Staples", "Exceptional"),
    ("CL", "Colgate-Palmolive Company", "Consumer Staples", "Excellent"),
    ("MDLZ", "Mondelez International", "Consumer Staples", "Average"),
    ("KHC", "Kraft Heinz Company", "Consumer Staples", "Average"),
    ("WBA", "Walgreens Boots Alliance", "Consumer Staples", "Weak"),
    ("GIS", "General Mills Inc.", "Consumer Staples", "Average"),
    # Consumer Discretionary
    ("AMZN", "Amazon.com Inc.", "Consumer Discretionary", "Excellent"),
    ("HD", "Home Depot Inc.", "Consumer Discretionary", "Excellent"),
    ("MCD", "McDonald's Corporation", "Consumer Discretionary", "Excellent"),
    ("NKE", "Nike Inc.", "Consumer Discretionary", "Average"),
    ("SBUX", "Starbucks Corporation", "Consumer Discretionary", "Average"),
    ("TJX", "TJX Companies Inc.", "Consumer Discretionary", "Excellent"),
    ("LOW", "Lowe's Companies Inc.", "Consumer Discretionary", "Excellent"),
    ("TSLA", "Tesla Inc.", "Consumer Discretionary", "Average"),
    ("CMG", "Chipotle Mexican Grill", "Consumer Discretionary", "Excellent"),
    ("AMC", "AMC Entertainment Holdings", "Consumer Discretionary", "Distressed"),
    # Industrials
    ("CAT", "Caterpillar Inc.", "Industrials", "Excellent"),
    ("GE", "GE Aerospace", "Industrials", "Excellent"),
    ("HON", "Honeywell International", "Industrials", "Excellent"),
    ("UNP", "Union Pacific Corporation", "Industrials", "Excellent"),
    ("DE", "Deere & Company", "Industrials", "Excellent"),
    ("BA", "Boeing Company", "Industrials", "Weak"),
    ("RTX", "RTX Corporation", "Industrials", "Average"),
    ("MMM", "3M Company", "Industrials", "Average"),
    ("UPS", "United Parcel Service", "Industrials", "Average"),
    ("FDX", "FedEx Corporation", "Industrials", "Average"),
    # Healthcare
    ("UNH", "UnitedHealth Group", "Healthcare", "Excellent"),
    ("LLY", "Eli Lilly and Company", "Healthcare", "Exceptional"),
    ("JNJ", "Johnson & Johnson", "Healthcare", "Excellent"),
    ("ABBV", "AbbVie Inc.", "Healthcare", "Excellent"),
    ("MRK", "Merck & Co. Inc.", "Healthcare", "Excellent"),
    ("PFE", "Pfizer Inc.", "Healthcare", "Average"),
    ("ISRG", "Intuitive Surgical", "Healthcare", "Excellent"),
    ("MRNA", "Moderna Inc.", "Healthcare", "Weak"),
    ("BMY", "Bristol-Myers Squibb", "Healthcare", "Average"),
    ("CVS", "CVS Health Corporation", "Healthcare", "Weak"),
    # Energy
    ("XOM", "Exxon Mobil Corporation", "Energy", "Excellent"),
    ("CVX", "Chevron Corporation", "Energy", "Excellent"),
    ("COP", "ConocoPhillips", "Energy", "Average"),
    ("OXY", "Occidental Petroleum", "Energy", "Average"),
    ("SLB", "Schlumberger Limited", "Energy", "Average"),
    ("DVN", "Devon Energy Corporation", "Energy", "Average"),
    ("HAL", "Halliburton Company", "Energy", "Average"),
    ("APA", "APA Corporation", "Energy", "Weak"),
    # Utilities
    ("NEE", "NextEra Energy Inc.", "Utilities", "Excellent"),
    ("DUK", "Duke Energy Corporation", "Utilities", "Average"),
    ("SO", "Southern Company", "Utilities", "Average"),
    ("AEP", "American Electric Power", "Utilities", "Average"),
    ("EXC", "Exelon Corporation", "Utilities", "Average"),
    ("D", "Dominion Energy Inc.", "Utilities", "Average"),
    ("SRE", "Sempra", "Utilities", "Average"),
    ("PCG", "PG&E Corporation", "Utilities", "Weak"),
    # REITs
    ("O", "Realty Income Corporation", "REITs", "Excellent"),
    ("AMT", "American Tower Corporation", "REITs", "Excellent"),
    ("PLD", "Prologis Inc.", "REITs", "Excellent"),
    ("SPG", "Simon Property Group", "REITs", "Average"),
    ("VICI", "VICI Properties Inc.", "REITs", "Average"),
    ("WELL", "Welltower Inc.", "REITs", "Average"),
    ("EQIX", "Equinix Inc.", "REITs", "Excellent"),
    ("ARE", "Alexandria Real Estate", "REITs", "Average"),
    # Telecommunications
    ("T", "AT&T Inc.", "Telecommunications", "Average"),
    ("VZ", "Verizon Communications", "Telecommunications", "Average"),
    ("TMUS", "T-Mobile US Inc.", "Telecommunications", "Excellent"),
    ("CMCSA", "Comcast Corporation", "Telecommunications", "Average"),
    ("CHTR", "Charter Communications", "Telecommunications", "Average"),
    ("TU", "TELUS Corporation", "Telecommunications", "Average"),
]


def main() -> None:
    assert 50 <= len(COMPANIES) <= 100, len(COMPANIES)
    UNIVERSE.mkdir(parents=True, exist_ok=True)
    (ROOT / "reports").mkdir(parents=True, exist_ok=True)
    (ROOT / "results").mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, str]] = []
    for ticker, company, sector, tier in COMPANIES:
        case_dir = UNIVERSE / ticker
        case_dir.mkdir(parents=True, exist_ok=True)
        manifest = {
            "company": company,
            "ticker": ticker,
            "industry": sector,
            "sector": sector,
            "sampling_quality_tier": tier,
            "notes": "Sampling label for campaign coverage only — not a HAP engine score.",
            "required_inputs": {
                "workbook": "workbook.xlsx or prefilled*.xlsx",
                "custom_run_filter": "custom_run_filter.csv (or .xlsx)",
                "manifest": "manifest.json (this file)",
            },
        }
        (case_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        rows.append(
            {
                "Ticker": ticker,
                "Company": company,
                "Sector": sector,
                "Sampling_Quality_Tier": tier,
                "Package_Path": str(case_dir),
            }
        )

    with (ROOT / "VALIDATION_UNIVERSE.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"companies={len(COMPANIES)}")
    print(f"sectors={dict(Counter(s for _, _, s, _ in COMPANIES))}")
    print(f"tiers={dict(Counter(t for _, _, _, t in COMPANIES))}")


if __name__ == "__main__":
    main()
