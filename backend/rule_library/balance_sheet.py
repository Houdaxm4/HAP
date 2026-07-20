"""Balance Sheet rules BS001–BS030 (RULE_LIBRARY.md + extended deterministic set)."""

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
        category="balance_sheet",
        severity=severity,  # type: ignore[arg-type]
        finding=finding,
        explanation=explanation,
        suggested_analyst_action=action,
    )


BALANCE_SHEET_RULES: dict[str, RuleDefinition] = {
    "BS001": _rule(
        "BS001",
        "POSITIVE",
        "Strong Liquidity",
        "Current ratio exceeds 2.0, indicating ample short-term liquidity.",
        "None.",
    ),
    "BS002": _rule(
        "BS002",
        "WARNING",
        "Liquidity Risk",
        "Current ratio is below 1.0 — current liabilities exceed current assets.",
        "Review near-term obligations and liquidity sources.",
    ),
    "BS003": _rule(
        "BS003",
        "CRITICAL",
        "Excessive Financial Leverage",
        "Debt to EBITDA exceeds 4.0x, indicating elevated leverage risk.",
        "Stress-test refinancing and covenant headroom.",
    ),
    "BS004": _rule(
        "BS004",
        "WARNING",
        "Debt Servicing Risk",
        "Interest coverage is below 3.0x.",
        "Review debt service capacity and maturity profile.",
    ),
    "BS005": _rule(
        "BS005",
        "POSITIVE",
        "Strong Financial Flexibility",
        "Net cash position — cash exceeds total debt.",
        "None.",
    ),
    "BS006": _rule(
        "BS006",
        "POSITIVE",
        "Balance Sheet Strengthening",
        "Total debt declined in every year of the evaluated window.",
        "None.",
    ),
    "BS007": _rule(
        "BS007",
        "POSITIVE",
        "Strong Quick Liquidity",
        "Quick ratio exceeds 1.5x.",
        "None.",
    ),
    "BS008": _rule(
        "BS008",
        "WARNING",
        "Quick Liquidity Risk",
        "Quick ratio is below 0.8x.",
        "Review receivables quality and inventory liquidation risk.",
    ),
    "BS009": _rule(
        "BS009",
        "POSITIVE",
        "High Cash Liquidity",
        "Cash ratio exceeds 0.5x of current liabilities.",
        "None.",
    ),
    "BS010": _rule(
        "BS010",
        "WARNING",
        "Minimal Cash Buffer",
        "Cash covers less than 10% of current liabilities.",
        "Assess liquidity runway and revolver availability.",
    ),
    "BS011": _rule(
        "BS011",
        "WARNING",
        "Elevated Leverage",
        "Debt to equity exceeds 2.0x.",
        "Review capital structure and equity cushion.",
    ),
    "BS012": _rule(
        "BS012",
        "POSITIVE",
        "Conservative Leverage",
        "Debt to equity is below 0.5x.",
        "None.",
    ),
    "BS013": _rule(
        "BS013",
        "CRITICAL",
        "High Net Leverage",
        "Net debt to EBITDA exceeds 3.0x.",
        "Review deleveraging path and free cash flow allocation.",
    ),
    "BS014": _rule(
        "BS014",
        "POSITIVE",
        "Modest Net Leverage",
        "Net debt to EBITDA is below 1.0x.",
        "None.",
    ),
    "BS015": _rule(
        "BS015",
        "POSITIVE",
        "Strong Cash vs Debt",
        "Cash represents more than 50% of total debt.",
        "None.",
    ),
    "BS016": _rule(
        "BS016",
        "WARNING",
        "Low Cash Relative to Debt",
        "Cash covers less than 10% of total debt.",
        "Assess refinancing risk and covenant flexibility.",
    ),
    "BS017": _rule(
        "BS017",
        "POSITIVE",
        "Exceptional Interest Coverage",
        "Interest coverage exceeds 8.0x.",
        "None.",
    ),
    "BS018": _rule(
        "BS018",
        "CRITICAL",
        "Distressed Interest Coverage",
        "Interest coverage is below 1.5x.",
        "Flag for committee review; stress-test earnings downturn.",
    ),
    "BS019": _rule(
        "BS019",
        "WARNING",
        "Incomplete Interest Coverage Data",
        "Material debt is reported without interest expense for coverage analysis.",
        "Request interest expense and debt maturity schedule.",
    ),
    "BS020": _rule(
        "BS020",
        "WARNING",
        "Working Capital Deficit",
        "Working capital is negative.",
        "Review short-term funding reliance and supplier terms.",
    ),
    "BS021": _rule(
        "BS021",
        "POSITIVE",
        "Working Capital Improving",
        "Working capital rose in every year of the evaluated window.",
        "None.",
    ),
    "BS022": _rule(
        "BS022",
        "WARNING",
        "Working Capital Deterioration",
        "Working capital trend is declining over the evaluation window.",
        "Normalize seasonal working capital swings before concluding.",
    ),
    "BS023": _rule(
        "BS023",
        "WARNING",
        "Rising Debt Load",
        "Total debt CAGR exceeds 10% over the evaluation window.",
        "Review debt classification and use of proceeds.",
    ),
    "BS024": _rule(
        "BS024",
        "POSITIVE",
        "Improving Liquidity",
        "Current ratio trend is improving over the evaluation window.",
        "None.",
    ),
    "BS025": _rule(
        "BS025",
        "WARNING",
        "Deteriorating Liquidity",
        "Current ratio trend is declining over the evaluation window.",
        "Investigate working capital drivers and near-term maturities.",
    ),
    "BS026": _rule(
        "BS026",
        "POSITIVE",
        "Deleveraging Trend",
        "Debt to equity is declining over the evaluation window.",
        "None.",
    ),
    "BS027": _rule(
        "BS027",
        "WARNING",
        "Increasing Leverage Trend",
        "Debt to equity is rising over the evaluation window.",
        "Review acquisition financing and shareholder distributions.",
    ),
    "BS028": _rule(
        "BS028",
        "WARNING",
        "Liability Growth Outpacing Assets",
        "Current liabilities are compounding faster than current assets.",
        "Review payables, accrued liabilities, and short-term borrowings.",
    ),
    "BS029": _rule(
        "BS029",
        "POSITIVE",
        "Fortress Balance Sheet",
        "Strong liquidity, modest leverage, and healthy interest coverage concurrently.",
        "None.",
    ),
    "BS030": _rule(
        "BS030",
        "WARNING",
        "Insufficient Balance Sheet History",
        "Too few balance sheet observations for robust leverage and liquidity conclusions.",
        "Request longer audited history before high-conviction use.",
    ),
}


