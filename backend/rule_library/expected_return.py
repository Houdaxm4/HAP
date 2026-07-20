"""Expected Return rules ER001–ER030 (HAP methodology + RULE_LIBRARY.md)."""

from __future__ import annotations

from analysis_engine.schemas import Evidence
from rule_library.base import RuleDefinition, RuleHit, evidence_from_metric


def _rule(
    rule_id: str,
    severity: str,
    finding: str,
    explanation: str,
    action: str | None = None,
) -> RuleDefinition:
    return RuleDefinition(
        rule_id=rule_id,
        category="expected_return",
        severity=severity,  # type: ignore[arg-type]
        finding=finding,
        explanation=explanation,
        suggested_analyst_action=action,
    )


EXPECTED_RETURN_RULES: dict[str, RuleDefinition] = {
    "ER001": _rule(
        "ER001",
        "POSITIVE",
        "Excellent Expected Return",
        "Expected annualized return exceeds 15%.",
        "None.",
    ),
    "ER002": _rule(
        "ER002",
        "POSITIVE",
        "Attractive Expected Return",
        "Expected annualized return is between 10% and 15%.",
        "None.",
    ),
    "ER003": _rule(
        "ER003",
        "INFO",
        "Moderate Expected Return",
        "Expected return is near the long-run equity market range.",
        "None.",
    ),
    "ER004": _rule(
        "ER004",
        "WARNING",
        "Limited Expected Return",
        "Expected return is below typical equity hurdle rates.",
        "Review growth and valuation assumptions.",
    ),
    "ER005": _rule(
        "ER005",
        "WARNING",
        "Poor Expected Return",
        "Expected return is below 5% annually.",
        "Reassess entry price or holding thesis.",
    ),
    "ER006": _rule(
        "ER006",
        "CRITICAL",
        "Negative Expected Return",
        "Base-case expected return is negative at today's price.",
        "Revise valuation or avoid new capital at current price.",
    ),
    "ER007": _rule(
        "ER007",
        "POSITIVE",
        "Superior Expected Return Versus Index",
        "Expected return exceeds S&P 500 hurdle by at least 3 percentage points.",
        "None.",
    ),
    "ER008": _rule(
        "ER008",
        "WARNING",
        "Index Likely Superior",
        "Expected return is below the S&P 500 expected return.",
        "Compare risk-adjusted alternatives.",
    ),
    "ER009": _rule(
        "ER009",
        "WARNING",
        "Inferior Investment Opportunity Versus Peers",
        "Expected return is below peer average hurdle.",
        "Review peer set and return drivers.",
    ),
    "ER010": _rule(
        "ER010",
        "WARNING",
        "Valuation Headwind",
        "Valuation reversion contribution is negative at today's price.",
        "Stress-test bear-case fair value.",
    ),
    "ER011": _rule(
        "ER011",
        "WARNING",
        "Return Dominated By Valuation Reversion",
        "More than half of expected return depends on multiple reversion.",
        "Validate fair value assumptions.",
    ),
    "ER012": _rule(
        "ER012",
        "WARNING",
        "Negative Growth Contribution",
        "Expected earnings or cash flow growth detracts from shareholder return.",
        "Review growth sustainability.",
    ),
    "ER013": _rule(
        "ER013",
        "POSITIVE",
        "Dividend Yield Supports Return",
        "Dividend yield provides meaningful return support above 2%.",
        "None.",
    ),
    "ER014": _rule(
        "ER014",
        "POSITIVE",
        "Buyback Yield Supports Return",
        "Share repurchases contribute materially to expected return.",
        "None.",
    ),
    "ER015": _rule(
        "ER015",
        "WARNING",
        "Elevated Dividend Yield",
        "Dividend yield exceeds 8% and may signal payout stress.",
        "Review dividend sustainability.",
    ),
    "ER016": _rule(
        "ER016",
        "WARNING",
        "Buybacks Exceed Free Cash Flow",
        "Repurchases exceed trailing free cash flow.",
        "Review funding sources for buybacks.",
    ),
    "ER017": _rule(
        "ER017",
        "WARNING",
        "Dividend Growth Exceeds Earnings Growth",
        "Dividend growth outpaces earnings growth.",
        "Review payout policy sustainability.",
    ),
    "ER018": _rule(
        "ER018",
        "WARNING",
        "FCF Growth Lags Earnings Growth",
        "Free cash flow growth trails earnings growth.",
        "Review cash conversion and capex intensity.",
    ),
    "ER019": _rule(
        "ER019",
        "INFO",
        "Valuation Inputs Missing",
        "Fair value unavailable; expected return cannot be fully computed.",
        "Complete valuation module inputs.",
    ),
    "ER020": _rule(
        "ER020",
        "INFO",
        "Market Price Missing",
        "Share price required for return estimation.",
        "Supply market data.",
    ),
    "ER021": _rule(
        "ER021",
        "INFO",
        "Multiple Expansion Assumption Material",
        "Multiple expansion contributes more than 3% annually.",
        "Document multiple expansion rationale.",
    ),
    "ER022": _rule(
        "ER022",
        "WARNING",
        "Bear Scenario Negative Return",
        "Bear-case expected return is negative.",
        "Stress-test downside case.",
    ),
    "ER023": _rule(
        "ER023",
        "POSITIVE",
        "Bull Scenario Exceptional Return",
        "Bull-case expected return exceeds 20%.",
        "None.",
    ),
    "ER024": _rule(
        "ER024",
        "WARNING",
        "Wide Return Scenario Spread",
        "Bear-to-bull expected return spread exceeds 10 percentage points.",
        "Reconcile scenario assumptions.",
    ),
    "ER025": _rule(
        "ER025",
        "WARNING",
        "Workbook Expected IRR Diverges",
        "Workbook expected IRR differs materially from HAP.",
        "Reconcile return assumptions.",
    ),
    "ER026": _rule(
        "ER026",
        "WARNING",
        "Workbook Expected CAGR Diverges",
        "Workbook expected CAGR differs materially from HAP.",
        "Reconcile return assumptions.",
    ),
    "ER027": _rule(
        "ER027",
        "POSITIVE",
        "Workbook Expected Return Aligned",
        "Workbook expected return metrics align with HAP.",
        "None.",
    ),
    "ER028": _rule(
        "ER028",
        "INFO",
        "HAP Could Not Reproduce Workbook Return",
        "Workbook return present but HAP cannot compute equivalent.",
        "Supply missing inputs.",
    ),
    "ER029": _rule(
        "ER029",
        "INFO",
        "Short Holding Period Assumption",
        "Holding period shorter than standard 5-year window.",
        "Document holding period rationale.",
    ),
    "ER030": _rule(
        "ER030",
        "CRITICAL",
        "Insufficient Expected Return Evidence",
        "Cannot estimate a reliable expected return.",
        "Request price, valuation, and growth inputs.",
    ),
}


