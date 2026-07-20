"""Builder that maps validated workbook cells into CompanyFinancialModel."""

from __future__ import annotations

from typing import Any

from canonical_model.company import (
    CompanyFinancialModel,
    MarketData,
    ValuationInputs,
)
from canonical_model.primitives import FinancialPoint, FinancialSeries, LineItemProvenance
from canonical_model.statements import BalanceSheet, CashFlowStatement, IncomeStatement
from canonical_model.workbook_metrics import WorkbookMetric

# (statement_attr, field_attr, concept needles)
_CONCEPT_ROUTES: list[tuple[str, str, tuple[str, ...]]] = [
    ("income_statement", "revenue", ("revenue", "sales", "total revenue")),
    ("income_statement", "cost_of_revenue", ("cost of revenue", "cost of goods", "cogs")),
    ("income_statement", "gross_profit", ("gross profit", "gross income")),
    ("income_statement", "operating_income", ("operating income", "operating profit", "opinc")),
    ("income_statement", "ebit", ("ebit",)),
    ("income_statement", "ebitda", ("ebitda",)),
    ("income_statement", "interest_expense", ("interest expense", "finance costs")),
    ("income_statement", "tax_expense", ("tax expense", "income tax")),
    ("income_statement", "net_income", ("net income", "netincomeloss", "profit for the period")),
    ("income_statement", "diluted_eps", ("diluted eps", "earnings per share diluted", "eps diluted")),
    ("balance_sheet", "cash", ("cash and cash equivalents", "cash")),
    ("balance_sheet", "current_assets", ("current assets",)),
    ("balance_sheet", "total_assets", ("total assets",)),
    ("balance_sheet", "current_liabilities", ("current liabilities",)),
    ("balance_sheet", "total_liabilities", ("total liabilities",)),
    ("balance_sheet", "total_debt", ("total debt", "long-term debt", "borrowings")),
    (
        "balance_sheet",
        "shareholders_equity",
        ("shareholders equity", "stockholders equity", "total equity", "equity"),
    ),
    ("balance_sheet", "invested_capital", ("invested capital",)),
    ("cash_flow_statement", "operating_cash_flow", ("operating cash flow", "cash from operations", "cfo")),
    ("cash_flow_statement", "capital_expenditures", ("capital expenditures", "capex", "purchases of ppe")),
    ("cash_flow_statement", "free_cash_flow", ("free cash flow", "fcf")),
    ("cash_flow_statement", "dividends", ("dividends paid", "dividends")),
    ("cash_flow_statement", "share_repurchases", ("share repurchase", "buyback", "treasury stock purchases")),
    ("cash_flow_statement", "financing_cash_flow", ("financing cash flow", "cash from financing")),
    ("cash_flow_statement", "investing_cash_flow", ("investing cash flow", "cash from investing")),
]

_MARKET_ROUTES: dict[str, tuple[str, ...]] = {
    "share_price": ("share price", "stock price", "price"),
    "shares_outstanding": ("shares outstanding", "diluted shares", "basic shares"),
    "market_cap": ("market cap", "market capitalization"),
    "enterprise_value": ("enterprise value", "ev"),
    "beta": ("beta",),
    "dividend_yield": ("dividend yield",),
}

_VALUATION_ROUTES: dict[str, tuple[str, ...]] = {
    "risk_free_rate": ("risk free rate", "risk-free rate"),
    "equity_risk_premium": ("equity risk premium", "erp"),
    "cost_of_equity": ("cost of equity", "ke"),
    "cost_of_debt": ("cost of debt", "kd"),
    "tax_rate": ("tax rate", "effective tax rate"),
    "wacc": ("wacc", "weighted average cost of capital"),
    "terminal_growth_rate": ("terminal growth", "perpetuity growth"),
    "net_debt": ("net debt",),
}

