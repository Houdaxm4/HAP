"""Enterprise Valuation rules VA001–VA038 (ENTERPRISE_VALUATION_MODULE_SPEC.md)."""

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
        category="valuation",
        severity=severity,  # type: ignore[arg-type]
        finding=finding,
        explanation=explanation,
        suggested_analyst_action=action,
    )


VALUATION_RULES: dict[str, RuleDefinition] = {
    "VA001": _rule(
        "VA001",
        "POSITIVE",
        "Highly Attractive Valuation",
        "Base-case intrinsic value exceeds market price by more than 30%.",
        "None.",
    ),
    "VA002": _rule(
        "VA002",
        "POSITIVE",
        "Attractive Valuation",
        "Meaningful but moderate margin of safety.",
        "None.",
    ),
    "VA003": _rule(
        "VA003",
        "WARNING",
        "Limited Upside",
        "Little room for error at current price.",
        "Tighten assumption review; stress-test bear case.",
    ),
    "VA004": _rule(
        "VA004",
        "WARNING",
        "Potentially Overvalued",
        "Base-case intrinsic value is below market price.",
        "Review growth and margin assumptions; compare reverse DCF.",
    ),
    "VA005": _rule(
        "VA005",
        "WARNING",
        "Market Implies Aggressive Growth",
        "Current price requires growth above plausible long-run bounds.",
        "Challenge forecast; review competitive outlook.",
    ),
    "VA006": _rule(
        "VA006",
        "POSITIVE",
        "Market Pricing Pessimism",
        "Price implies decline while base case shows material MOS.",
        "Validate whether pessimism is warranted.",
    ),
    "VA007": _rule(
        "VA007",
        "INFO",
        "Reverse DCF Not Reliable",
        "Inputs do not support a stable reverse DCF solution.",
        "Rely on other methods; fix WACC/terminal spread.",
    ),
    "VA008": _rule(
        "VA008",
        "WARNING",
        "WACC May Be Too Low",
        "Discount rate below typical equity risk floor.",
        "Revise WACC; document build-up.",
    ),
    "VA009": _rule(
        "VA009",
        "WARNING",
        "WACC May Be Too High",
        "Discount rate may over-penalize long-duration cash flows.",
        "Revise WACC; review beta and capital structure.",
    ),
    "VA010": _rule(
        "VA010",
        "CRITICAL",
        "WACC Inconsistent With Risk",
        "Discount rate does not appear to price equity risk.",
        "Revise WACC immediately.",
    ),
    "VA011": _rule(
        "VA011",
        "WARNING",
        "Terminal Growth Above GDP",
        "Perpetuity growth exceeds nominal GDP anchor.",
        "Revise terminal growth.",
    ),
    "VA012": _rule(
        "VA012",
        "CRITICAL",
        "Unsustainable Terminal Growth",
        "Terminal growth above 5% is rarely sustainable.",
        "Revise terminal growth.",
    ),
    "VA013": _rule(
        "VA013",
        "WARNING",
        "Declining Terminal State",
        "Valuation assumes perpetual decline.",
        "Confirm structural decline narrative.",
    ),
    "VA014": _rule(
        "VA014",
        "WARNING",
        "DCF Dominated By Terminal Value",
        "More than 75% of DCF value from terminal period.",
        "Extend forecast; review terminal assumptions.",
    ),
    "VA015": _rule(
        "VA015",
        "INFO",
        "Short Forecast Horizon",
        "Explicit forecast shorter than standard 5-year window.",
        "Extend forecast or document rationale.",
    ),
    "VA016": _rule(
        "VA016",
        "WARNING",
        "Negative FCF In Forecast",
        "DCF relies on future cash flows not yet realized.",
        "Document turnaround path; use bear weighting.",
    ),
    "VA017": _rule(
        "VA017",
        "INFO",
        "DCF Valuation Unavailable",
        "Insufficient inputs for DCF.",
        "Supply WACC and FCF forecast inputs.",
    ),
    "VA018": _rule(
        "VA018",
        "WARNING",
        "Bear Case Does Not Support Margin Of Safety",
        "Even conservative scenario below current price.",
        "Revisit assumptions or acknowledge limited downside cushion.",
    ),
    "VA019": _rule(
        "VA019",
        "WARNING",
        "Valuation Methods Disagree Materially",
        "Methods span more than 40% of base value.",
        "Reconcile method inputs; prioritize most economic method.",
    ),
    "VA020": _rule(
        "VA020",
        "INFO",
        "Valuation Based On Single Method",
        "No triangulation across methods.",
        "Add peer multiples or owner earnings cross-check.",
    ),
    "VA021": _rule(
        "VA021",
        "WARNING",
        "Multiple Materially Above Peers",
        "Market or model multiple exceeds peer upper range.",
        "Review peer set and growth differentials.",
    ),
    "VA022": _rule(
        "VA022",
        "POSITIVE",
        "Discount To Peers",
        "Valuation below peer lower bound with positive MOS.",
        "Verify peer comparability.",
    ),
    "VA023": _rule(
        "VA023",
        "INFO",
        "Peer Multiples Not Available",
        "Cannot cross-check vs peers.",
        "Request industry research / peer set.",
    ),
    "VA024": _rule(
        "VA024",
        "WARNING",
        "Historical Multiple Extreme",
        "Trading rich vs own history.",
        "Review whether fundamentals justify premium.",
    ),
    "VA025": _rule(
        "VA025",
        "POSITIVE",
        "Historical Valuation Discount",
        "Below company's own typical multiple band.",
        "Confirm regime change not warranted.",
    ),
    "VA026": _rule(
        "VA026",
        "WARNING",
        "Owner Earnings Below Reported Earnings",
        "Cash economic earnings lag accounting earnings.",
        "Review capex intensity and working capital.",
    ),
    "VA027": _rule(
        "VA027",
        "POSITIVE",
        "Owner Earnings Confirms DCF",
        "Independent methods agree with attractive MOS.",
        "None.",
    ),
    "VA028": _rule(
        "VA028",
        "WARNING",
        "Net Debt Bridge Uncertain",
        "EV to equity conversion may be unreliable.",
        "Reconcile net debt; review capital structure.",
    ),
    "VA029": _rule(
        "VA029",
        "WARNING",
        "Leverage Amplifies Valuation Error",
        "Small EV errors swing equity materially.",
        "Review debt and cash; stress EV sensitivity.",
    ),
    "VA030": _rule(
        "VA030",
        "WARNING",
        "Workbook Intrinsic Value Diverges From HAP",
        "Analyst workbook IV differs materially from HAP computation.",
        "Reconcile inputs; investigate workbook formula.",
    ),
    "VA031": _rule(
        "VA031",
        "WARNING",
        "Workbook Margin Of Safety Diverges",
        "MOS formula or price input may differ.",
        "Reconcile price, share count, and fair value cells.",
    ),
    "VA032": _rule(
        "VA032",
        "WARNING",
        "Workbook WACC Diverges",
        "Discount rate assumptions differ.",
        "Revise WACC build-up; align assumptions.",
    ),
    "VA033": _rule(
        "VA033",
        "WARNING",
        "Workbook Terminal Growth Diverges",
        "Perpetuity assumptions differ.",
        "Revise terminal growth; document rationale.",
    ),
    "VA034": _rule(
        "VA034",
        "POSITIVE",
        "Workbook Valuation Aligned With HAP",
        "Independent HAP valuation confirms workbook fair value.",
        "None.",
    ),
    "VA035": _rule(
        "VA035",
        "INFO",
        "HAP Could Not Reproduce Workbook Valuation",
        "Missing inputs prevent HAP from validating workbook.",
        "Supply missing assumptions.",
    ),
    "VA036": _rule(
        "VA036",
        "WARNING",
        "Cyclical Peak Normalization Required",
        "Normalized earnings may be lower than current.",
        "Use through-cycle margins in valuation.",
    ),
    "VA037": _rule(
        "VA037",
        "CRITICAL",
        "Distressed Valuation Uncertainty",
        "Equity value relies on turnaround not in base statements.",
        "Model restructuring; widen bear case.",
    ),
    "VA038": _rule(
        "VA038",
        "CRITICAL",
        "Insufficient Valuation Evidence",
        "Cannot form a reliable view of worth.",
        "Request market data and valuation assumptions.",
    ),
}


