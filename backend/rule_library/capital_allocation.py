"""Capital Allocation rules CA001–CA025 (RULE_LIBRARY.md + extended deterministic set)."""

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
        category="capital_allocation",
        severity=severity,  # type: ignore[arg-type]
        finding=finding,
        explanation=explanation,
        suggested_analyst_action=action,
    )


CAPITAL_ALLOCATION_RULES: dict[str, RuleDefinition] = {
    "CA001": _rule(
        "CA001",
        "POSITIVE",
        "Excellent Capital Allocation",
        "Returns on invested capital are improving while share count is declining.",
        "None.",
    ),
    "CA002": _rule(
        "CA002",
        "WARNING",
        "Potential Value Destructive Acquisition",
        "Material acquisition activity coincides with declining ROIC.",
        "Review acquisition economics and goodwill/intangible buildup.",
    ),
    "CA003": _rule(
        "CA003",
        "POSITIVE",
        "Shareholder Friendly Management",
        "Dividends have grown consistently across the evaluation window.",
        "None.",
    ),
    "CA004": _rule(
        "CA004",
        "POSITIVE",
        "Value Creating Buybacks",
        "Repurchases appear to have been executed below estimated intrinsic value.",
        "None.",
    ),
    "CA005": _rule(
        "CA005",
        "WARNING",
        "Aggressive Financial Engineering",
        "Share repurchases occurred while leverage rose materially.",
        "Review prudence of debt-funded buybacks.",
    ),
    "CA006": _rule(
        "CA006",
        "WARNING",
        "Deteriorating Reinvestment Returns",
        "ROIC declined over the evaluation window.",
        "Assess whether reinvestment is still earning attractive returns.",
    ),
    "CA007": _rule(
        "CA007",
        "WARNING",
        "Shareholder Dilution",
        "Share count is rising, diluting per-share ownership.",
        "Review equity issuance and compensation dilution.",
    ),
    "CA008": _rule(
        "CA008",
        "POSITIVE",
        "Disciplined Buybacks",
        "Repurchases are funded from free cash flow without excessive leverage.",
        "None.",
    ),
    "CA009": _rule(
        "CA009",
        "WARNING",
        "Unsustainable Dividend",
        "Cash dividends exceed free cash flow.",
        "Review payout sustainability and balance sheet flexibility.",
    ),
    "CA010": _rule(
        "CA010",
        "POSITIVE",
        "Value-Creating Reinvestment",
        "Reinvestment is elevated while ROIC exceeds the cost of capital.",
        "None.",
    ),
    "CA011": _rule(
        "CA011",
        "CRITICAL",
        "Value-Destructive Reinvestment",
        "Heavy reinvestment coincides with ROIC below the cost of capital.",
        "Challenge growth capex and acquisition returns.",
    ),
    "CA012": _rule(
        "CA012",
        "WARNING",
        "Empire Building Risk",
        "Acquisition-driven expansion with rising leverage and weak organic growth.",
        "Separate organic vs inorganic returns; stress-test integration risk.",
    ),
    "CA013": _rule(
        "CA013",
        "INFO",
        "Capital Hoarding",
        "Strong free cash flow with minimal dividends or buybacks.",
        "Assess whether excess cash should be returned or reinvested.",
    ),
    "CA014": _rule(
        "CA014",
        "POSITIVE",
        "Balanced Capital Return",
        "Dividends and buybacks are funded within free cash flow capacity.",
        "None.",
    ),
    "CA015": _rule(
        "CA015",
        "WARNING",
        "High Payout Risk",
        "Dividends consume a very high share of free cash flow.",
        "Model downside scenarios for payout coverage.",
    ),
    "CA016": _rule(
        "CA016",
        "POSITIVE",
        "Accretive Capital Return",
        "Net share count declined while earnings per share expanded.",
        "None.",
    ),
    "CA017": _rule(
        "CA017",
        "CRITICAL",
        "Acquisitions Masking Weak Core",
        "Reported growth appears acquisition-driven while organic returns weaken.",
        "Treat organic economics as primary allocation truth.",
    ),
    "CA018": _rule(
        "CA018",
        "POSITIVE",
        "Prudent Leverage Use",
        "Leverage was stable or declining during capital return activity.",
        "None.",
    ),
    "CA019": _rule(
        "CA019",
        "WARNING",
        "Leverage-Funded Expansion",
        "Debt rose materially alongside acquisition spending.",
        "Review whether leverage-funded deals earn adequate returns.",
    ),
    "CA020": _rule(
        "CA020",
        "POSITIVE",
        "Improving Economic Spread",
        "ROIC spread versus cost of capital is positive and improving.",
        "None.",
    ),
    "CA021": _rule(
        "CA021",
        "CRITICAL",
        "Economic Value Destruction",
        "ROIC is below the cost of capital on a sustained basis.",
        "Reassess reinvestment priorities and capital returns.",
    ),
    "CA022": _rule(
        "CA022",
        "WARNING",
        "Weak Retained Earnings Deployment",
        "Retained capital is not compounding at attractive incremental returns.",
        "Review internal reinvestment hurdle rates.",
    ),
    "CA023": _rule(
        "CA023",
        "WARNING",
        "Insufficient Allocation History",
        "Too little history to assess management capital allocation discipline.",
        "Request longer audited history before high-conviction use.",
    ),
    "CA024": _rule(
        "CA024",
        "POSITIVE",
        "Exemplary Capital Allocation",
        "Improving ROIC, disciplined returns to shareholders, and sustainable funding.",
        "None.",
    ),
    "CA025": _rule(
        "CA025",
        "INFO",
        "Incomplete Acquisition Disclosure",
        "Revenue step-ups suggest acquisitions without adequate spend disclosure.",
        "Request acquisition spend and return disclosures.",
    ),
}