class BalanceSheetRuleInputs:
    def __init__(
        self,
        *,
        current_ratio: float | None = None,
        quick_ratio: float | None = None,
        cash_ratio: float | None = None,
        debt_to_equity: float | None = None,
        debt_to_ebitda: float | None = None,
        net_debt: float | None = None,
        net_debt_to_ebitda: float | None = None,
        interest_coverage: float | None = None,
        cash_to_debt: float | None = None,
        working_capital: float | None = None,
        working_capital_by_period: dict[str, float] | None = None,
        debt_by_period: dict[str, float] | None = None,
        debt_cagr: float | None = None,
        current_assets_cagr: float | None = None,
        current_liabilities_cagr: float | None = None,
        liquidity_trend: float | None = None,
        leverage_trend: float | None = None,
        working_capital_trend: float | None = None,
        interest_expense_available: bool = True,
        material_debt: bool = False,
        balance_sheet_point_count: int = 0,
        off_balance_sheet_flag: bool = False,
        period: str | None = None,
        periods: list[str] | None = None,
        evidence_by_metric: dict[str, list[Evidence]] | None = None,
    ) -> None:
        self.current_ratio = current_ratio
        self.quick_ratio = quick_ratio
        self.cash_ratio = cash_ratio
        self.debt_to_equity = debt_to_equity
        self.debt_to_ebitda = debt_to_ebitda
        self.net_debt = net_debt
        self.net_debt_to_ebitda = net_debt_to_ebitda
        self.interest_coverage = interest_coverage
        self.cash_to_debt = cash_to_debt
        self.working_capital = working_capital
        self.working_capital_by_period = working_capital_by_period or {}
        self.debt_by_period = debt_by_period or {}
        self.debt_cagr = debt_cagr
        self.current_assets_cagr = current_assets_cagr
        self.current_liabilities_cagr = current_liabilities_cagr
        self.liquidity_trend = liquidity_trend
        self.leverage_trend = leverage_trend
        self.working_capital_trend = working_capital_trend
        self.interest_expense_available = interest_expense_available
        self.material_debt = material_debt
        self.balance_sheet_point_count = balance_sheet_point_count
        self.off_balance_sheet_flag = off_balance_sheet_flag
        self.period = period
        self.periods = periods or []
        self.evidence_by_metric = evidence_by_metric or {}


