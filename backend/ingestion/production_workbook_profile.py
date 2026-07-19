"""Evidence-based production layout profile for Bloomberg Custom_Run_Filter workbooks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

LayoutType = Literal["key_value", "time_series", "metric_value", "raw_grid"]

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"
PRODUCTION_FIXTURES_DIR = FIXTURES_DIR / "production"
PRODUCTION_AAPL_WORKBOOK = PRODUCTION_FIXTURES_DIR / "custom_run_filter_aapl.xlsx"
PRODUCTION_AAPL_PROFILE = PRODUCTION_FIXTURES_DIR / "custom_run_filter_aapl.profile.json"
PRODUCTION_TICKERS = ("AAPL", "MSFT", "AMZN", "TJX")


@dataclass(frozen=True)
class SheetSectionProfile:
    """Maps one semantic CustomRunData section to an actual worksheet layout."""

    section: str
    sheet_name: str
    layout: LayoutType
  # 1-based Excel coordinates
    label_column: int = 1
    value_column: int = 2
    header_row: int = 1
    data_start_row: int = 2
    period_start_column: int = 2
    evidence_tickers: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProductionWorkbookProfile:
    """Reverse-engineered contract for a verified production workbook family."""

    version: int
    evidence_tickers: tuple[str, ...]
    sections: tuple[SheetSectionProfile, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> ProductionWorkbookProfile:
        sections = tuple(
            SheetSectionProfile(
                section=str(item["section"]),
                sheet_name=str(item["sheet_name"]),
                layout=item["layout"],
                label_column=int(item.get("label_column", 1)),
                value_column=int(item.get("value_column", 2)),
                header_row=int(item.get("header_row", 1)),
                data_start_row=int(item.get("data_start_row", 2)),
                period_start_column=int(item.get("period_start_column", 2)),
                evidence_tickers=tuple(item.get("evidence_tickers", ())),
            )
            for item in payload.get("sections", [])
        )
        return cls(
            version=int(payload.get("version", 1)),
            evidence_tickers=tuple(payload.get("evidence_tickers", ())),
            sections=sections,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "evidence_tickers": list(self.evidence_tickers),
            "sections": [
                {
                    "section": section.section,
                    "sheet_name": section.sheet_name,
                    "layout": section.layout,
                    "label_column": section.label_column,
                    "value_column": section.value_column,
                    "header_row": section.header_row,
                    "data_start_row": section.data_start_row,
                    "period_start_column": section.period_start_column,
                    "evidence_tickers": list(section.evidence_tickers),
                }
                for section in self.sections
            ],
        }


def production_workbook_available() -> bool:
    return PRODUCTION_AAPL_WORKBOOK.exists()


def production_profile_available() -> bool:
    return PRODUCTION_AAPL_PROFILE.exists()


def load_production_profile(path: Path | None = None) -> ProductionWorkbookProfile:
    profile_path = path or PRODUCTION_AAPL_PROFILE
    if not profile_path.exists():
        raise FileNotFoundError(
            "Production Custom_Run_Filter profile is missing. "
            f"Expected profile at: {profile_path}. "
            "Commit the real AAPL workbook to "
            f"{PRODUCTION_AAPL_WORKBOOK}, run "
            "backend/scripts/inspect_custom_run_workbook.py, and commit the "
            "resulting profile JSON before implementing the parser."
        )
    payload = json.loads(profile_path.read_text(encoding="utf-8"))
    return ProductionWorkbookProfile.from_dict(payload)