class CapitalAllocationRuleInputs:
    def __init__(
        self,
        *,
        roic: float | None = None,
        roic_change: float | None = None,
        roic_spread: float | None = None,
        roic_spread_change: float | None = None,
        share_count_cagr: float | None = None,
        eps_cagr: float | None = None,
        buyback_to_fcf: float | None = None,
        payout_to_fcf: float | None = None,
        dividend_cagr: float | None = None,
        reinvestment_rate: float | None = None,
        inorganic_share: float | None = None,
        acquisition_intensity: float | None = None,
        debt_change: float | None = None,
        organic_rev_cagr: float | None = None,
        latest_fcf: float | None = None,
        total_dividends: float | None = None,
        total_buybacks: float | None = None,
        buybacks_below_intrinsic: bool = False,
        organic_data_available: bool = False,
        acquisition_data_available: bool = False,
        history_points: int = 0,
        period: str | None = None,
        periods: list[str] | None = None,
        dividend_by_period: dict[str, float] | None = None,
        evidence_by_metric: dict[str, list[Evidence]] | None = None,
    ) -> None:
        self.roic = roic
        self.roic_change = roic_change
        self.roic_spread = roic_spread
        self.roic_spread_change = roic_spread_change
        self.share_count_cagr = share_count_cagr
        self.eps_cagr = eps_cagr
        self.buyback_to_fcf = buyback_to_fcf
        self.payout_to_fcf = payout_to_fcf
        self.dividend_cagr = dividend_cagr
        self.reinvestment_rate = reinvestment_rate
        self.inorganic_share = inorganic_share
        self.acquisition_intensity = acquisition_intensity
        self.debt_change = debt_change
        self.organic_rev_cagr = organic_rev_cagr
        self.latest_fcf = latest_fcf
        self.total_dividends = total_dividends
        self.total_buybacks = total_buybacks
        self.buybacks_below_intrinsic = buybacks_below_intrinsic
        self.organic_data_available = organic_data_available
        self.acquisition_data_available = acquisition_data_available
        self.history_points = history_points
        self.period = period
        self.periods = periods or []
        self.dividend_by_period = dividend_by_period or {}
        self.evidence_by_metric = evidence_by_metric or {}