class ValuationRuleInputs:
    def __init__(
        self,
        *,
        margin_of_safety: float | None = None,
        fair_value_base: float | None = None,
        share_price: float | None = None,
        reverse_dcf_implied_growth: float | None = None,
        reverse_dcf_implied_fcf_cagr: float | None = None,
        reverse_dcf_solvable: bool = False,
        wacc: float | None = None,
        risk_free_rate: float | None = None,
        terminal_growth: float | None = None,
        gdp_growth: float | None = None,
        dcf_terminal_share: float | None = None,
        forecast_years: int | None = None,
        negative_forecast_fcf: bool = False,
        turnaround_plan: bool = False,
        dcf_available: bool = False,
        scenario_bear_value: float | None = None,
        method_spread: float | None = None,
        method_count: int = 0,
        implied_ev_to_ebitda: float | None = None,
        peer_p25: float | None = None,
        peer_p75: float | None = None,
        peer_median: float | None = None,
        historical_median_multiple: float | None = None,
        multiples_method_available: bool = False,
        owner_earnings_run_rate: float | None = None,
        latest_net_income: float | None = None,
        oe_value_per_share: float | None = None,
        dcf_value_per_share: float | None = None,
        net_debt_uncertain: bool = False,
        net_debt_to_ev: float | None = None,
        equity_sensitivity_high: bool = False,
        cyclicality_flag: bool = False,
        margin_vs_10y_median: float | None = None,
        negative_fcf_years: int = 0,
        hap_equity_value: float | None = None,
        comparison_statuses: dict[str, str] | None = None,
        workbook_valuation_present: bool = False,
        hap_valuation_computable: bool = True,
        period: str | None = None,
        evidence_by_metric: dict[str, list[Evidence]] | None = None,
    ) -> None:
        self.margin_of_safety = margin_of_safety
        self.fair_value_base = fair_value_base
        self.share_price = share_price
        self.reverse_dcf_implied_growth = reverse_dcf_implied_growth
        self.reverse_dcf_implied_fcf_cagr = reverse_dcf_implied_fcf_cagr
        self.reverse_dcf_solvable = reverse_dcf_solvable
        self.wacc = wacc
        self.risk_free_rate = risk_free_rate
        self.terminal_growth = terminal_growth
        self.gdp_growth = gdp_growth
        self.dcf_terminal_share = dcf_terminal_share
        self.forecast_years = forecast_years
        self.negative_forecast_fcf = negative_forecast_fcf
        self.turnaround_plan = turnaround_plan
        self.dcf_available = dcf_available
        self.scenario_bear_value = scenario_bear_value
        self.method_spread = method_spread
        self.method_count = method_count
        self.implied_ev_to_ebitda = implied_ev_to_ebitda
        self.peer_p25 = peer_p25
        self.peer_p75 = peer_p75
        self.peer_median = peer_median
        self.historical_median_multiple = historical_median_multiple
        self.multiples_method_available = multiples_method_available
        self.owner_earnings_run_rate = owner_earnings_run_rate
        self.latest_net_income = latest_net_income
        self.oe_value_per_share = oe_value_per_share
        self.dcf_value_per_share = dcf_value_per_share
        self.net_debt_uncertain = net_debt_uncertain
        self.net_debt_to_ev = net_debt_to_ev
        self.equity_sensitivity_high = equity_sensitivity_high
        self.cyclicality_flag = cyclicality_flag
        self.margin_vs_10y_median = margin_vs_10y_median
        self.negative_fcf_years = negative_fcf_years
        self.hap_equity_value = hap_equity_value
        self.comparison_statuses = comparison_statuses or {}
        self.workbook_valuation_present = workbook_valuation_present
        self.hap_valuation_computable = hap_valuation_computable
        self.period = period
        self.evidence_by_metric = evidence_by_metric or {}


