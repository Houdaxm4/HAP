"""Internal prefilled workbook fill plan — implementation detail only."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from ingestion.models.company_financial_model import CompanyFinancialModel, SecStatementValue
from ingestion.models.custom_run_data import MetricSeries
from models.workbook_schema import WorkbookStructure
from services.workbook_service import WorkbookService


@dataclass
class InternalFillTarget:
    """One cell to populate, derived internally — not a user-facing mapping file."""

    worksheet: str
    cell: str
    concept: str
    period: str
    value: Any | None
    status: str = "pending"
    source: str = "sec"
    xbrl_tag: str | None = None
    source_document: str | None = None
    filing_type: str | None = None
    filing_date: str | None = None
    accession_number: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    failure_reason: str | None = None


class PrefilledWorkbookMapper:
    """
    Derive fill targets by matching workbook labels and period headers.

    Users never provide worksheet/cell mapping files. This mapper inspects
    the prefilled workbook structure and aligns it with the financial model.
    """

    def __init__(self, workbook_service: WorkbookService | None = None) -> None:
        self.workbook_service = workbook_service or WorkbookService()

    def build_fill_plan(
        self,
        structure: WorkbookStructure,
        model: CompanyFinancialModel,
    ) -> list[InternalFillTarget]:
        label_index = self._build_label_index(structure)
        targets: list[InternalFillTarget] = []

        targets.extend(self._targets_from_sec(label_index, model.sec_statement_values))
        targets.extend(self._targets_from_series(label_index, model.historical_metrics, "custom_run_historical"))
        targets.extend(self._targets_from_series(label_index, model.proprietary_metrics, "custom_run_proprietary"))
        targets.extend(self._targets_from_series(label_index, model.valuation_metrics, "custom_run_valuation"))
        targets.extend(self._targets_from_market_data(label_index, model.market_data))

        return targets

    def _targets_from_sec(
        self,
        label_index: dict[str, list[tuple[str, str, str | None]]],
        sec_values: list[SecStatementValue],
    ) -> list[InternalFillTarget]:
        targets: list[InternalFillTarget] = []
        for fact in sec_values:
            key = self._normalize_label(fact.concept)
            for worksheet, cell, period_header in label_index.get(key, []):
                if period_header and not self._periods_match(period_header, fact.period):
                    continue
                targets.append(
                    InternalFillTarget(
                        worksheet=worksheet,
                        cell=cell,
                        concept=fact.concept,
                        period=fact.period,
                        value=fact.value,
                        status="filled",
                        source="sec",
                        xbrl_tag=fact.xbrl_tag,
                        confidence=0.9,
                        reasoning=f"SEC fact {fact.xbrl_tag} for {fact.period}.",
                    )
                )
        return targets

    def _targets_from_series(
        self,
        label_index: dict[str, list[tuple[str, str, str | None]]],
        metrics: dict[str, dict[str, Any]],
        source: str,
    ) -> list[InternalFillTarget]:
        targets: list[InternalFillTarget] = []
        for metric, period_values in metrics.items():
            key = self._normalize_label(metric)
            for period, value in period_values.items():
                if value is None:
                    continue
                for worksheet, cell, period_header in label_index.get(key, []):
                    if period_header and not self._periods_match(period_header, period):
                        continue
                    targets.append(
                        InternalFillTarget(
                            worksheet=worksheet,
                            cell=cell,
                            concept=metric,
                            period=period,
                            value=value,
                            status="filled",
                            source=source,
                            confidence=0.95,
                            reasoning=f"Custom_Run proprietary metric '{metric}' ({period}).",
                        )
                    )
        return targets

    def _targets_from_market_data(
        self,
        label_index: dict[str, list[tuple[str, str, str | None]]],
        market_data: dict[str, Any],
    ) -> list[InternalFillTarget]:
        targets: list[InternalFillTarget] = []
        for field, value in market_data.items():
            if value is None:
                continue
            key = self._normalize_label(field)
            for worksheet, cell, _ in label_index.get(key, []):
                targets.append(
                    InternalFillTarget(
                        worksheet=worksheet,
                        cell=cell,
                        concept=field,
                        period="current",
                        value=value,
                        status="filled",
                        source="custom_run_market",
                        confidence=0.95,
                        reasoning=f"Custom_Run market data '{field}'.",
                    )
                )
        return targets

    def _build_label_index(
        self,
        structure: WorkbookStructure,
    ) -> dict[str, list[tuple[str, str, str | None]]]:
        """
        Index prefilled workbook labels to (worksheet, target_cell, period_header).

        Supports layouts:
        - Label in column A, value in column B (no period header)
        - Label in column A, period headers in row 1, values in matching columns
        """
        index: dict[str, list[tuple[str, str, str | None]]] = {}
        for sheet in structure.worksheets:
            period_headers: dict[int, str] = {}
            for cell in sheet.cells:
                col_match = re.match(r"([A-Z]+)(\d+)", cell.address)
                if not col_match:
                    continue
                col, row = col_match.group(1), int(col_match.group(2))
                if row == 1 and col != "A" and cell.value:
                    period_headers[self._col_to_index(col)] = str(cell.value).strip()

            for cell in sheet.cells:
                col_match = re.match(r"([A-Z]+)(\d+)", cell.address)
                if not col_match:
                    continue
                col, row = col_match.group(1), int(col_match.group(2))
                if col != "A" or row <= 1 or not cell.value:
                    continue
                label = self._normalize_label(str(cell.value))
                value_col_index = 2  # default column B
                value_col = self._index_to_col(value_col_index)
                period_header = period_headers.get(value_col_index)
                index.setdefault(label, []).append((sheet.name, f"{value_col}{row}", period_header))

                for col_index, header in period_headers.items():
                    value_col = self._index_to_col(col_index)
                    index.setdefault(label, []).append((sheet.name, f"{value_col}{row}", header))
        return index

    @staticmethod
    def _normalize_label(label: str) -> str:
        return re.sub(r"[^a-z0-9]", "", label.lower())

    @staticmethod
    def _periods_match(header: str, period: str) -> bool:
        h = header.upper().replace(" ", "")
        p = period.upper().replace(" ", "")
        return h == p or h in p or p in h

    @staticmethod
    def _col_to_index(col: str) -> int:
        index = 0
        for char in col:
            index = index * 26 + (ord(char) - ord("A") + 1)
        return index

    @staticmethod
    def _index_to_col(index: int) -> str:
        result = ""
        while index > 0:
            index, remainder = divmod(index - 1, 26)
            result = chr(ord("A") + remainder) + result
        return result
