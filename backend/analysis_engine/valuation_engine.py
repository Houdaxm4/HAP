"""Deterministic enterprise valuation math for the Valuation module."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from analysis_engine.utils import mean, paired_periods, safe_div
from canonical_model import CompanyFinancialModel, FinancialPoint, FinancialSeries

DEFAULT_FORECAST_YEARS = 5
DEFAULT_GDP_GROWTH = 0.04
METHOD_CONFIDENCE_THRESHOLD = 0.55
SYNTHESIS_WEIGHTS = {
    "dcf": 0.35,
    "owner_earnings": 0.25,
    "multiples": 0.25,
    "historical": 0.15,
}


@dataclass
class AssumptionRecord:
    code: str
    value: float | None
    unit: str
    source: str
    source_document: str | None = None
    confidence: float = 0.60
    provenance: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "source_document": self.source_document,
            "confidence": self.confidence,
            "provenance": self.provenance,
        }


@dataclass
class MethodValuation:
    method: str
    enterprise_value: float | None = None
    equity_value: float | None = None
    value_per_share: float | None = None
    confidence: float = 0.0
    available: bool = False
    dcf_terminal_share: float | None = None
    dcf_pv_forecast_share: float | None = None
    implied_multiple: float | None = None
    negative_forecast_fcf: bool = False


@dataclass
class ScenarioValuation:
    name: str
    value_per_share: float | None = None
    margin_of_safety: float | None = None


@dataclass
class ValuationComputeResult:
    assumptions: list[AssumptionRecord] = field(default_factory=list)
    methods: dict[str, MethodValuation] = field(default_factory=dict)
    hap_enterprise_value: float | None = None
    hap_equity_value: float | None = None
    hap_intrinsic_value_per_share: float | None = None
    fair_value_base: float | None = None
    fair_value_low: float | None = None
    fair_value_high: float | None = None
    margin_of_safety: float | None = None
    premium_discount: float | None = None
    method_spread: float | None = None
    reverse_dcf_implied_growth: float | None = None
    reverse_dcf_implied_fcf_cagr: float | None = None
    reverse_dcf_solvable: bool = False
    scenarios: dict[str, ScenarioValuation] = field(default_factory=dict)
    method_count: int = 0
    dcf_available: bool = False
    latest_fcf: float | None = None
    latest_net_income: float | None = None
    owner_earnings_run_rate: float | None = None
    share_price: float | None = None
    shares: float | None = None
    net_debt: float | None = None
    wacc: float | None = None
    terminal_growth: float | None = None
    forecast_years: int = DEFAULT_FORECAST_YEARS
    gdp_growth: float = DEFAULT_GDP_GROWTH
    implied_ev_to_ebitda: float | None = None
    peer_p25: float | None = None
    peer_median: float | None = None
    peer_p75: float | None = None
    historical_median_multiple: float | None = None
    cyclicality_flag: bool = False
    turnaround_plan: bool = False
    confidence_penalty: float = 0.0


def compute_valuation(model: CompanyFinancialModel) -> ValuationComputeResult:
    """Run all valuation methodologies and synthesize fair value."""
    result = ValuationComputeResult()
    metadata = dict(model.metadata or {})
    val_meta = metadata.get("valuation") if isinstance(metadata.get("valuation"), dict) else {}
    evidence = metadata.get("assumption_evidence") or val_meta.get("assumption_evidence") or {}
    if not isinstance(evidence, dict):
        evidence = {}

    vi = model.valuation_inputs
    md = model.market_data
    income = model.income_statement
    bs = model.balance_sheet
    cfs = model.cash_flow_statement

    result.share_price = md.share_price
    result.shares = md.shares_outstanding
    result.wacc = vi.wacc
    result.terminal_growth = vi.terminal_growth_rate
    result.forecast_years = vi.forecast_years or DEFAULT_FORECAST_YEARS
    result.gdp_growth = _float_or(val_meta.get("gdp_nominal_growth"), DEFAULT_GDP_GROWTH)
    result.cyclicality_flag = bool(val_meta.get("cyclicality_flag"))
    result.turnaround_plan = bool(val_meta.get("turnaround_plan"))

    fcf_series = _resolve_fcf_series(cfs.operating_cash_flow, cfs.capital_expenditures, cfs.free_cash_flow)
    result.latest_fcf = fcf_series.latest().value if fcf_series.latest() else None
    result.latest_net_income = income.net_income.latest().value if income.net_income.latest() else None

    tax_rate = _resolve_tax_rate(model)
    result.net_debt = _resolve_net_debt(model)

    _register_assumption(result, "WACC", result.wacc, "ratio", "valuation_inputs", evidence, "valuation_inputs.wacc")
    _register_assumption(
        result,
        "TERMINAL_GROWTH",
        result.terminal_growth,
        "ratio",
        "valuation_inputs",
        evidence,
        "valuation_inputs.terminal_growth_rate",
    )
    _register_assumption(
        result,
        "FORECAST_YEARS",
        float(result.forecast_years),
        "count",
        "valuation_inputs" if vi.forecast_years else "derived_default",
        evidence,
        "valuation_inputs.forecast_years",
        default_confidence=0.50 if not vi.forecast_years else 0.85,
    )
    _register_assumption(result, "TAX_RATE", tax_rate, "ratio", _tax_source(model), evidence, "valuation_inputs.tax_rate")
    _register_assumption(result, "NET_DEBT", result.net_debt, model.reporting_currency, _net_debt_source(model), evidence, "valuation_inputs.net_debt")
    _register_assumption(
        result,
        "GDP_NOMINAL_GROWTH",
        result.gdp_growth,
        "ratio",
        "metadata.valuation" if val_meta.get("gdp_nominal_growth") is not None else "derived_default",
        evidence,
        "metadata.valuation.gdp_nominal_growth",
        default_confidence=0.70 if val_meta.get("gdp_nominal_growth") is not None else 0.50,
    )

    if vi.forecast_years is None:
        result.confidence_penalty += 0.05

    base_growth = _forecast_growth_path(model, val_meta, fcf_series)
    _register_assumption(
        result,
        "FORECAST_REVENUE_GROWTH",
        mean(base_growth) if base_growth else None,
        "ratio",
        "metadata.valuation" if val_meta.get("forecast_revenue_growth") else "derived_default",
        evidence,
        "metadata.valuation.forecast_revenue_growth",
    )

    if result.wacc is not None and result.terminal_growth is not None and result.latest_fcf is not None:
        if result.wacc > result.terminal_growth:
            dcf = _compute_dcf(
                latest_fcf=result.latest_fcf,
                growth_path=base_growth,
                wacc=result.wacc,
                terminal_growth=result.terminal_growth,
                forecast_years=result.forecast_years,
                net_debt=result.net_debt,
                shares=result.shares,
                minority=vi.minority_interest,
                preferred=vi.preferred_equity,
            )
            result.methods["dcf"] = dcf
            result.dcf_available = True
        else:
            result.confidence_penalty += 0.08
    else:
        result.confidence_penalty += 0.10

    oe = _compute_owner_earnings(model, val_meta, vi, result)
    if oe.available:
        result.methods["owner_earnings"] = oe

    peer = _parse_peer_multiple(val_meta.get("peer_ev_to_ebitda"))
    result.peer_p25, result.peer_median, result.peer_p75 = peer
    if result.peer_median is not None:
        _register_assumption(
            result,
            "PEER_MEDIAN_EV_EBITDA",
            result.peer_median,
            "ratio",
            "metadata.valuation",
            evidence,
            "metadata.valuation.peer_ev_to_ebitda",
        )
        mult = _compute_peer_multiples(model, result.peer_median, result.net_debt, result.shares)
        if mult.available:
            result.methods["multiples"] = mult

    hist = _historical_median(val_meta.get("historical_ev_to_ebitda"))
    result.historical_median_multiple = hist
    if hist is not None:
        hmult = _compute_historical_multiples(model, hist, result.net_debt, result.shares)
        if hmult.available:
            result.methods["historical"] = hmult

    method_values = {
        name: m.value_per_share
        for name, m in result.methods.items()
        if m.available and m.value_per_share is not None and m.confidence >= METHOD_CONFIDENCE_THRESHOLD
    }
    result.method_count = len(method_values)

    if method_values:
        result.fair_value_base = _synthesize_base_value(method_values)
        result.hap_intrinsic_value_per_share = result.fair_value_base
        primary = result.methods.get("dcf") or next(iter(result.methods.values()))
        result.hap_enterprise_value = primary.enterprise_value
        result.hap_equity_value = primary.equity_value
        if result.methods.get("dcf"):
            result.hap_enterprise_value = result.methods["dcf"].enterprise_value
            result.hap_equity_value = result.methods["dcf"].equity_value

    if result.fair_value_base and result.share_price:
        result.margin_of_safety = safe_div(result.fair_value_base - result.share_price, result.fair_value_base)
        result.premium_discount = safe_div(result.share_price - result.fair_value_base, result.fair_value_base)

    if method_values and result.fair_value_base:
        vals = list(method_values.values())
        result.method_spread = safe_div(max(vals) - min(vals), result.fair_value_base)

    if (
        result.share_price
        and result.shares
        and result.wacc
        and result.terminal_growth is not None
        and result.latest_fcf is not None
        and result.wacc > result.terminal_growth
    ):
        implied_g = _solve_implied_terminal_growth(
            target_price=result.share_price,
            latest_fcf=result.latest_fcf,
            growth_path=base_growth,
            wacc=result.wacc,
            forecast_years=result.forecast_years,
            net_debt=result.net_debt or 0.0,
            shares=result.shares,
        )
        if implied_g is not None:
            result.reverse_dcf_implied_growth = implied_g
            result.reverse_dcf_solvable = True

    ebitda = _latest_ebitda(model)
    if result.hap_enterprise_value and ebitda:
        result.implied_ev_to_ebitda = safe_div(result.hap_enterprise_value, ebitda)

    scenarios = _compute_scenarios(model, val_meta, result, base_growth, tax_rate, peer)
    result.scenarios = scenarios
    if "bear" in scenarios:
        result.fair_value_low = scenarios["bear"].value_per_share
    if "bull" in scenarios:
        result.fair_value_high = scenarios["bull"].value_per_share
    if "base" in scenarios and scenarios["base"].value_per_share is not None:
        result.fair_value_base = scenarios["base"].value_per_share
        result.hap_intrinsic_value_per_share = result.fair_value_base
        if result.share_price:
            result.margin_of_safety = safe_div(
                result.fair_value_base - result.share_price, result.fair_value_base
            )

    return result


def _compute_dcf(
    *,
    latest_fcf: float,
    growth_path: list[float],
    wacc: float,
    terminal_growth: float,
    forecast_years: int,
    net_debt: float | None,
    shares: float | None,
    minority: float | None,
    preferred: float | None,
) -> MethodValuation:
    path = list(growth_path[:forecast_years])
    while len(path) < forecast_years:
        path.append(path[-1] if path else terminal_growth)
    fcf = latest_fcf
    pv_forecast = 0.0
    negative = False
    for year, growth in enumerate(path, start=1):
        fcf = fcf * (1.0 + growth)
        if fcf < 0:
            negative = True
        pv_forecast += fcf / ((1.0 + wacc) ** year)
    tv = fcf * (1.0 + terminal_growth) / (wacc - terminal_growth)
    pv_tv = tv / ((1.0 + wacc) ** forecast_years)
    ev = pv_forecast + pv_tv
    total = pv_forecast + pv_tv
    terminal_share = safe_div(pv_tv, total) if total else None
    forecast_share = safe_div(pv_forecast, total) if total else None
    equity = ev - (net_debt or 0.0) - (minority or 0.0) - (preferred or 0.0)
    per_share = safe_div(equity, shares) if shares else None
    conf = 0.85
    if terminal_share is not None and terminal_share > 0.75:
        conf -= 0.10
    if negative:
        conf -= 0.08
    return MethodValuation(
        method="dcf",
        enterprise_value=ev,
        equity_value=equity,
        value_per_share=per_share,
        confidence=max(0.45, conf),
        available=per_share is not None,
        dcf_terminal_share=terminal_share,
        dcf_pv_forecast_share=forecast_share,
        negative_forecast_fcf=negative,
    )


def _compute_owner_earnings(
    model: CompanyFinancialModel,
    val_meta: dict[str, Any],
    vi: Any,
    result: ValuationComputeResult,
) -> MethodValuation:
    cfs = model.cash_flow_statement
    ocf = cfs.operating_cash_flow.latest()
    if ocf is None:
        return MethodValuation(method="owner_earnings")
    maint = val_meta.get("maintenance_capex")
    if maint is None:
        capex = cfs.capital_expenditures.latest()
        maint_value = abs(capex.value) if capex else 0.0
        conf = 0.65
    else:
        maint_value = abs(float(maint))
        conf = 0.80
    owner_earnings = ocf.value - maint_value
    result.owner_earnings_run_rate = owner_earnings
    wacc = result.wacc
    g = result.terminal_growth or 0.02
    if wacc is None or wacc <= g:
        return MethodValuation(method="owner_earnings")
    ev = owner_earnings * (1.0 + g) / (wacc - g)
    equity = ev - (result.net_debt or 0.0) - (vi.minority_interest or 0.0) - (vi.preferred_equity or 0.0)
    per_share = safe_div(equity, result.shares) if result.shares else None
    return MethodValuation(
        method="owner_earnings",
        enterprise_value=ev,
        equity_value=equity,
        value_per_share=per_share,
        confidence=conf,
        available=per_share is not None and owner_earnings > 0,
    )


def _compute_peer_multiples(
    model: CompanyFinancialModel,
    peer_median: float,
    net_debt: float | None,
    shares: float | None,
) -> MethodValuation:
    ebitda = _latest_ebitda(model)
    if ebitda is None or ebitda <= 0:
        return MethodValuation(method="multiples")
    ev = ebitda * peer_median
    equity = ev - (net_debt or 0.0)
    per_share = safe_div(equity, shares) if shares else None
    return MethodValuation(
        method="multiples",
        enterprise_value=ev,
        equity_value=equity,
        value_per_share=per_share,
        confidence=0.80,
        available=per_share is not None,
        implied_multiple=peer_median,
    )


def _compute_historical_multiples(
    model: CompanyFinancialModel,
    hist_median: float,
    net_debt: float | None,
    shares: float | None,
) -> MethodValuation:
    ebitda = _latest_ebitda(model)
    if ebitda is None or ebitda <= 0:
        return MethodValuation(method="historical")
    ev = ebitda * hist_median
    equity = ev - (net_debt or 0.0)
    per_share = safe_div(equity, shares) if shares else None
    return MethodValuation(
        method="historical",
        enterprise_value=ev,
        equity_value=equity,
        value_per_share=per_share,
        confidence=0.72,
        available=per_share is not None,
        implied_multiple=hist_median,
    )


def _compute_scenarios(
    model: CompanyFinancialModel,
    val_meta: dict[str, Any],
    result: ValuationComputeResult,
    base_growth: list[float],
    tax_rate: float | None,
    peer: tuple[float | None, float | None, float | None],
) -> dict[str, ScenarioValuation]:
    overrides = val_meta.get("scenarios") if isinstance(val_meta.get("scenarios"), dict) else {}
    scenarios: dict[str, ScenarioValuation] = {}
    p25, median, p75 = peer
    for name, adj in (
        ("bear", {"growth_factor": 0.70, "margin_bps": -0.01, "tg_bps": -0.005, "wacc_bps": 0.0075, "peer": p25}),
        ("base", {"growth_factor": 1.0, "margin_bps": 0.0, "tg_bps": 0.0, "wacc_bps": 0.0, "peer": median}),
        ("bull", {"growth_factor": 1.25, "margin_bps": 0.01, "tg_bps": 0.0025, "wacc_bps": -0.005, "peer": p75}),
    ):
        custom = overrides.get(name) if isinstance(overrides.get(name), dict) else {}
        wacc = (result.wacc or 0.09) + adj["wacc_bps"] + float(custom.get("wacc_delta", 0.0))
        tg = (result.terminal_growth or 0.02) + adj["tg_bps"] + float(custom.get("terminal_growth_delta", 0.0))
        tg = min(tg, result.gdp_growth)
        tg = max(tg, 0.0)
        growth_path = [max(-0.10, min(0.30, g * adj["growth_factor"])) for g in base_growth]
        if result.latest_fcf is None or wacc <= tg:
            scenarios[name] = ScenarioValuation(name=name)
            continue
        dcf = _compute_dcf(
            latest_fcf=result.latest_fcf,
            growth_path=growth_path,
            wacc=wacc,
            terminal_growth=tg,
            forecast_years=result.forecast_years,
            net_debt=result.net_debt,
            shares=result.shares,
            minority=model.valuation_inputs.minority_interest,
            preferred=model.valuation_inputs.preferred_equity,
        )
        value = dcf.value_per_share
        if adj["peer"] is not None and name != "base":
            alt = _compute_peer_multiples(model, adj["peer"], result.net_debt, result.shares)
            if alt.value_per_share is not None and value is not None:
                value = (value + alt.value_per_share) / 2.0
            elif alt.value_per_share is not None:
                value = alt.value_per_share
        mos = safe_div(value - result.share_price, value) if value and result.share_price else None
        scenarios[name] = ScenarioValuation(name=name, value_per_share=value, margin_of_safety=mos)
    return scenarios


def _synthesize_base_value(method_values: dict[str, float]) -> float | None:
    if not method_values:
        return None
    if len(method_values) == 1:
        return next(iter(method_values.values()))
    if len(method_values) == 2:
        return mean(list(method_values.values()))
    weighted_items = []
    for key, value in method_values.items():
        weight = SYNTHESIS_WEIGHTS.get(key, 0.10)
        weighted_items.append((value, weight))
    weighted_items.sort(key=lambda item: item[0])
    total_weight = sum(weight for _, weight in weighted_items)
    cumulative = 0.0
    for value, weight in weighted_items:
        cumulative += weight
        if cumulative >= total_weight / 2.0:
            return value
    return weighted_items[-1][0]


def _solve_implied_terminal_growth(
    *,
    target_price: float,
    latest_fcf: float,
    growth_path: list[float],
    wacc: float,
    forecast_years: int,
    net_debt: float,
    shares: float,
) -> float | None:
    low, high = -0.02, min(0.12, wacc - 0.005)
    if low >= high:
        return None
    for _ in range(40):
        mid = (low + high) / 2.0
        dcf = _compute_dcf(
            latest_fcf=latest_fcf,
            growth_path=growth_path,
            wacc=wacc,
            terminal_growth=mid,
            forecast_years=forecast_years,
            net_debt=net_debt,
            shares=shares,
            minority=None,
            preferred=None,
        )
        if dcf.value_per_share is None:
            return None
        if abs(dcf.value_per_share - target_price) < 0.01:
            return mid
        if dcf.value_per_share > target_price:
            low = mid
        else:
            high = mid
    return (low + high) / 2.0


def _forecast_growth_path(model: CompanyFinancialModel, val_meta: dict[str, Any], fcf: FinancialSeries) -> list[float]:
    raw = val_meta.get("forecast_revenue_growth")
    if isinstance(raw, list) and raw:
        return [float(x) for x in raw]
    if isinstance(raw, dict) and raw:
        return [float(v) for _, v in sorted(raw.items())]
    rev = model.income_statement.revenue
    cagr = rev.cagr(5) if len(rev) >= 2 else None
    base = cagr if cagr is not None else 0.03
    fcf_cagr = fcf.cagr(5) if len(fcf) >= 2 else base
    start = min(base, fcf_cagr, 0.15)
    path = []
    for i in range(DEFAULT_FORECAST_YEARS):
        fade = max(0.02, start * (0.85 ** i))
        path.append(fade)
    return path


def _resolve_fcf_series(ocf: FinancialSeries, capex: FinancialSeries, reported: FinancialSeries) -> FinancialSeries:
    if not reported.is_empty:
        return reported
    derived = FinancialSeries(name="Free Cash Flow", currency=ocf.currency)
    for period in paired_periods(ocf, capex):
        ocf_point = ocf.point_for(period)
        capex_point = capex.point_for(period)
        if ocf_point is None or capex_point is None:
            continue
        derived.upsert(
            FinancialPoint(
                period=period,
                value=ocf_point.value - abs(capex_point.value),
                currency=ocf_point.currency,
                source="derived",
                confidence=ocf_point.confidence,
            )
        )
    return derived


def _resolve_tax_rate(model: CompanyFinancialModel) -> float | None:
    if model.valuation_inputs.tax_rate is not None:
        return model.valuation_inputs.tax_rate
    income = model.income_statement
    ebit = income.ebit.latest() or income.operating_income.latest()
    tax = income.tax_expense.latest()
    if ebit is None or tax is None or ebit.value == 0:
        return None
    return max(0.0, min(0.5, abs(tax.value) / abs(ebit.value)))


def _tax_source(model: CompanyFinancialModel) -> str:
    return "valuation_inputs" if model.valuation_inputs.tax_rate is not None else "derived_default"


def _resolve_net_debt(model: CompanyFinancialModel) -> float | None:
    if model.valuation_inputs.net_debt is not None:
        return model.valuation_inputs.net_debt
    debt = model.balance_sheet.total_debt.latest()
    cash = model.balance_sheet.cash.latest()
    if debt is None and cash is None:
        return None
    return (debt.value if debt else 0.0) - (cash.value if cash else 0.0)


def _net_debt_source(model: CompanyFinancialModel) -> str:
    return "valuation_inputs" if model.valuation_inputs.net_debt is not None else "derived_default"


def _latest_ebitda(model: CompanyFinancialModel) -> float | None:
    income = model.income_statement
    if not income.ebitda.is_empty and income.ebitda.latest():
        return income.ebitda.latest().value
    oi = income.operating_income.latest() or income.ebit.latest()
    return oi.value if oi else None


def _parse_peer_multiple(raw: Any) -> tuple[float | None, float | None, float | None]:
    if raw is None:
        return None, None, None
    if isinstance(raw, (int, float)):
        value = float(raw)
        return value * 0.85, value, value * 1.15
    if isinstance(raw, dict):
        p25 = _float_or(raw.get("p25"), None)
        med = _float_or(raw.get("median"), None)
        p75 = _float_or(raw.get("p75"), None)
        if med is not None and p25 is None:
            p25 = med * 0.85
        if med is not None and p75 is None:
            p75 = med * 1.15
        return p25, med, p75
    return None, None, None


def _historical_median(raw: Any) -> float | None:
    if isinstance(raw, dict) and raw:
        values = sorted(float(v) for v in raw.values())
        return values[len(values) // 2]
    if isinstance(raw, (int, float)):
        return float(raw)
    return None


def _register_assumption(
    result: ValuationComputeResult,
    code: str,
    value: float | None,
    unit: str,
    source: str,
    evidence: dict[str, Any],
    field: str,
    *,
    default_confidence: float = 0.85,
) -> None:
    if value is None:
        return
    ev = evidence.get(code.lower()) or evidence.get(field.split(".")[-1]) or {}
    if not isinstance(ev, dict):
        ev = {}
    conf = _float_or(ev.get("confidence"), default_confidence if source != "derived_default" else 0.60)
    result.assumptions.append(
        AssumptionRecord(
            code=code,
            value=value,
            unit=unit,
            source=str(ev.get("source") or source),
            source_document=ev.get("source_document"),
            confidence=conf,
            provenance={"field": field, **{k: v for k, v in ev.items() if k not in {"source", "confidence"}}},
        )
    )


def _float_or(value: Any, default: float | None) -> float | None:
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
