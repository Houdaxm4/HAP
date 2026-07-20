"""Deterministic expected return math for the Expected Return module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from analysis_engine.utils import mean, safe_div
from analysis_engine.valuation_engine import (
    AssumptionRecord,
    ValuationComputeResult,
    _register_assumption,
    _resolve_fcf_series,
    compute_valuation,
)
from canonical_model import CompanyFinancialModel

DEFAULT_HOLDING_PERIOD = 5
DEFAULT_SP500_EXPECTED_RETURN = 0.08
GROWTH_CAP = 0.30
GROWTH_FLOOR = -0.15
RETURN_CAP = 0.50
RETURN_FLOOR = -0.50


@dataclass
class ScenarioReturn:
    name: str
    expected_cagr: float | None = None
    expected_irr: float | None = None
    valuation_reversion: float | None = None
    fair_value_per_share: float | None = None


@dataclass
class ExpectedReturnComputeResult:
    assumptions: list[AssumptionRecord] = field(default_factory=list)
    dividend_yield: float | None = None
    buyback_yield: float | None = None
    eps_growth_contribution: float | None = None
    fcf_growth_contribution: float | None = None
    growth_contribution: float | None = None
    valuation_reversion: float | None = None
    multiple_expansion: float | None = None
    expected_cagr: float | None = None
    expected_irr: float | None = None
    holding_period_years: int = DEFAULT_HOLDING_PERIOD
    fair_value_base: float | None = None
    fair_value_low: float | None = None
    fair_value_high: float | None = None
    share_price: float | None = None
    margin_of_safety: float | None = None
    sp500_expected_return: float = DEFAULT_SP500_EXPECTED_RETURN
    peer_expected_return: float | None = None
    scenarios: dict[str, ScenarioReturn] = field(default_factory=dict)
    valuation_available: bool = False
    valuation_method_count: int = 0
    valuation_methods_used: list[str] = field(default_factory=list)
    confidence_penalty: float = 0.0


def compute_expected_return(
    model: CompanyFinancialModel,
    valuation: ValuationComputeResult | None = None,
) -> ExpectedReturnComputeResult:
    """Estimate forward shareholder return from price, valuation, growth, and yields.

    When ``valuation`` is provided (preferred in full engine runs), it is reused
    and not recomputed. Standalone module tests may omit it.
    """
    result = ExpectedReturnComputeResult()
    metadata = dict(model.metadata or {})
    er_meta = metadata.get("expected_return") if isinstance(metadata.get("expected_return"), dict) else {}
    evidence = metadata.get("assumption_evidence") or er_meta.get("assumption_evidence") or {}
    if not isinstance(evidence, dict):
        evidence = {}

    valuation_result = valuation if valuation is not None else compute_valuation(model)
    result.fair_value_base = valuation_result.fair_value_base
    result.fair_value_low = valuation_result.fair_value_low
    result.fair_value_high = valuation_result.fair_value_high
    result.share_price = valuation_result.share_price
    result.margin_of_safety = valuation_result.margin_of_safety
    result.valuation_available = valuation_result.fair_value_base is not None
    result.valuation_method_count = valuation_result.method_count
    result.valuation_methods_used = list(valuation_result.methods.keys())

    md = model.market_data
    income = model.income_statement
    cfs = model.cash_flow_statement

    result.holding_period_years = int(
        er_meta.get("holding_period_years")
        or model.valuation_inputs.forecast_years
        or DEFAULT_HOLDING_PERIOD
    )
    result.sp500_expected_return = _float_or(
        er_meta.get("sp500_expected_return"),
        DEFAULT_SP500_EXPECTED_RETURN,
    )
    result.peer_expected_return = _float_or(er_meta.get("peer_expected_return"), None)

    _register_assumption(
        result,
        "HOLDING_PERIOD_YEARS",
        float(result.holding_period_years),
        "count",
        "metadata.expected_return" if er_meta.get("holding_period_years") else "valuation_inputs",
        evidence,
        "expected_return.holding_period_years",
        default_confidence=0.85 if er_meta.get("holding_period_years") else 0.70,
    )
    _register_assumption(
        result,
        "SP500_EXPECTED_RETURN",
        result.sp500_expected_return,
        "ratio",
        "metadata.expected_return" if er_meta.get("sp500_expected_return") is not None else "derived_default",
        evidence,
        "expected_return.sp500_expected_return",
        default_confidence=0.75,
    )
    if result.peer_expected_return is not None:
        _register_assumption(
            result,
            "PEER_EXPECTED_RETURN",
            result.peer_expected_return,
            "ratio",
            "metadata.expected_return",
            evidence,
            "expected_return.peer_expected_return",
        )

    if result.fair_value_base is not None:
        _register_assumption(
            result,
            "FAIR_VALUE_BASE",
            result.fair_value_base,
            model.reporting_currency,
            "hap_valuation_engine",
            evidence,
            "valuation.fair_value_base",
            default_confidence=0.80,
        )

    if result.share_price is None or result.share_price <= 0:
        result.confidence_penalty += 0.15
        return result

    if not result.valuation_available:
        result.confidence_penalty += 0.12
        return result

    market_cap = (
        result.share_price * md.shares_outstanding
        if md.shares_outstanding
        else md.market_cap
    )

    result.dividend_yield = _resolve_dividend_yield(model, market_cap, er_meta)
    result.buyback_yield = _resolve_buyback_yield(model, market_cap, er_meta)

    fcf_series = _resolve_fcf_series(
        cfs.operating_cash_flow,
        cfs.capital_expenditures,
        cfs.free_cash_flow,
    )
    eps_cagr = income.diluted_eps.cagr(5) if len(income.diluted_eps) >= 2 else None
    fcf_cagr = fcf_series.cagr(5) if len(fcf_series) >= 2 else None

    eps_overlay = _float_or(er_meta.get("expected_eps_growth"), None)
    fcf_overlay = _float_or(er_meta.get("expected_fcf_growth"), None)
    result.eps_growth_contribution = _cap_growth(eps_overlay if eps_overlay is not None else eps_cagr)
    result.fcf_growth_contribution = _cap_growth(fcf_overlay if fcf_overlay is not None else fcf_cagr)

    growth_items = [
        value
        for value in (result.eps_growth_contribution, result.fcf_growth_contribution)
        if value is not None
    ]
    result.growth_contribution = mean(growth_items) if growth_items else None

    if result.eps_growth_contribution is not None:
        _register_assumption(
            result,
            "EPS_GROWTH_CONTRIBUTION",
            result.eps_growth_contribution,
            "ratio",
            "metadata.expected_return" if eps_overlay is not None else "derived_default",
            evidence,
            "expected_return.expected_eps_growth",
            default_confidence=0.85 if eps_overlay is not None else 0.70,
        )
    if result.fcf_growth_contribution is not None:
        _register_assumption(
            result,
            "FCF_GROWTH_CONTRIBUTION",
            result.fcf_growth_contribution,
            "ratio",
            "metadata.expected_return" if fcf_overlay is not None else "derived_default",
            evidence,
            "expected_return.expected_fcf_growth",
            default_confidence=0.85 if fcf_overlay is not None else 0.70,
        )
    if result.dividend_yield is not None:
        _register_assumption(
            result,
            "DIVIDEND_YIELD",
            result.dividend_yield,
            "ratio",
            _yield_source(model, er_meta, "dividend_yield"),
            evidence,
            "expected_return.dividend_yield",
        )
    if result.buyback_yield is not None:
        _register_assumption(
            result,
            "BUYBACK_YIELD",
            result.buyback_yield,
            "ratio",
            _yield_source(model, er_meta, "buyback_yield"),
            evidence,
            "expected_return.buyback_yield",
        )

    if eps_overlay is None and eps_cagr is None:
        result.confidence_penalty += 0.06
    if fcf_overlay is None and fcf_cagr is None:
        result.confidence_penalty += 0.06

    result.valuation_reversion = _valuation_reversion(
        fair_value=result.fair_value_base,
        share_price=result.share_price,
        holding_period=result.holding_period_years,
    )
    result.multiple_expansion = _resolve_multiple_expansion(
        model, valuation_result, er_meta, result.holding_period_years
    )
    if result.multiple_expansion is not None:
        _register_assumption(
            result,
            "MULTIPLE_EXPANSION",
            result.multiple_expansion,
            "ratio",
            "metadata.expected_return" if er_meta.get("multiple_expansion_cagr") is not None else "derived_default",
            evidence,
            "expected_return.multiple_expansion_cagr",
            default_confidence=0.75,
        )

    components = [
        result.growth_contribution,
        result.dividend_yield,
        result.buyback_yield,
        result.valuation_reversion,
        result.multiple_expansion,
    ]
    available = [value for value in components if value is not None]
    if available:
        result.expected_cagr = max(RETURN_FLOOR, min(RETURN_CAP, sum(available)))

    result.expected_irr = _solve_expected_irr(
        share_price=result.share_price,
        fair_value=result.fair_value_base,
        holding_period=result.holding_period_years,
        dividend_yield=result.dividend_yield or 0.0,
        growth_rate=result.eps_growth_contribution or result.growth_contribution or 0.0,
    )
    if result.expected_irr is None and result.expected_cagr is not None:
        result.expected_irr = result.expected_cagr

    for name, fair_value in (
        ("bear", result.fair_value_low),
        ("base", result.fair_value_base),
        ("bull", result.fair_value_high),
    ):
        scenario_fv = fair_value
        if name in valuation_result.scenarios and valuation_result.scenarios[name].value_per_share is not None:
            scenario_fv = valuation_result.scenarios[name].value_per_share
        reversion = _valuation_reversion(
            fair_value=scenario_fv,
            share_price=result.share_price,
            holding_period=result.holding_period_years,
        )
        scenario_components = [
            result.growth_contribution,
            result.dividend_yield,
            result.buyback_yield,
            reversion,
            result.multiple_expansion,
        ]
        scenario_available = [value for value in scenario_components if value is not None]
        scenario_cagr = (
            max(RETURN_FLOOR, min(RETURN_CAP, sum(scenario_available)))
            if scenario_available
            else None
        )
        scenario_irr = _solve_expected_irr(
            share_price=result.share_price,
            fair_value=scenario_fv,
            holding_period=result.holding_period_years,
            dividend_yield=result.dividend_yield or 0.0,
            growth_rate=result.eps_growth_contribution or result.growth_contribution or 0.0,
        )
        result.scenarios[name] = ScenarioReturn(
            name=name,
            expected_cagr=scenario_cagr,
            expected_irr=scenario_irr if scenario_irr is not None else scenario_cagr,
            valuation_reversion=reversion,
            fair_value_per_share=scenario_fv,
        )

    if result.holding_period_years < 5:
        result.confidence_penalty += 0.05

    return result


def _resolve_dividend_yield(
    model: CompanyFinancialModel,
    market_cap: float | None,
    er_meta: dict[str, Any],
) -> float | None:
    overlay = _float_or(er_meta.get("dividend_yield"), None)
    if overlay is not None:
        return max(0.0, overlay)
    if model.market_data.dividend_yield is not None:
        return max(0.0, model.market_data.dividend_yield)
    dividends = model.cash_flow_statement.dividends
    if market_cap and market_cap > 0 and not dividends.is_empty:
        latest = dividends.latest()
        if latest is not None:
            return max(0.0, abs(latest.value) / market_cap)
    return None


def _resolve_buyback_yield(
    model: CompanyFinancialModel,
    market_cap: float | None,
    er_meta: dict[str, Any],
) -> float | None:
    overlay = _float_or(er_meta.get("buyback_yield"), None)
    if overlay is not None:
        return max(0.0, overlay)
    buybacks = model.cash_flow_statement.share_repurchases
    if market_cap and market_cap > 0 and not buybacks.is_empty:
        latest = buybacks.latest()
        if latest is not None:
            return max(0.0, abs(latest.value) / market_cap)
    return None


def _resolve_multiple_expansion(
    model: CompanyFinancialModel,
    valuation: ValuationComputeResult,
    er_meta: dict[str, Any],
    holding_period: int,
) -> float | None:
    overlay = _float_or(er_meta.get("multiple_expansion_cagr"), None)
    if overlay is not None:
        return overlay
    target = _float_or(er_meta.get("target_ev_ebitda_multiple"), None)
    if target is None:
        val_meta = model.metadata.get("valuation") if isinstance(model.metadata.get("valuation"), dict) else {}
        peer = val_meta.get("peer_ev_to_ebitda")
        if isinstance(peer, dict):
            target = _float_or(peer.get("median"), None)
        elif isinstance(peer, (int, float)):
            target = float(peer)
    if target is None or valuation.implied_ev_to_ebitda is None or holding_period <= 0:
        return 0.0 if overlay == 0.0 else None
    if valuation.implied_ev_to_ebitda <= 0:
        return None
    ratio_change = target / valuation.implied_ev_to_ebitda
    if ratio_change <= 0:
        return None
    return max(-0.10, min(0.15, ratio_change ** (1.0 / holding_period) - 1.0))


def _valuation_reversion(
    *,
    fair_value: float | None,
    share_price: float | None,
    holding_period: int,
) -> float | None:
    if fair_value is None or share_price is None or fair_value <= 0 or share_price <= 0 or holding_period <= 0:
        return None
    return (fair_value / share_price) ** (1.0 / holding_period) - 1.0


def _solve_expected_irr(
    *,
    share_price: float,
    fair_value: float | None,
    holding_period: int,
    dividend_yield: float,
    growth_rate: float,
) -> float | None:
    if fair_value is None or fair_value <= 0 or holding_period <= 0:
        return None
    div_per_share = dividend_yield * share_price
    low, high = -0.25, 0.60
    for _ in range(60):
        mid = (low + high) / 2.0
        pv = -share_price
        dividend = div_per_share
        for year in range(1, holding_period + 1):
            if year > 1:
                dividend *= 1.0 + growth_rate
            pv += dividend / ((1.0 + mid) ** year)
        pv += fair_value / ((1.0 + mid) ** holding_period)
        if abs(pv) < 0.01:
            return mid
        if pv > 0:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _cap_growth(value: float | None) -> float | None:
    if value is None:
        return None
    return max(GROWTH_FLOOR, min(GROWTH_CAP, value))


def _yield_source(model: CompanyFinancialModel, er_meta: dict[str, Any], field: str) -> str:
    if er_meta.get(field) is not None:
        return "metadata.expected_return"
    if field == "dividend_yield" and model.market_data.dividend_yield is not None:
        return "market_data"
    return "derived_default"


def _float_or(value: Any, default: float | None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