# Workbook metric concept needles → normalized metric code.
# These are analyst formula / ratio cells — never statement facts.
_WORKBOOK_METRIC_ROUTES: list[tuple[str, tuple[str, ...]]] = [
    ("ROIC", ("roic", "return on invested capital")),
    ("ROE", ("roe", "return on equity")),
    ("ROA", ("roa", "return on assets")),
    ("GROSS_MARGIN", ("gross margin",)),
    ("OPERATING_MARGIN", ("operating margin", "ebit margin")),
    ("NET_MARGIN", ("net margin",)),
    ("REV_CAGR", ("revenue cagr", "rev cagr")),
    ("EPS_CAGR", ("eps cagr", "diluted eps cagr")),
    ("FCF_CAGR", ("fcf cagr", "free cash flow cagr")),
    ("OI_CAGR", ("operating income cagr", "oi cagr")),
    ("BV_CAGR", ("book value cagr", "bv cagr")),
    ("REV_YOY", ("revenue yoy", "revenue growth yoy")),
    ("GROWTH_STABILITY", ("growth stability",)),
    ("ORGANIC_REV_CAGR", ("organic revenue cagr", "organic rev cagr")),
    ("FCF_MARGIN", ("fcf margin", "free cash flow margin")),
    ("CASH_CONVERSION", ("cash conversion",)),
    ("OWNER_EARNINGS", ("owner earnings",)),
    ("CURRENT_RATIO", ("current ratio",)),
    ("QUICK_RATIO", ("quick ratio",)),
    ("DEBT_TO_EQUITY", ("debt to equity", "debt/equity", "d/e")),
    ("DEBT_TO_EBITDA", ("debt to ebitda", "debt/ebitda")),
    ("INTEREST_COVERAGE", ("interest coverage",)),
    ("INTRINSIC_VALUE", ("intrinsic value", "iv per share")),
    ("MARGIN_OF_SAFETY", ("margin of safety", "mos")),
    ("ENTERPRISE_VALUE", ("enterprise value", "ev implied")),
    ("EQUITY_VALUE", ("equity value",)),
    ("FAIR_VALUE", ("fair value", "fair value per share")),
    ("WACC", ("wacc", "weighted average cost of capital")),
    ("TERMINAL_GROWTH", ("terminal growth", "perpetuity growth")),
    ("EXPECTED_IRR", ("expected irr", "irr")),
    ("EXPECTED_CAGR", ("expected cagr", "expected return cagr")),
]