def evaluate_valuation_rules(inputs: ValuationRuleInputs) -> list[RuleHit]:
    hits: list[RuleHit] = []
    period = inputs.period
    gdp = inputs.gdp_growth if inputs.gdp_growth is not None else 0.04

    def _ev(metric: str, value: float | None) -> list[Evidence]:
        if metric in inputs.evidence_by_metric and inputs.evidence_by_metric[metric]:
            return list(inputs.evidence_by_metric[metric])
        return [evidence_from_metric(metric=metric, value=value, period=period, confidence=0.85)]

    def _hit(rule_id: str, metrics: dict[str, float | None], metric_key: str) -> None:
        hits.append(
            RuleHit(
                rule=VALUATION_RULES[rule_id],
                trigger_metrics=metrics,
                periods=[period] if period else [],
                evidence=_ev(metric_key, metrics.get(metric_key)),
            )
        )

    mos = inputs.margin_of_safety
    if mos is not None and mos > 0.30:
        _hit("VA001", {"MARGIN_OF_SAFETY": mos}, "MARGIN_OF_SAFETY")
    elif mos is not None and 0.15 <= mos <= 0.30:
        _hit("VA002", {"MARGIN_OF_SAFETY": mos}, "MARGIN_OF_SAFETY")
    elif mos is not None and 0.0 <= mos < 0.10:
        _hit("VA003", {"MARGIN_OF_SAFETY": mos}, "MARGIN_OF_SAFETY")
    elif (
        inputs.fair_value_base is not None
        and inputs.share_price is not None
        and inputs.fair_value_base < inputs.share_price
    ):
        _hit("VA004", {"FAIR_VALUE_BASE": inputs.fair_value_base, "SHARE_PRICE": inputs.share_price}, "MARGIN_OF_SAFETY")

    implied_g = inputs.reverse_dcf_implied_growth
    if implied_g is not None and (
        implied_g > gdp + 0.06
        or (
            inputs.reverse_dcf_implied_fcf_cagr is not None
            and inputs.reverse_dcf_implied_fcf_cagr > 0.25
        )
    ):
        _hit(
            "VA005",
            {
                "REVERSE_DCF_IMPLIED_GROWTH": implied_g,
                "REVERSE_DCF_IMPLIED_FCF_CAGR": inputs.reverse_dcf_implied_fcf_cagr,
            },
            "REVERSE_DCF_IMPLIED_GROWTH",
        )
    elif implied_g is not None and implied_g < 0 and mos is not None and mos > 0.15:
        _hit("VA006", {"REVERSE_DCF_IMPLIED_GROWTH": implied_g, "MARGIN_OF_SAFETY": mos}, "REVERSE_DCF_IMPLIED_GROWTH")

    if not inputs.reverse_dcf_solvable and (
        (inputs.wacc is not None and inputs.terminal_growth is not None and inputs.wacc <= inputs.terminal_growth)
        or (inputs.latest_net_income is not None and inputs.negative_fcf_years >= 3 and not inputs.turnaround_plan)
    ):
        _hit("VA007", {"REVERSE_DCF_SOLVABLE": 0.0}, "REVERSE_DCF_IMPLIED_GROWTH")

    if inputs.wacc is not None and inputs.wacc < 0.06:
        _hit("VA008", {"WACC": inputs.wacc}, "WACC")
    if inputs.wacc is not None and inputs.wacc > 0.14:
        _hit("VA009", {"WACC": inputs.wacc}, "WACC")
    if (
        inputs.wacc is not None
        and inputs.risk_free_rate is not None
        and inputs.wacc < inputs.risk_free_rate + 0.03
    ):
        _hit("VA010", {"WACC": inputs.wacc, "RISK_FREE_RATE": inputs.risk_free_rate}, "WACC")

    if inputs.terminal_growth is not None and inputs.gdp_growth is not None and inputs.terminal_growth > inputs.gdp_growth:
        _hit("VA011", {"TERMINAL_GROWTH": inputs.terminal_growth}, "TERMINAL_GROWTH")
    if inputs.terminal_growth is not None and inputs.terminal_growth > 0.05:
        _hit("VA012", {"TERMINAL_GROWTH": inputs.terminal_growth}, "TERMINAL_GROWTH")
    if inputs.terminal_growth is not None and inputs.terminal_growth < 0:
        _hit("VA013", {"TERMINAL_GROWTH": inputs.terminal_growth}, "TERMINAL_GROWTH")

    if inputs.dcf_terminal_share is not None and inputs.dcf_terminal_share > 0.75:
        _hit("VA014", {"DCF_TERMINAL_VALUE_SHARE": inputs.dcf_terminal_share}, "DCF_TERMINAL_VALUE_SHARE")
    if inputs.forecast_years is not None and inputs.forecast_years < 5:
        _hit("VA015", {"FORECAST_YEARS": float(inputs.forecast_years)}, "FORECAST_YEARS")
    if inputs.negative_forecast_fcf and not inputs.turnaround_plan:
        _hit("VA016", {"NEGATIVE_FCF_FORECAST": 1.0}, "DCF_VALUE_PER_SHARE")
    if not inputs.dcf_available:
        _hit("VA017", {"DCF_AVAILABLE": 0.0}, "DCF_VALUE_PER_SHARE")

    if (
        inputs.scenario_bear_value is not None
        and inputs.share_price is not None
        and inputs.scenario_bear_value < inputs.share_price
    ):
        _hit(
            "VA018",
            {"SCENARIO_BEAR_VALUE_PER_SHARE": inputs.scenario_bear_value, "SHARE_PRICE": inputs.share_price},
            "SCENARIO_BEAR_VALUE_PER_SHARE",
        )

    if inputs.method_spread is not None and inputs.method_spread > 0.40:
        _hit("VA019", {"METHOD_SPREAD": inputs.method_spread}, "METHOD_SPREAD")
    if inputs.method_count == 1:
        _hit("VA020", {"METHOD_COUNT": float(inputs.method_count)}, "METHOD_COUNT")

    peer_p75 = inputs.peer_p75
    if inputs.implied_ev_to_ebitda is not None and peer_p75 is not None:
        if inputs.implied_ev_to_ebitda > peer_p75 * 1.15:
            _hit("VA021", {"IMPLIED_EV_EBITDA": inputs.implied_ev_to_ebitda}, "IMPLIED_EV_EBITDA")
        elif (
            inputs.peer_median is not None
            and inputs.share_price is not None
            and inputs.fair_value_base is not None
            and inputs.implied_ev_to_ebitda > peer_p75
            and inputs.fair_value_base < inputs.share_price
        ):
            _hit("VA021", {"IMPLIED_EV_EBITDA": inputs.implied_ev_to_ebitda}, "IMPLIED_EV_EBITDA")

    if (
        inputs.implied_ev_to_ebitda is not None
        and inputs.peer_p25 is not None
        and inputs.implied_ev_to_ebitda < inputs.peer_p25 * 0.85
        and mos is not None
        and mos > 0.10
    ):
        _hit("VA022", {"IMPLIED_EV_EBITDA": inputs.implied_ev_to_ebitda, "MARGIN_OF_SAFETY": mos}, "IMPLIED_EV_EBITDA")

    if not inputs.multiples_method_available and inputs.peer_median is None:
        _hit("VA023", {"PEER_DATA": 0.0}, "PEER_MEDIAN_EV_EBITDA")

    if (
        inputs.implied_ev_to_ebitda is not None
        and inputs.historical_median_multiple is not None
        and inputs.implied_ev_to_ebitda > inputs.historical_median_multiple * 1.50
    ):
        _hit("VA024", {"IMPLIED_EV_EBITDA": inputs.implied_ev_to_ebitda}, "IMPLIED_EV_EBITDA")
    if (
        inputs.implied_ev_to_ebitda is not None
        and inputs.historical_median_multiple is not None
        and inputs.implied_ev_to_ebitda < inputs.historical_median_multiple * 0.75
        and mos is not None
        and mos > 0.10
    ):
        _hit("VA025", {"IMPLIED_EV_EBITDA": inputs.implied_ev_to_ebitda, "MARGIN_OF_SAFETY": mos}, "IMPLIED_EV_EBITDA")

    if (
        inputs.owner_earnings_run_rate is not None
        and inputs.latest_net_income is not None
        and inputs.latest_net_income > 0
        and inputs.owner_earnings_run_rate < inputs.latest_net_income * 0.70
    ):
        _hit(
            "VA026",
            {"OWNER_EARNINGS_RUN_RATE": inputs.owner_earnings_run_rate, "NET_INCOME": inputs.latest_net_income},
            "OWNER_EARNINGS_RUN_RATE",
        )

    if (
        inputs.oe_value_per_share is not None
        and inputs.dcf_value_per_share is not None
        and inputs.dcf_value_per_share > 0
        and abs(inputs.oe_value_per_share - inputs.dcf_value_per_share) / inputs.dcf_value_per_share <= 0.10
        and mos is not None
        and mos > 0.15
    ):
        _hit(
            "VA027",
            {
                "OE_VALUE_PER_SHARE": inputs.oe_value_per_share,
                "DCF_VALUE_PER_SHARE": inputs.dcf_value_per_share,
            },
            "OE_VALUE_PER_SHARE",
        )

    if inputs.net_debt_uncertain:
        _hit("VA028", {"NET_DEBT_UNCERTAIN": 1.0}, "NET_DEBT")
    if inputs.equity_sensitivity_high:
        _hit("VA029", {"NET_DEBT_TO_EV": inputs.net_debt_to_ev}, "NET_DEBT")

    statuses = inputs.comparison_statuses
    if statuses.get("INTRINSIC_VALUE") == "divergent":
        _hit("VA030", {"WORKBOOK_IV_STATUS": 1.0}, "HAP_INTRINSIC_VALUE_PER_SHARE")
    if statuses.get("MARGIN_OF_SAFETY") == "divergent":
        _hit("VA031", {"WORKBOOK_MOS_STATUS": 1.0}, "MARGIN_OF_SAFETY")
    if statuses.get("WACC") == "divergent":
        _hit("VA032", {"WORKBOOK_WACC_STATUS": 1.0}, "WACC")
    if statuses.get("TERMINAL_GROWTH") == "divergent":
        _hit("VA033", {"WORKBOOK_TG_STATUS": 1.0}, "TERMINAL_GROWTH")
    if statuses.get("FAIR_VALUE") in {"match", "within_tolerance"}:
        _hit("VA034", {"WORKBOOK_FV_STATUS": 1.0}, "FAIR_VALUE_BASE")
    if inputs.workbook_valuation_present and not inputs.hap_valuation_computable:
        _hit("VA035", {"HAP_REPRODUCTION": 0.0}, "FAIR_VALUE_BASE")

    if (
        inputs.cyclicality_flag
        and inputs.margin_vs_10y_median is not None
        and inputs.margin_vs_10y_median > 1.20
        and inputs.multiples_method_available
    ):
        _hit("VA036", {"MARGIN_VS_10Y_MEDIAN": inputs.margin_vs_10y_median}, "OPERATING_MARGIN")

    distressed = (
        (inputs.fair_value_base is not None and inputs.fair_value_base < 0)
        or (inputs.negative_fcf_years >= 3 and not inputs.turnaround_plan)
    )
    if distressed and inputs.hap_equity_value is not None and inputs.hap_equity_value > 0:
        _hit("VA037", {"DISTRESSED": 1.0}, "HAP_EQUITY_VALUE")

    if inputs.method_count < 2 and inputs.share_price is None:
        _hit("VA038", {"METHOD_COUNT": float(inputs.method_count)}, "METHOD_COUNT")

    return hits