class ExpectedReturnRuleInputs:
    def __init__(
        self,
        *,
        expected_cagr: float | None = None,
        expected_irr: float | None = None,
        growth_contribution: float | None = None,
        dividend_yield: float | None = None,
        buyback_yield: float | None = None,
        valuation_reversion: float | None = None,
        multiple_expansion: float | None = None,
        sp500_expected_return: float = 0.08,
        peer_expected_return: float | None = None,
        holding_period_years: int = 5,
        valuation_available: bool = True,
        share_price_available: bool = True,
        dividend_cagr: float | None = None,
        eps_growth: float | None = None,
        fcf_growth: float | None = None,
        buybacks_exceed_fcf: bool = False,
        scenario_bear_cagr: float | None = None,
        scenario_bull_cagr: float | None = None,
        comparison_statuses: dict[str, str] | None = None,
        workbook_return_present: bool = False,
        hap_return_computable: bool = True,
        period: str | None = None,
        evidence_by_metric: dict[str, list[Evidence]] | None = None,
    ) -> None:
        self.expected_cagr = expected_cagr
        self.expected_irr = expected_irr
        self.growth_contribution = growth_contribution
        self.dividend_yield = dividend_yield
        self.buyback_yield = buyback_yield
        self.valuation_reversion = valuation_reversion
        self.multiple_expansion = multiple_expansion
        self.sp500_expected_return = sp500_expected_return
        self.peer_expected_return = peer_expected_return
        self.holding_period_years = holding_period_years
        self.valuation_available = valuation_available
        self.share_price_available = share_price_available
        self.dividend_cagr = dividend_cagr
        self.eps_growth = eps_growth
        self.fcf_growth = fcf_growth
        self.buybacks_exceed_fcf = buybacks_exceed_fcf
        self.scenario_bear_cagr = scenario_bear_cagr
        self.scenario_bull_cagr = scenario_bull_cagr
        self.comparison_statuses = comparison_statuses or {}
        self.workbook_return_present = workbook_return_present
        self.hap_return_computable = hap_return_computable
        self.period = period
        self.evidence_by_metric = evidence_by_metric or {}