class CompanyFinancialModelBuilder:
    """
    Convert validated workbook cell payloads into a CompanyFinancialModel.

    Populates historical ``FinancialSeries`` structures. Never returns Excel
    workbook objects.
    """

    def build(
        self,
        *,
        analysis_id: str,
        ticker: str,
        company: str | None = None,
        analysis_type: str | None = None,
        reporting_currency: str = "USD",
        provenance_report: Any | None = None,
        discrepancy_report: Any | None = None,
        workbook_cells: list[dict[str, Any]] | None = None,
        market_data: MarketData | dict[str, Any] | None = None,
        valuation_inputs: ValuationInputs | dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        company_facts: dict[str, Any] | None = None,
        custom_run: Any | None = None,
    ) -> CompanyFinancialModel:
        cells = list(workbook_cells or [])
        if not cells and company_facts is not None:
            from services.sec_statement_extractor import extract_statement_cells_from_sec

            cells = extract_statement_cells_from_sec(company_facts)
        if not cells:
            cells = self._cells_from_artifacts(provenance_report, discrepancy_report)

        model = CompanyFinancialModel(
            analysis_id=analysis_id,
            ticker=ticker.upper(),
            company=company,
            analysis_type=analysis_type,
            reporting_currency=reporting_currency,
            income_statement=IncomeStatement(currency=reporting_currency),
            balance_sheet=BalanceSheet(currency=reporting_currency),
            cash_flow_statement=CashFlowStatement(currency=reporting_currency),
            market_data=self._coerce_market(market_data, reporting_currency),
            valuation_inputs=self._coerce_valuation(valuation_inputs, reporting_currency),
            metadata=dict(metadata or {}),
        )

        unmapped: list[dict[str, Any]] = []
        mapped_count = 0
        workbook_metric_count = 0
        for cell in cells:
            if self._map_workbook_metric(model, cell, default_currency=reporting_currency):
                mapped_count += 1
                workbook_metric_count += 1
                continue
            mapped = self._map_cell(model, cell, default_currency=reporting_currency)
            if mapped:
                mapped_count += 1
            else:
                # Market/valuation scalars still count as mapped when handled below.
                unmapped.append(
                    {
                        "concept": cell.get("concept"),
                        "period": cell.get("period"),
                        "cell_ref": cell.get("cell_ref"),
                    }
                )

        still_unmapped: list[dict[str, Any]] = []
        for cell in unmapped:
            # Retry full cell payload from original list for scalar mapping.
            original = next(
                (
                    item
                    for item in cells
                    if item.get("cell_ref") == cell.get("cell_ref")
                    and item.get("concept") == cell.get("concept")
                    and item.get("period") == cell.get("period")
                ),
                cell,
            )
            market_hit = self._map_scalar_concept(model.market_data, original, _MARKET_ROUTES)
            valuation_hit = self._map_scalar_concept(
                model.valuation_inputs, original, _VALUATION_ROUTES
            )
            if market_hit or valuation_hit:
                mapped_count += 1
            else:
                still_unmapped.append(cell)

        # Also allow market / valuation concepts that were statement-mapped already.
        for cell in cells:
            self._map_scalar_concept(model.market_data, cell, _MARKET_ROUTES)
            self._map_scalar_concept(model.valuation_inputs, cell, _VALUATION_ROUTES)

        if custom_run is not None:
            applied = self._apply_custom_run(model, custom_run, default_currency=reporting_currency)
            mapped_count += applied

        model.refresh_periods()
        model.metadata["mapped_cell_count"] = mapped_count
        model.metadata["workbook_metric_count"] = workbook_metric_count
        model.metadata["unmapped_cells"] = still_unmapped
        model.metadata["series_point_count"] = self._count_points(model)
        if custom_run is not None:
            model.metadata["custom_run_ticker"] = getattr(custom_run, "ticker", None)
            model.metadata["custom_run_series_count"] = getattr(custom_run, "series_count", None)
            model.metadata["custom_run_source"] = getattr(custom_run, "source_filename", None)
        return model

    def _apply_custom_run(
        self,
        model: CompanyFinancialModel,
        custom_run: Any,
        *,
        default_currency: str,
    ) -> int:
        """
        Import CustomRunData market / valuation / proprietary analytics.

        Statement facts remain SEC-sourced. Proprietary metrics are stored for
        comparison (workbook_metrics / metadata) and never recalculated.
        """
        applied = 0
        price = custom_run.scalar("Current Price (Live Price)")
        if isinstance(price, (int, float)) and model.market_data.share_price is None:
            model.market_data.share_price = float(price)
            applied += 1
        mkt_cap = custom_run.scalar("Current Market Capitalization")
        if isinstance(mkt_cap, (int, float)) and model.market_data.market_cap is None:
            model.market_data.market_cap = float(mkt_cap)
            applied += 1
        ev = custom_run.scalar("Current Enterprise Value (not-diluted)")
        if isinstance(ev, (int, float)) and model.market_data.enterprise_value is None:
            model.market_data.enterprise_value = float(ev)
            applied += 1
        div_yield = custom_run.scalar("Current Dividend Yield")
        if isinstance(div_yield, (int, float)) and model.market_data.dividend_yield is None:
            model.market_data.dividend_yield = float(div_yield)
            applied += 1

        wacc = custom_run.scalar("WACC") or (custom_run.assumptions or {}).get("wacc")
        if isinstance(wacc, (int, float)) and model.valuation_inputs.wacc is None:
            model.valuation_inputs.wacc = float(wacc)
            applied += 1

        # Shares from historical series (latest), Custom_Run is in millions.
        shares_series = None
        if hasattr(custom_run, "series_for"):
            shares_series = custom_run.series_for("Shares Outstanding Diluted Average (MM)")
        if (
            shares_series is not None
            and model.market_data.shares_outstanding is None
        ):
            for value in reversed(shares_series.values):
                if value is not None:
                    model.market_data.shares_outstanding = float(value) * 1_000_000.0
                    applied += 1
                    break

        # Proprietary metrics → workbook_metrics for comparison only.
        proprietary_map = {
            "Current PE10": ("PE10", "Current PE10"),
            "Current E10": ("E10", "Current E10"),
            "Final Score": ("FINAL_SCORE", "Final Score"),
            "Franchise Power": ("FRANCHISE_POWER", "Franchise Power"),
            "ROCE": ("ROCE", "ROCE"),
            "Current Graham Instrinsic Value": ("INTRINSIC_VALUE", "Current Graham Intrinsic Value"),
            "Expected Return @ Current Price": ("EXPECTED_CAGR", "Expected Return @ Current Price"),
        }
        for source_key, (code, name) in proprietary_map.items():
            value = custom_run.scalar(source_key)
            if not isinstance(value, (int, float)):
                continue
            model.workbook_metrics.add(
                WorkbookMetric(
                    code=code,
                    name=name,
                    value=float(value),
                    unit="ratio" if abs(float(value)) <= 10 else "USD",
                    is_formula=False,
                    source="custom_run_filter",
                    confidence=0.95,
                )
            )
            applied += 1

        model.metadata["custom_run_proprietary"] = {
            "valuation": dict(getattr(custom_run, "valuation_metrics", {}) or {}),
            "quality": dict(getattr(custom_run, "quality_metrics", {}) or {}),
            "market": dict(getattr(custom_run, "market_data", {}) or {}),
        }
        return applied

    def _map_workbook_metric(
        self,
        model: CompanyFinancialModel,
        cell: dict[str, Any],
        *,
        default_currency: str,
    ) -> bool:
        """Route analyst formula / ratio cells to ``workbook_metrics`` only."""
        if not self._is_workbook_metric_cell(cell):
            return False
        metric = self._workbook_metric_from_cell(cell, default_currency=default_currency)
        if metric is None:
            return False
        model.workbook_metrics.add(metric)
        return True

    @staticmethod
    def _is_workbook_metric_cell(cell: dict[str, Any]) -> bool:
        if cell.get("is_workbook_metric") is True:
            return True
        if str(cell.get("metric_origin") or "").lower() == "workbook":
            return True
        if cell.get("is_formula") is True and cell.get("period"):
            concept = str(cell.get("concept") or "").lower()
            if CompanyFinancialModelBuilder._match_workbook_metric_code(concept):
                return True
        return False

    @staticmethod
    def _match_workbook_metric_code(concept: str) -> str | None:
        key = " ".join(concept.lower().split())
        ranked = sorted(
            _WORKBOOK_METRIC_ROUTES,
            key=lambda route: max(len(needle) for needle in route[1]),
            reverse=True,
        )
        for code, needles in ranked:
            if any(needle == key or needle in key for needle in needles):
                return code
        explicit = str(concept or "").strip().upper().replace(" ", "_")
        if explicit and any(code == explicit for code, _ in _WORKBOOK_METRIC_ROUTES):
            return explicit
        return None

    @staticmethod
    def _workbook_metric_from_cell(
        cell: dict[str, Any],
        *,
        default_currency: str,
    ) -> WorkbookMetric | None:
        concept = str(cell.get("concept") or "").strip()
        code = (
            str(cell.get("metric_code") or "").strip().upper()
            or CompanyFinancialModelBuilder._match_workbook_metric_code(concept)
        )
        if not code:
            return None
        period = str(cell.get("period") or "").strip() or None
        try:
            value = float(cell.get("value"))
        except (TypeError, ValueError):
            return None
        unit = str(cell.get("unit") or cell.get("currency") or "ratio")
        confidence = cell.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None
        return WorkbookMetric(
            code=code,
            name=concept or code,
            value=value,
            period=period,
            unit=unit,
            is_formula=bool(cell.get("is_formula", True)),
            cell_ref=cell.get("cell_ref"),
            formula=cell.get("formula"),
            source=str(cell.get("source") or cell.get("source_document") or "workbook"),
            confidence=confidence,
            module_hint=cell.get("module_hint"),
            provenance=LineItemProvenance(
                concept=concept or code,
                cell_ref=cell.get("cell_ref"),
                source_document=cell.get("source_document"),
                xbrl_tag=cell.get("xbrl_tag"),
                worksheet=cell.get("worksheet"),
                filing_type=cell.get("filing_type"),
                accession_number=cell.get("accession_number"),
            ),
        )

    def _map_cell(
        self,
        model: CompanyFinancialModel,
        cell: dict[str, Any],
        *,
        default_currency: str,
    ) -> bool:
        point = self._financial_point_from_cell(cell, default_currency=default_currency)
        if point is None:
            return False
        route = self._match_statement_route(str(cell.get("concept") or ""))
        if route is None:
            return False
        statement_name, field_name = route
        statement = getattr(model, statement_name)
        series: FinancialSeries = getattr(statement, field_name)
        series.upsert(point)
        if not series.currency:
            series.currency = point.currency
        return True

    @staticmethod
    def _financial_point_from_cell(
        cell: dict[str, Any],
        *,
        default_currency: str,
    ) -> FinancialPoint | None:
        period = str(cell.get("period") or "").strip()
        if not period:
            return None
        try:
            value = float(cell.get("value"))
        except (TypeError, ValueError):
            return None

        currency = str(cell.get("currency") or cell.get("unit") or default_currency)
        source = cell.get("source") or cell.get("source_document")
        audited = bool(cell.get("audited", False))
        if cell.get("filing_type") in {"10-K", "20-F", "Annual Report"}:
            audited = True if cell.get("audited") is None else audited

        confidence = cell.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None

        return FinancialPoint(
            period=period,
            value=value,
            currency=currency,
            source=str(source) if source else None,
            confidence=confidence,
            audited=audited,
            provenance=LineItemProvenance(
                concept=str(cell.get("concept") or "") or None,
                cell_ref=cell.get("cell_ref"),
                source_document=cell.get("source_document"),
                xbrl_tag=cell.get("xbrl_tag"),
                worksheet=cell.get("worksheet"),
                filing_type=cell.get("filing_type"),
                accession_number=cell.get("accession_number"),
            ),
        )

    @staticmethod
    def _match_statement_route(concept: str) -> tuple[str, str] | None:
        key = " ".join(concept.lower().split())
        ranked = sorted(
            _CONCEPT_ROUTES,
            key=lambda route: max(len(needle) for needle in route[2]),
            reverse=True,
        )
        for statement, field, needles in ranked:
            if any(needle == key or needle in key for needle in needles):
                if field == "cash" and "flow" in key:
                    continue
                if field == "total_assets" and "current" in key:
                    continue
                if field == "shareholders_equity" and key in {"return on equity", "roe"}:
                    continue
                if CompanyFinancialModelBuilder._match_workbook_metric_code(key):
                    continue
                return statement, field
        return None

    @staticmethod
    def _map_scalar_concept(
        target: MarketData | ValuationInputs,
        cell: dict[str, Any],
        routes: dict[str, tuple[str, ...]],
    ) -> bool:
        key = " ".join(str(cell.get("concept") or "").lower().split())
        try:
            value = float(cell.get("value"))
        except (TypeError, ValueError):
            return False
        for field_name, needles in routes.items():
            if any(needle == key or needle in key for needle in needles):
                setattr(target, field_name, value)
                return True
        return False

    def _cells_from_artifacts(
        self,
        provenance_report: Any | None,
        discrepancy_report: Any | None,
    ) -> list[dict[str, Any]]:
        provenance = _as_dict(provenance_report)
        discrepancy = _as_dict(discrepancy_report)
        failed_refs = {
            check.get("cell_ref")
            for check in discrepancy.get("checks", [])
            if check.get("status") == "fail"
        }

        cells: list[dict[str, Any]] = []
        for entry in provenance.get("entries", []):
            if entry.get("status") != "filled":
                continue
            if entry.get("cell_ref") in failed_refs:
                continue
            cells.append(
                {
                    "concept": entry.get("concept"),
                    "period": entry.get("period"),
                    "value": entry.get("value"),
                    "currency": entry.get("unit") or entry.get("currency") or "USD",
                    "unit": entry.get("unit") or "USD",
                    "source": entry.get("source_document"),
                    "source_document": entry.get("source_document"),
                    "cell_ref": entry.get("cell_ref"),
                    "xbrl_tag": entry.get("xbrl_tag"),
                    "confidence": entry.get("confidence"),
                    "audited": entry.get("audited"),
                    "filing_type": entry.get("filing_type"),
                    "accession_number": entry.get("accession_number"),
                    "worksheet": entry.get("worksheet"),
                }
            )
        return cells

    @staticmethod
    def _count_points(model: CompanyFinancialModel) -> int:
        total = 0
        for statement in (
            model.income_statement,
            model.balance_sheet,
            model.cash_flow_statement,
        ):
            for field_name in type(statement).model_fields:
                value = getattr(statement, field_name)
                if isinstance(value, FinancialSeries):
                    total += len(value)
        return total

    @staticmethod
    def _coerce_market(
        value: MarketData | dict[str, Any] | None,
        currency: str,
    ) -> MarketData:
        if value is None:
            return MarketData(currency=currency)
        if isinstance(value, MarketData):
            return value
        payload = dict(value)
        payload.setdefault("currency", currency)
        return MarketData.model_validate(payload)

    @staticmethod
    def _coerce_valuation(
        value: ValuationInputs | dict[str, Any] | None,
        currency: str,
    ) -> ValuationInputs:
        if value is None:
            return ValuationInputs(currency=currency)
        if isinstance(value, ValuationInputs):
            return value
        payload = dict(value)
        payload.setdefault("currency", currency)
        return ValuationInputs.model_validate(payload)


def build_company_financial_model(**kwargs: Any) -> CompanyFinancialModel:
    """Convenience wrapper around CompanyFinancialModelBuilder.build."""
    return CompanyFinancialModelBuilder().build(**kwargs)


def _as_dict(value: Any | None) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump()
    raise TypeError(f"Unsupported artifact type: {type(value)!r}")