def evaluate_balance_sheet_rules(inputs: BalanceSheetRuleInputs) -> list[RuleHit]:
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
                rule=BALANCE_SHEET_RULES[rule_id],
                trigger_metrics=metrics,
                periods=periods[-5:] if periods else ([period] if period else []),
                evidence=_ev(metric_key, metrics.get(metric_key)),
            )
        )

    if inputs.balance_sheet_point_count < 3:
        _hit("BS030", {"BS_HISTORY_YEARS": float(inputs.balance_sheet_point_count)}, "BS_HISTORY_YEARS")

    if inputs.current_ratio is not None:
        if inputs.current_ratio > 2.0:
            _hit("BS001", {"CURRENT_RATIO": inputs.current_ratio}, "CURRENT_RATIO")
        if inputs.current_ratio < 1.0:
            _hit("BS002", {"CURRENT_RATIO": inputs.current_ratio}, "CURRENT_RATIO")

    if inputs.quick_ratio is not None:
        if inputs.quick_ratio > 1.5:
            _hit("BS007", {"QUICK_RATIO": inputs.quick_ratio}, "QUICK_RATIO")
        if inputs.quick_ratio < 0.8:
            _hit("BS008", {"QUICK_RATIO": inputs.quick_ratio}, "QUICK_RATIO")

    if inputs.cash_ratio is not None:
        if inputs.cash_ratio > 0.5:
            _hit("BS009", {"CASH_RATIO": inputs.cash_ratio}, "CASH_RATIO")
        if inputs.cash_ratio < 0.1:
            _hit("BS010", {"CASH_RATIO": inputs.cash_ratio}, "CASH_RATIO")

    if inputs.debt_to_ebitda is not None and inputs.debt_to_ebitda > 4.0:
        _hit("BS003", {"DEBT_TO_EBITDA": inputs.debt_to_ebitda}, "DEBT_TO_EBITDA")

    if inputs.interest_coverage is not None:
        if inputs.interest_coverage < 3.0:
            _hit("BS004", {"INTEREST_COVERAGE": inputs.interest_coverage}, "INTEREST_COVERAGE")
        if inputs.interest_coverage > 8.0:
            _hit("BS017", {"INTEREST_COVERAGE": inputs.interest_coverage}, "INTEREST_COVERAGE")
        if inputs.interest_coverage < 1.5:
            _hit("BS018", {"INTEREST_COVERAGE": inputs.interest_coverage}, "INTEREST_COVERAGE")

    if inputs.net_debt is not None and inputs.net_debt < 0:
        _hit("BS005", {"NET_DEBT": inputs.net_debt}, "NET_DEBT")

    debt_ordered = sorted(inputs.debt_by_period.items(), key=lambda item: item[0])
    if len(debt_ordered) >= 3:
        debt_values = [value for _, value in debt_ordered]
        if all(debt_values[i] > debt_values[i + 1] for i in range(len(debt_values) - 1)):
            _hit("BS006", {"DEBT_TREND": debt_values[0] - debt_values[-1]}, "DEBT_TO_EQUITY")

    if inputs.debt_to_equity is not None:
        if inputs.debt_to_equity > 2.0:
            _hit("BS011", {"DEBT_TO_EQUITY": inputs.debt_to_equity}, "DEBT_TO_EQUITY")
        if inputs.debt_to_equity < 0.5:
            _hit("BS012", {"DEBT_TO_EQUITY": inputs.debt_to_equity}, "DEBT_TO_EQUITY")

    if inputs.net_debt_to_ebitda is not None:
        if inputs.net_debt_to_ebitda > 3.0:
            _hit("BS013", {"NET_DEBT_TO_EBITDA": inputs.net_debt_to_ebitda}, "NET_DEBT_TO_EBITDA")
        if inputs.net_debt_to_ebitda < 1.0:
            _hit("BS014", {"NET_DEBT_TO_EBITDA": inputs.net_debt_to_ebitda}, "NET_DEBT_TO_EBITDA")

    if inputs.cash_to_debt is not None:
        if inputs.cash_to_debt > 0.5:
            _hit("BS015", {"CASH_TO_DEBT": inputs.cash_to_debt}, "CASH_TO_DEBT")
        if inputs.cash_to_debt < 0.1:
            _hit("BS016", {"CASH_TO_DEBT": inputs.cash_to_debt}, "CASH_TO_DEBT")

    if inputs.material_debt and not inputs.interest_expense_available:
        _hit("BS019", {"INTEREST_COVERAGE": None}, "INTEREST_COVERAGE")

    if inputs.working_capital is not None and inputs.working_capital < 0:
        _hit("BS020", {"WORKING_CAPITAL": inputs.working_capital}, "WORKING_CAPITAL")

    wc_ordered = sorted(inputs.working_capital_by_period.items(), key=lambda item: item[0])
    if len(wc_ordered) >= 3:
        wc_values = [value for _, value in wc_ordered]
        if all(wc_values[i] < wc_values[i + 1] for i in range(len(wc_values) - 1)):
            _hit("BS021", {"WORKING_CAPITAL_TREND": wc_values[-1] - wc_values[0]}, "WORKING_CAPITAL")

    if inputs.working_capital_trend is not None and inputs.working_capital_trend < 0:
        _hit("BS022", {"WORKING_CAPITAL_TREND": inputs.working_capital_trend}, "WORKING_CAPITAL")

    if inputs.debt_cagr is not None and inputs.debt_cagr > 0.10:
        _hit("BS023", {"DEBT_CAGR": inputs.debt_cagr}, "DEBT_TO_EQUITY")

    if inputs.liquidity_trend is not None:
        if inputs.liquidity_trend > 0:
            _hit("BS024", {"LIQUIDITY_TREND": inputs.liquidity_trend}, "CURRENT_RATIO")
        if inputs.liquidity_trend < 0:
            _hit("BS025", {"LIQUIDITY_TREND": inputs.liquidity_trend}, "CURRENT_RATIO")

    if inputs.leverage_trend is not None:
        if inputs.leverage_trend < 0:
            _hit("BS026", {"LEVERAGE_TREND": inputs.leverage_trend}, "DEBT_TO_EQUITY")
        if inputs.leverage_trend > 0:
            _hit("BS027", {"LEVERAGE_TREND": inputs.leverage_trend}, "DEBT_TO_EQUITY")

    if (
        inputs.current_assets_cagr is not None
        and inputs.current_liabilities_cagr is not None
        and inputs.current_liabilities_cagr - inputs.current_assets_cagr > 0.05
    ):
        _hit(
            "BS028",
            {
                "CURRENT_ASSETS_CAGR": inputs.current_assets_cagr,
                "CURRENT_LIABILITIES_CAGR": inputs.current_liabilities_cagr,
            },
            "CURRENT_RATIO",
        )

    if (
        inputs.current_ratio is not None
        and inputs.current_ratio > 1.5
        and inputs.debt_to_ebitda is not None
        and inputs.debt_to_ebitda < 2.5
        and inputs.interest_coverage is not None
        and inputs.interest_coverage > 5.0
    ):
        _hit("BS029", {"CURRENT_RATIO": inputs.current_ratio}, "CURRENT_RATIO")

    if inputs.off_balance_sheet_flag:
        hits.append(
            RuleHit(
                rule=_rule(
                    "BS031",
                    "WARNING",
                    "Off-Balance-Sheet Obligations Flagged",
                    "Analyst metadata flags material off-balance-sheet obligations.",
                    "Investigate off-balance-sheet obligations and guarantees.",
                ),
                trigger_metrics={"OFF_BALANCE_SHEET": 1.0},
                periods=periods[-3:] if periods else [],
                evidence=_ev("OFF_BALANCE_SHEET", 1.0),
            )
        )

    return hits