def evaluate_expected_return_rules(inputs: ExpectedReturnRuleInputs) -> list[RuleHit]:
    hits: list[RuleHit] = []
    period = inputs.period
    cagr = inputs.expected_cagr

    def _ev(metric: str, value: float | None) -> list[Evidence]:
        if metric in inputs.evidence_by_metric and inputs.evidence_by_metric[metric]:
            return list(inputs.evidence_by_metric[metric])
        return [evidence_from_metric(metric=metric, value=value, period=period, confidence=0.85)]

    def _hit(rule_id: str, metrics: dict[str, float | None], metric_key: str) -> None:
        hits.append(
            RuleHit(
                rule=EXPECTED_RETURN_RULES[rule_id],
                trigger_metrics=metrics,
                periods=[period] if period else [],
                evidence=_ev(metric_key, metrics.get(metric_key)),
            )
        )

    if not inputs.share_price_available:
        _hit("ER020", {"SHARE_PRICE": 0.0}, "SHARE_PRICE")
    if not inputs.valuation_available:
        _hit("ER019", {"FAIR_VALUE": 0.0}, "FAIR_VALUE_BASE")

    if cagr is not None:
        if cagr > 0.15:
            _hit("ER001", {"EXPECTED_CAGR": cagr}, "EXPECTED_CAGR")
        elif 0.10 <= cagr <= 0.15:
            _hit("ER002", {"EXPECTED_CAGR": cagr}, "EXPECTED_CAGR")
        elif 0.08 <= cagr < 0.10:
            _hit("ER003", {"EXPECTED_CAGR": cagr}, "EXPECTED_CAGR")
        elif 0.05 <= cagr < 0.08:
            _hit("ER004", {"EXPECTED_CAGR": cagr}, "EXPECTED_CAGR")
        elif 0.0 <= cagr < 0.05:
            _hit("ER005", {"EXPECTED_CAGR": cagr}, "EXPECTED_CAGR")
        elif cagr < 0:
            _hit("ER006", {"EXPECTED_CAGR": cagr}, "EXPECTED_CAGR")

    if cagr is not None and cagr >= inputs.sp500_expected_return + 0.03:
        _hit(
            "ER007",
            {"EXPECTED_CAGR": cagr, "SP500_EXPECTED_RETURN": inputs.sp500_expected_return},
            "EXPECTED_CAGR",
        )
    elif cagr is not None and cagr < inputs.sp500_expected_return:
        _hit(
            "ER008",
            {"EXPECTED_CAGR": cagr, "SP500_EXPECTED_RETURN": inputs.sp500_expected_return},
            "EXPECTED_CAGR",
        )

    if (
        cagr is not None
        and inputs.peer_expected_return is not None
        and cagr < inputs.peer_expected_return
    ):
        _hit(
            "ER009",
            {"EXPECTED_CAGR": cagr, "PEER_EXPECTED_RETURN": inputs.peer_expected_return},
            "EXPECTED_CAGR",
        )

    if inputs.valuation_reversion is not None and inputs.valuation_reversion < 0:
        _hit("ER010", {"VALUATION_REVERSION": inputs.valuation_reversion}, "VALUATION_REVERSION")

    if (
        cagr is not None
        and inputs.valuation_reversion is not None
        and cagr > 0
        and inputs.valuation_reversion / cagr > 0.50
    ):
        _hit(
            "ER011",
            {"VALUATION_REVERSION": inputs.valuation_reversion, "EXPECTED_CAGR": cagr},
            "VALUATION_REVERSION",
        )

    if inputs.growth_contribution is not None and inputs.growth_contribution < 0:
        _hit("ER012", {"GROWTH_CONTRIBUTION": inputs.growth_contribution}, "GROWTH_CONTRIBUTION")

    if inputs.dividend_yield is not None and inputs.dividend_yield > 0.02 and (cagr or 0) > 0:
        _hit("ER013", {"DIVIDEND_YIELD": inputs.dividend_yield}, "DIVIDEND_YIELD")
    if inputs.buyback_yield is not None and inputs.buyback_yield > 0.02:
        _hit("ER014", {"BUYBACK_YIELD": inputs.buyback_yield}, "BUYBACK_YIELD")
    if inputs.dividend_yield is not None and inputs.dividend_yield > 0.08:
        _hit("ER015", {"DIVIDEND_YIELD": inputs.dividend_yield}, "DIVIDEND_YIELD")
    if inputs.buybacks_exceed_fcf:
        _hit("ER016", {"BUYBACKS_EXCEED_FCF": 1.0}, "BUYBACK_YIELD")

    if (
        inputs.dividend_cagr is not None
        and inputs.eps_growth is not None
        and inputs.dividend_cagr > inputs.eps_growth + 0.02
    ):
        _hit(
            "ER017",
            {"DIVIDEND_CAGR": inputs.dividend_cagr, "EPS_GROWTH": inputs.eps_growth},
            "DIVIDEND_YIELD",
        )

    if (
        inputs.fcf_growth is not None
        and inputs.eps_growth is not None
        and inputs.fcf_growth < inputs.eps_growth - 0.03
    ):
        _hit(
            "ER018",
            {"FCF_GROWTH": inputs.fcf_growth, "EPS_GROWTH": inputs.eps_growth},
            "GROWTH_CONTRIBUTION",
        )

    if inputs.multiple_expansion is not None and inputs.multiple_expansion > 0.03:
        _hit("ER021", {"MULTIPLE_EXPANSION": inputs.multiple_expansion}, "MULTIPLE_EXPANSION")

    if inputs.scenario_bear_cagr is not None and inputs.scenario_bear_cagr < 0:
        _hit("ER022", {"SCENARIO_BEAR_CAGR": inputs.scenario_bear_cagr}, "EXPECTED_CAGR")
    if inputs.scenario_bull_cagr is not None and inputs.scenario_bull_cagr > 0.20:
        _hit("ER023", {"SCENARIO_BULL_CAGR": inputs.scenario_bull_cagr}, "EXPECTED_CAGR")
    if (
        inputs.scenario_bear_cagr is not None
        and inputs.scenario_bull_cagr is not None
        and inputs.scenario_bull_cagr - inputs.scenario_bear_cagr > 0.10
    ):
        _hit(
            "ER024",
            {
                "SCENARIO_BEAR_CAGR": inputs.scenario_bear_cagr,
                "SCENARIO_BULL_CAGR": inputs.scenario_bull_cagr,
            },
            "EXPECTED_CAGR",
        )

    statuses = inputs.comparison_statuses
    if statuses.get("EXPECTED_IRR") == "divergent":
        _hit("ER025", {"WORKBOOK_IRR_STATUS": 1.0}, "EXPECTED_IRR")
    if statuses.get("EXPECTED_CAGR") == "divergent":
        _hit("ER026", {"WORKBOOK_CAGR_STATUS": 1.0}, "EXPECTED_CAGR")
    irr_ok = statuses.get("EXPECTED_IRR") in {"match", "within_tolerance"}
    cagr_ok = statuses.get("EXPECTED_CAGR") in {"match", "within_tolerance"}
    if irr_ok or cagr_ok:
        _hit("ER027", {"WORKBOOK_RETURN_STATUS": 1.0}, "EXPECTED_CAGR")
    if inputs.workbook_return_present and not inputs.hap_return_computable:
        _hit("ER028", {"HAP_REPRODUCTION": 0.0}, "EXPECTED_CAGR")

    if inputs.holding_period_years < 5:
        _hit("ER029", {"HOLDING_PERIOD_YEARS": float(inputs.holding_period_years)}, "HOLDING_PERIOD_YEARS")

    if cagr is None and not inputs.share_price_available and not inputs.valuation_available:
        _hit("ER030", {"EXPECTED_CAGR": 0.0}, "EXPECTED_CAGR")
    elif cagr is None and inputs.share_price_available and not inputs.valuation_available:
        _hit("ER030", {"EXPECTED_CAGR": 0.0}, "EXPECTED_CAGR")

    return hits