def evaluate_capital_allocation_rules(inputs: CapitalAllocationRuleInputs) -> list[RuleHit]:
    hits: list[RuleHit] = []
    period = inputs.period
    periods = inputs.periods

    def _ev(metric: str, value: float | None) -> list[Evidence]:
        if metric in inputs.evidence_by_metric and inputs.evidence_by_metric[metric]:
            return list(inputs.evidence_by_metric[metric])
        return [evidence_from_metric(metric=metric, value=value, period=period, confidence=0.85)]

    def _hit(rule_id: str, metrics: dict[str, float | None], metric_key: str) -> None:
        hits.append(
            RuleHit(
                rule=CAPITAL_ALLOCATION_RULES[rule_id],
                trigger_metrics=metrics,
                periods=periods[-5:] if periods else ([period] if period else []),
                evidence=_ev(metric_key, metrics.get(metric_key)),
            )
        )

    if inputs.history_points < 3:
        _hit("CA023", {"CA_HISTORY_YEARS": float(inputs.history_points)}, "CA_HISTORY_YEARS")

    if (
        inputs.roic_change is not None
        and inputs.roic_change > 0.02
        and inputs.share_count_cagr is not None
        and inputs.share_count_cagr < 0
    ):
        _hit(
            "CA001",
            {"ROIC_CHANGE": inputs.roic_change, "SHARE_COUNT_CAGR": inputs.share_count_cagr},
            "ROIC_CHANGE",
        )

    if (
        inputs.acquisition_intensity is not None
        and inputs.acquisition_intensity >= 0.15
        and inputs.roic_change is not None
        and inputs.roic_change < -0.02
    ):
        _hit(
            "CA002",
            {
                "ACQUISITION_INTENSITY": inputs.acquisition_intensity,
                "ROIC_CHANGE": inputs.roic_change,
            },
            "ACQUISITION_INTENSITY",
        )

    div_ordered = sorted(inputs.dividend_by_period.items(), key=lambda item: item[0])
    if len(div_ordered) >= 3:
        div_values = [value for _, value in div_ordered]
        if all(div_values[i] < div_values[i + 1] for i in range(len(div_values) - 1)):
            _hit("CA003", {"DIVIDEND_CAGR": inputs.dividend_cagr}, "DIVIDEND_CAGR")

    if inputs.buybacks_below_intrinsic:
        _hit("CA004", {"BUYBACK_BELOW_IV": 1.0}, "BUYBACK_TO_FCF")

    if (
        inputs.total_buybacks is not None
        and inputs.total_buybacks > 0
        and inputs.debt_change is not None
        and inputs.debt_change > 0.10
    ):
        _hit(
            "CA005",
            {"DEBT_CHANGE": inputs.debt_change, "BUYBACK_TO_FCF": inputs.buyback_to_fcf},
            "DEBT_CHANGE",
        )

    if inputs.roic_change is not None and inputs.roic_change < -0.02:
        _hit("CA006", {"ROIC_CHANGE": inputs.roic_change}, "ROIC_CHANGE")

    if inputs.share_count_cagr is not None and inputs.share_count_cagr > 0.03:
        _hit("CA007", {"SHARE_COUNT_CAGR": inputs.share_count_cagr}, "SHARE_COUNT_CAGR")

    if (
        inputs.buyback_to_fcf is not None
        and 0.05 <= inputs.buyback_to_fcf <= 0.45
        and inputs.latest_fcf is not None
        and inputs.latest_fcf > 0
        and (inputs.debt_change is None or inputs.debt_change <= 0.05)
    ):
        _hit("CA008", {"BUYBACK_TO_FCF": inputs.buyback_to_fcf}, "BUYBACK_TO_FCF")

    if (
        inputs.payout_to_fcf is not None
        and inputs.payout_to_fcf > 1.0
    ):
        _hit("CA009", {"PAYOUT_TO_FCF": inputs.payout_to_fcf}, "PAYOUT_TO_FCF")

    if (
        inputs.reinvestment_rate is not None
        and inputs.reinvestment_rate >= 0.25
        and inputs.roic_spread is not None
        and inputs.roic_spread > 0.02
    ):
        _hit(
            "CA010",
            {"REINVESTMENT_RATE": inputs.reinvestment_rate, "ROIC_SPREAD": inputs.roic_spread},
            "REINVESTMENT_RATE",
        )

    if (
        inputs.reinvestment_rate is not None
        and inputs.reinvestment_rate >= 0.30
        and inputs.roic_spread is not None
        and inputs.roic_spread < 0
    ):
        _hit(
            "CA011",
            {"REINVESTMENT_RATE": inputs.reinvestment_rate, "ROIC_SPREAD": inputs.roic_spread},
            "REINVESTMENT_RATE",
        )

    if (
        inputs.inorganic_share is not None
        and inputs.inorganic_share >= 0.30
        and inputs.debt_change is not None
        and inputs.debt_change > 0.08
        and inputs.organic_rev_cagr is not None
        and inputs.organic_rev_cagr < 0.03
    ):
        _hit(
            "CA012",
            {
                "INORGANIC_REV_SHARE": inputs.inorganic_share,
                "DEBT_CHANGE": inputs.debt_change,
            },
            "INORGANIC_REV_SHARE",
        )

    if (
        inputs.latest_fcf is not None
        and inputs.latest_fcf > 0
        and (inputs.total_buybacks or 0) < inputs.latest_fcf * 0.05
        and (inputs.total_dividends or 0) < inputs.latest_fcf * 0.10
    ):
        _hit("CA013", {"FCF": inputs.latest_fcf}, "FCF")

    if (
        inputs.latest_fcf is not None
        and inputs.latest_fcf > 0
        and inputs.payout_to_fcf is not None
        and inputs.payout_to_fcf <= 0.80
        and inputs.buyback_to_fcf is not None
        and inputs.buyback_to_fcf > 0
        and (inputs.payout_to_fcf + inputs.buyback_to_fcf) <= 0.85
    ):
        _hit("CA014", {"PAYOUT_TO_FCF": inputs.payout_to_fcf}, "PAYOUT_TO_FCF")

    if inputs.payout_to_fcf is not None and inputs.payout_to_fcf > 0.80:
        _hit("CA015", {"PAYOUT_TO_FCF": inputs.payout_to_fcf}, "PAYOUT_TO_FCF")

    if (
        inputs.share_count_cagr is not None
        and inputs.share_count_cagr < 0
        and inputs.eps_cagr is not None
        and inputs.eps_cagr > 0.05
    ):
        _hit(
            "CA016",
            {"SHARE_COUNT_CAGR": inputs.share_count_cagr, "EPS_CAGR": inputs.eps_cagr},
            "EPS_CAGR",
        )

    if (
        inputs.total_buybacks is not None
        and inputs.total_buybacks > 0
        and inputs.debt_change is not None
        and inputs.debt_change <= 0
    ):
        _hit("CA018", {"DEBT_CHANGE": inputs.debt_change}, "DEBT_CHANGE")

    if (
        inputs.acquisition_intensity is not None
        and inputs.acquisition_intensity >= 0.10
        and inputs.debt_change is not None
        and inputs.debt_change > 0.10
    ):
        _hit(
            "CA019",
            {
                "ACQUISITION_INTENSITY": inputs.acquisition_intensity,
                "DEBT_CHANGE": inputs.debt_change,
            },
            "ACQUISITION_INTENSITY",
        )

    if (
        inputs.roic_spread is not None
        and inputs.roic_spread > 0
        and inputs.roic_spread_change is not None
        and inputs.roic_spread_change > 0.01
    ):
        _hit(
            "CA020",
            {"ROIC_SPREAD": inputs.roic_spread, "ROIC_SPREAD_CHANGE": inputs.roic_spread_change},
            "ROIC_SPREAD",
        )

    if inputs.roic_spread is not None and inputs.roic_spread < -0.02:
        _hit("CA021", {"ROIC_SPREAD": inputs.roic_spread}, "ROIC_SPREAD")

    if (
        inputs.roic_change is not None
        and inputs.roic_change < 0
        and inputs.reinvestment_rate is not None
        and inputs.reinvestment_rate > 0.35
    ):
        _hit(
            "CA022",
            {"ROIC_CHANGE": inputs.roic_change, "REINVESTMENT_RATE": inputs.reinvestment_rate},
            "ROIC_CHANGE",
        )

    if (
        inputs.roic_change is not None
        and inputs.roic_change > 0.02
        and inputs.share_count_cagr is not None
        and inputs.share_count_cagr <= 0
        and inputs.payout_to_fcf is not None
        and inputs.payout_to_fcf <= 0.75
    ):
        _hit("CA024", {"ROIC_CHANGE": inputs.roic_change}, "ROIC_CHANGE")

    if (
        not inputs.acquisition_data_available
        and inputs.inorganic_share is not None
        and inputs.inorganic_share >= 0.20
    ):
        _hit("CA025", {"INORGANIC_REV_SHARE": inputs.inorganic_share}, "INORGANIC_REV_SHARE")

    if (
        inputs.organic_data_available
        and inputs.inorganic_share is not None
        and inputs.inorganic_share >= 0.25
        and inputs.organic_rev_cagr is not None
        and inputs.organic_rev_cagr < 0
    ):
        _hit(
            "CA017",
            {
                "INORGANIC_REV_SHARE": inputs.inorganic_share,
                "ORGANIC_REV_CAGR": inputs.organic_rev_cagr,
            },
            "ORGANIC_REV_CAGR",
        )

    return hits
