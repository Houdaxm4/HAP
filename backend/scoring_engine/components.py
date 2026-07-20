"""Deterministic 0–100 component score mappers for the scoring engine.

Mappings are piecewise-linear and aligned with RULE_LIBRARY profitability
thresholds (e.g. ROIC 10%/15%/20%, ROE 20%). No LLM judgment.
"""

from __future__ import annotations

from analysis_engine.utils import mean


def _clamp(score: float) -> float:
    return max(0.0, min(100.0, round(score, 2)))


def _piecewise(value: float, points: list[tuple[float, float]]) -> float:
    """Linear interpolate ``value`` across (raw, score) anchor points."""
    ordered = sorted(points, key=lambda item: item[0])
    if value <= ordered[0][0]:
        return _clamp(ordered[0][1])
    if value >= ordered[-1][0]:
        return _clamp(ordered[-1][1])
    for (x0, y0), (x1, y1) in zip(ordered, ordered[1:]):
        if x0 <= value <= x1:
            if x1 == x0:
                return _clamp(y1)
            t = (value - x0) / (x1 - x0)
            return _clamp(y0 + t * (y1 - y0))
    return _clamp(ordered[-1][1])


def score_roic(roic: float, wacc: float | None = None) -> float:
    """Map ROIC to 0–100 using PR001–PR004 thresholds."""
    base = _piecewise(
        roic,
        [
            (0.00, 25.0),
            (0.05, 40.0),
            (0.10, 70.0),
            (0.15, 85.0),
            (0.20, 95.0),
            (0.30, 100.0),
        ],
    )
    if wacc is not None and roic < wacc:
        # PR004: economic value destruction — cap below average band.
        return _clamp(min(base, 39.0))
    return base


def score_operating_margin(margin: float) -> float:
    return _piecewise(
        margin,
        [
            (-0.05, 10.0),
            (0.00, 35.0),
            (0.08, 60.0),
            (0.15, 75.0),
            (0.25, 90.0),
            (0.40, 100.0),
        ],
    )


def score_net_margin(margin: float) -> float:
    return _piecewise(
        margin,
        [
            (-0.05, 10.0),
            (0.00, 35.0),
            (0.05, 60.0),
            (0.10, 75.0),
            (0.20, 90.0),
            (0.30, 100.0),
        ],
    )


def score_roe(roe: float) -> float:
    """Aligned with PR009 (ROE > 20% excellent)."""
    return _piecewise(
        roe,
        [
            (0.00, 25.0),
            (0.08, 50.0),
            (0.12, 65.0),
            (0.15, 75.0),
            (0.20, 90.0),
            (0.30, 100.0),
        ],
    )


def score_roa(roa: float) -> float:
    return _piecewise(
        roa,
        [
            (0.00, 25.0),
            (0.03, 50.0),
            (0.05, 65.0),
            (0.08, 80.0),
            (0.12, 90.0),
            (0.20, 100.0),
        ],
    )


def score_margin_stability(stability: float) -> float:
    """``stability`` is already a 0–1 series stability score."""
    return _clamp(stability * 100.0)


def score_revenue_cagr(cagr: float) -> float:
    """Map revenue CAGR to 0–100 per GROWTH_MODULE_SPEC.md §6.3."""
    return _piecewise(
        cagr,
        [
            (-0.10, 5.0),
            (-0.05, 20.0),
            (0.00, 40.0),
            (0.03, 50.0),
            (0.08, 70.0),
            (0.15, 90.0),
            (0.25, 98.0),
        ],
    )


def score_eps_cagr(cagr: float) -> float:
    """Map EPS CAGR to 0–100 per GROWTH_MODULE_SPEC.md §6.3."""
    return _piecewise(
        cagr,
        [
            (-0.15, 5.0),
            (-0.05, 25.0),
            (0.00, 45.0),
            (0.08, 70.0),
            (0.15, 85.0),
            (0.20, 92.0),
            (0.30, 98.0),
        ],
    )


def score_fcf_cagr(
    cagr: float,
    *,
    latest_fcf: float | None = None,
    revenue_cagr: float | None = None,
) -> float:
    """Map FCF CAGR to 0–100 with cash-consuming expansion cap."""
    base = _piecewise(
        cagr,
        [
            (-0.15, 5.0),
            (-0.05, 25.0),
            (0.00, 45.0),
            (0.08, 70.0),
            (0.15, 90.0),
            (0.25, 98.0),
        ],
    )
    if (
        latest_fcf is not None
        and latest_fcf < 0
        and revenue_cagr is not None
        and revenue_cagr > 0
    ):
        return _clamp(min(base, 35.0))
    return base


def score_growth_stability(stability: float) -> float:
    """Map 0–1 growth stability to 0–100."""
    return _clamp(stability * 100.0)


def score_organic_growth(
    organic_cagr: float,
    *,
    inorganic_rev_share: float | None = None,
) -> float:
    """Map organic revenue CAGR with optional inorganic penalty."""
    base = score_revenue_cagr(organic_cagr)
    if inorganic_rev_share is None:
        return base
    penalty = min(40.0, max(0.0, inorganic_rev_share) * 100.0)
    return _clamp(base - penalty)


def score_fcf_margin(fcf_margin: float, *, latest_fcf: float | None = None) -> float:
    """Map FCF margin to 0–100 for the Cash Flow Score FREE_CASH_FLOW component."""
    base = _piecewise(
        fcf_margin,
        [
            (-0.10, 5.0),
            (-0.02, 20.0),
            (0.00, 35.0),
            (0.05, 55.0),
            (0.10, 70.0),
            (0.15, 85.0),
            (0.25, 95.0),
            (0.35, 100.0),
        ],
    )
    if latest_fcf is not None and latest_fcf < 0:
        return _clamp(min(base, 30.0))
    return base


def score_cash_conversion(conversion: float) -> float:
    """Map cash conversion (OCF / net income) to 0–100 — CF002/CF003 thresholds."""
    return _piecewise(
        conversion,
        [
            (0.00, 10.0),
            (0.50, 40.0),
            (0.70, 55.0),
            (0.85, 70.0),
            (1.00, 85.0),
            (1.20, 95.0),
            (1.50, 100.0),
        ],
    )


def score_owner_earnings_margin(oe_margin: float) -> float:
    """Map owner earnings margin (owner earnings / revenue) to 0–100."""
    return _piecewise(
        oe_margin,
        [
            (-0.05, 10.0),
            (0.00, 35.0),
            (0.05, 55.0),
            (0.10, 70.0),
            (0.15, 85.0),
            (0.25, 95.0),
            (0.35, 100.0),
        ],
    )


def score_fcf_stability(stability: float) -> float:
    """Map 0–1 FCF stability to 0–100."""
    return _clamp(stability * 100.0)


def score_debt_leverage(debt_to_ebitda: float) -> float:
    """Lower gross/net debt to EBITDA is better (BS003 threshold at 4.0)."""
    return _piecewise(
        debt_to_ebitda,
        [
            (0.0, 100.0),
            (1.0, 90.0),
            (2.0, 75.0),
            (3.0, 60.0),
            (4.0, 40.0),
            (6.0, 20.0),
            (8.0, 10.0),
        ],
    )


def score_liquidity(current_ratio: float) -> float:
    """Map current ratio to 0–100 (BS001/BS002 thresholds)."""
    return _piecewise(
        current_ratio,
        [
            (0.0, 5.0),
            (0.5, 25.0),
            (1.0, 50.0),
            (1.5, 70.0),
            (2.0, 85.0),
            (3.0, 95.0),
            (4.0, 100.0),
        ],
    )


def score_interest_coverage(coverage: float) -> float:
    """Map interest coverage to 0–100 (BS004 threshold at 3.0)."""
    return _piecewise(
        coverage,
        [
            (0.0, 5.0),
            (1.0, 20.0),
            (1.5, 30.0),
            (3.0, 55.0),
            (5.0, 75.0),
            (8.0, 90.0),
            (12.0, 100.0),
        ],
    )


def score_net_cash_position(
    net_debt: float,
    *,
    ebitda: float | None = None,
) -> float:
    """Net cash (negative net debt) scores highest; levered net debt uses inverse scale."""
    if net_debt <= 0:
        return 95.0
    if ebitda is not None and ebitda > 0:
        return score_debt_leverage(net_debt / ebitda)
    return _piecewise(
        net_debt,
        [
            (0.0, 90.0),
            (1_000_000_000.0, 70.0),
            (5_000_000_000.0, 50.0),
            (20_000_000_000.0, 30.0),
            (50_000_000_000.0, 15.0),
        ],
    )


def score_working_capital_trend(trend_score: float) -> float:
    """Map encoded WC trend (-1 down, 0 flat, 1 up) to 0–100."""
    return _piecewise(
        trend_score,
        [
            (-1.0, 30.0),
            (0.0, 55.0),
            (1.0, 85.0),
        ],
    )


def score_roic_trend(roic_change: float) -> float:
    """Map multi-year ROIC change to 0–100 (capital allocation reinvestment quality)."""
    return _piecewise(
        roic_change,
        [
            (-0.10, 15.0),
            (-0.05, 30.0),
            (-0.02, 45.0),
            (0.00, 55.0),
            (0.03, 75.0),
            (0.05, 88.0),
            (0.10, 98.0),
        ],
    )


def score_share_buybacks(
    share_count_cagr: float | None = None,
    buyback_to_fcf: float | None = None,
) -> float | None:
    """Score buyback discipline from dilution trend and FCF funding."""
    scores: list[float] = []
    if share_count_cagr is not None:
        scores.append(
            _piecewise(
                share_count_cagr,
                [
                    (-0.08, 95.0),
                    (-0.03, 85.0),
                    (0.00, 60.0),
                    (0.03, 40.0),
                    (0.08, 20.0),
                ],
            )
        )
    if buyback_to_fcf is not None:
        scores.append(
            _piecewise(
                buyback_to_fcf,
                [
                    (0.00, 45.0),
                    (0.10, 65.0),
                    (0.25, 80.0),
                    (0.40, 90.0),
                    (0.60, 75.0),
                    (0.80, 50.0),
                ],
            )
        )
    if not scores:
        return None
    return _clamp(sum(scores) / len(scores))


def score_dividend_policy(
    payout_to_fcf: float | None = None,
    dividend_cagr: float | None = None,
) -> float | None:
    """Sustainable dividends: FCF-backed payout with moderate growth."""
    scores: list[float] = []
    if payout_to_fcf is not None:
        scores.append(
            _piecewise(
                payout_to_fcf,
                [
                    (0.00, 55.0),
                    (0.30, 75.0),
                    (0.50, 85.0),
                    (0.70, 65.0),
                    (1.00, 40.0),
                    (1.20, 20.0),
                ],
            )
        )
    if dividend_cagr is not None:
        scores.append(
            _piecewise(
                dividend_cagr,
                [
                    (-0.10, 25.0),
                    (0.00, 55.0),
                    (0.05, 70.0),
                    (0.10, 85.0),
                    (0.20, 90.0),
                ],
            )
        )
    if not scores:
        return None
    return _clamp(sum(scores) / len(scores))


def score_reinvestment_quality(
    reinvestment_rate: float,
    *,
    roic: float | None = None,
    wacc: float | None = None,
) -> float:
    """Reinvestment is valuable when returns on capital exceed cost of capital."""
    base = _piecewise(
        reinvestment_rate,
        [
            (0.00, 50.0),
            (0.20, 60.0),
            (0.40, 70.0),
            (0.60, 75.0),
            (0.90, 65.0),
        ],
    )
    if roic is None:
        return base
    spread = roic - (wacc if wacc is not None else 0.08)
    spread_adj = _piecewise(
        spread,
        [
            (-0.05, -25.0),
            (0.00, -10.0),
            (0.03, 5.0),
            (0.08, 15.0),
            (0.15, 25.0),
        ],
    )
    return _clamp(base + spread_adj)


def score_acquisition_quality(
    *,
    inorganic_share: float | None = None,
    roic_change: float | None = None,
    acquisition_intensity: float | None = None,
) -> float | None:
    """Penalize acquisition-heavy growth that coincides with deteriorating ROIC."""
    if inorganic_share is None and acquisition_intensity is None and roic_change is None:
        return None
    base = 70.0
    if inorganic_share is not None:
        base -= min(35.0, max(0.0, inorganic_share) * 50.0)
    if acquisition_intensity is not None:
        base -= min(20.0, max(0.0, acquisition_intensity - 0.15) * 80.0)
    if roic_change is not None and roic_change < 0:
        base -= min(30.0, abs(roic_change) * 200.0)
    if roic_change is not None and roic_change > 0.02:
        base += min(15.0, roic_change * 100.0)
    return _clamp(base)


def score_industry_trends(
    industry_growth_rate: float | None = None,
    industry_growth_trend: float | None = None,
) -> float | None:
    """Forward industry demand — conservative neutral center near 55."""
    scores: list[float] = []
    if industry_growth_rate is not None:
        scores.append(
            _piecewise(
                industry_growth_rate,
                [
                    (-0.05, 20.0),
                    (0.00, 45.0),
                    (0.02, 55.0),
                    (0.05, 70.0),
                    (0.08, 80.0),
                    (0.12, 88.0),
                ],
            )
        )
    if industry_growth_trend is not None:
        scores.append(
            _piecewise(
                industry_growth_trend,
                [
                    (-0.50, 25.0),
                    (-0.20, 40.0),
                    (0.00, 55.0),
                    (0.20, 68.0),
                    (0.50, 80.0),
                ],
            )
        )
    return _clamp(mean(scores)) if scores else None


def score_competitive_position(
    *,
    moat_score: float | None = None,
    market_share_trend: float | None = None,
    advantage_trend: float | None = None,
    pricing_power_score: float | None = None,
) -> float | None:
    scores: list[float] = []
    if moat_score is not None:
        scores.append(_piecewise(moat_score, [(0.2, 25.0), (0.5, 55.0), (0.7, 72.0), (0.85, 85.0)]))
    if market_share_trend is not None:
        scores.append(
            _piecewise(
                market_share_trend,
                [(-0.30, 30.0), (0.00, 55.0), (0.15, 70.0), (0.30, 82.0)],
            )
        )
    if advantage_trend is not None:
        scores.append(
            _piecewise(
                advantage_trend,
                [(-0.20, 35.0), (0.00, 55.0), (0.10, 68.0), (0.25, 80.0)],
            )
        )
    if pricing_power_score is not None:
        scores.append(
            _piecewise(
                pricing_power_score,
                [(0.2, 30.0), (0.5, 55.0), (0.7, 72.0), (0.9, 85.0)],
            )
        )
    return _clamp(mean(scores)) if scores else None


def score_management_guidance(
    *,
    revenue_guidance_trend: float | None = None,
    margin_guidance_trend: float | None = None,
    guidance_accuracy_score: float | None = None,
) -> float | None:
    scores: list[float] = []
    if revenue_guidance_trend is not None:
        scores.append(
            _piecewise(
                revenue_guidance_trend,
                [(-1.0, 25.0), (-0.50, 40.0), (0.00, 55.0), (0.50, 70.0), (1.0, 82.0)],
            )
        )
    if margin_guidance_trend is not None:
        scores.append(
            _piecewise(
                margin_guidance_trend,
                [(-1.0, 30.0), (0.00, 55.0), (0.50, 70.0), (1.0, 80.0)],
            )
        )
    if guidance_accuracy_score is not None:
        scores.append(
            _piecewise(
                guidance_accuracy_score,
                [(0.3, 30.0), (0.5, 50.0), (0.7, 65.0), (0.85, 78.0), (0.95, 85.0)],
            )
        )
    return _clamp(mean(scores)) if scores else None


def score_market_opportunities(
    *,
    product_pipeline_strength: float | None = None,
    geographic_expansion_potential: float | None = None,
    margin_expansion_potential: float | None = None,
    structural_growth_catalyst: float | None = None,
) -> float | None:
    scores: list[float] = []
    if product_pipeline_strength is not None:
        scores.append(
            _piecewise(
                product_pipeline_strength,
                [(0.2, 35.0), (0.5, 55.0), (0.7, 72.0), (0.9, 84.0)],
            )
        )
    if geographic_expansion_potential is not None:
        scores.append(
            _piecewise(
                geographic_expansion_potential,
                [(0.1, 40.0), (0.4, 58.0), (0.6, 72.0), (0.8, 82.0)],
            )
        )
    if margin_expansion_potential is not None:
        scores.append(
            _piecewise(
                margin_expansion_potential,
                [(0.0, 50.0), (0.10, 60.0), (0.25, 72.0), (0.40, 80.0)],
            )
        )
    if structural_growth_catalyst is not None:
        scores.append(
            _piecewise(
                structural_growth_catalyst,
                [(0.0, 45.0), (0.4, 60.0), (0.7, 75.0), (0.9, 85.0)],
            )
        )
    return _clamp(mean(scores)) if scores else None


def score_structural_risk(
    *,
    regulatory_exposure: float | None = None,
    technological_disruption_risk: float | None = None,
    customer_concentration: float | None = None,
    supplier_concentration: float | None = None,
    cyclicality_exposure: float | None = None,
    structural_decline_risk: float | None = None,
    regulatory_trend: float | None = None,
) -> float | None:
    """Higher score = lower structural risk (conservative)."""
    risk_signals: list[float] = []
    if regulatory_exposure is not None:
        risk_signals.append(regulatory_exposure)
    if technological_disruption_risk is not None:
        risk_signals.append(technological_disruption_risk)
    if customer_concentration is not None:
        risk_signals.append(min(1.0, customer_concentration * 1.5))
    if supplier_concentration is not None:
        risk_signals.append(min(1.0, supplier_concentration * 1.2))
    if cyclicality_exposure is not None:
        risk_signals.append(cyclicality_exposure * 0.85)
    if structural_decline_risk is not None:
        risk_signals.append(structural_decline_risk)
    if not risk_signals:
        return None
    risk_index = mean(risk_signals) or 0.0
    if regulatory_trend is not None and regulatory_trend < 0:
        risk_index += min(0.15, abs(regulatory_trend) * 0.25)
    risk_index = min(1.0, risk_index)
    return _clamp(100.0 - risk_index * 70.0)


def score_margin_of_safety(margin_of_safety: float) -> float:
    return _piecewise(
        margin_of_safety,
        [
            (-0.30, 10.0),
            (-0.15, 25.0),
            (0.00, 45.0),
            (0.10, 60.0),
            (0.20, 75.0),
            (0.30, 85.0),
            (0.50, 95.0),
        ],
    )


def score_dcf_reasonableness(
    *,
    terminal_share: float | None = None,
    terminal_growth: float | None = None,
    gdp_growth: float | None = None,
    wacc: float | None = None,
    forecast_years: int | None = None,
    reverse_dcf_unrealistic: bool = False,
) -> float | None:
    if wacc is None and terminal_share is None and terminal_growth is None:
        return None
    score = 70.0
    if terminal_share is not None and terminal_share > 0.75:
        score -= 20.0
    if terminal_growth is not None and gdp_growth is not None and terminal_growth > gdp_growth:
        score -= 15.0
    if wacc is not None and (wacc < 0.06 or wacc > 0.14):
        score -= 15.0
    if forecast_years is not None and forecast_years < 5:
        score -= 5.0
    if reverse_dcf_unrealistic:
        score -= 10.0
    if (
        terminal_share is not None
        and terminal_share <= 0.75
        and wacc is not None
        and 0.06 <= wacc <= 0.14
        and not reverse_dcf_unrealistic
    ):
        score += 10.0
    return _clamp(score)


def score_multiple_reasonableness(
    *,
    implied_multiple: float | None = None,
    peer_p25: float | None = None,
    peer_median: float | None = None,
    peer_p75: float | None = None,
    historical_median: float | None = None,
    margin_of_safety: float | None = None,
) -> float | None:
    if implied_multiple is None:
        return None
    if peer_p25 is not None and implied_multiple < peer_p25 * 0.85 and (margin_of_safety or 0) > 0.10:
        return 90.0
    if peer_median is not None:
        if abs(implied_multiple - peer_median) / peer_median <= 0.10:
            return 60.0
        if implied_multiple > (peer_p75 or peer_median * 1.15):
            return 32.0
    if historical_median is not None and implied_multiple < historical_median * 0.75 and (margin_of_safety or 0) > 0.10:
        return 88.0
    return 55.0


def score_method_convergence(method_spread: float | None) -> float | None:
    if method_spread is None:
        return None
    return _piecewise(
        method_spread,
        [
            (0.15, 90.0),
            (0.25, 70.0),
            (0.40, 50.0),
            (0.60, 30.0),
        ],
    )


def score_workbook_alignment(
    *,
    divergent_count: int = 0,
    comparable_count: int = 0,
    workbook_only_count: int = 0,
    all_within_tolerance: bool = False,
) -> float | None:
    if comparable_count == 0 and workbook_only_count == 0:
        return None
    if all_within_tolerance and divergent_count == 0:
        return 90.0
    if divergent_count > 0:
        return 45.0
    if workbook_only_count > 0 and comparable_count == 0:
        return 50.0
    return 65.0


def score_return_contribution(rate: float | None) -> float | None:
    """Map an annualized return contribution (ratio) to a 0–100 score."""
    if rate is None:
        return None
    return _piecewise(
        rate,
        [
            (-0.15, 10.0),
            (-0.05, 25.0),
            (0.00, 45.0),
            (0.03, 55.0),
            (0.05, 62.0),
            (0.08, 70.0),
            (0.10, 78.0),
            (0.12, 85.0),
            (0.15, 92.0),
            (0.20, 97.0),
        ],
    )


def score_valuation_reversion_contribution(reversion: float | None) -> float | None:
    if reversion is None:
        return None
    return _piecewise(
        reversion,
        [
            (-0.12, 15.0),
            (-0.06, 30.0),
            (0.00, 50.0),
            (0.04, 65.0),
            (0.08, 78.0),
            (0.12, 88.0),
            (0.18, 95.0),
        ],
    )


def score_expected_cagr_level(expected_cagr: float | None) -> float | None:
    if expected_cagr is None:
        return None
    return score_return_contribution(expected_cagr)


def score_expected_return_workbook_alignment(
    *,
    divergent_count: int = 0,
    comparable_count: int = 0,
    workbook_only_count: int = 0,
    all_within_tolerance: bool = False,
) -> float | None:
    return score_workbook_alignment(
        divergent_count=divergent_count,
        comparable_count=comparable_count,
        workbook_only_count=workbook_only_count,
        all_within_tolerance=all_within_tolerance,
    )


def weighted_module_score(
    components: dict[str, float | None],
    weights: dict[str, float],
) -> tuple[float | None, dict[str, float]]:
    """
    Compute a renormalized weighted score over available components.

    Returns (score_or_None, effective_weights_used).
    """
    available = {
        code: value
        for code, value in components.items()
        if value is not None and code in weights
    }
    if not available:
        return None, {}
    weight_sum = sum(weights[code] for code in available)
    if weight_sum <= 0:
        return None, {}
    effective = {code: weights[code] / weight_sum for code in available}
    score = sum(available[code] * effective[code] for code in available)
    return _clamp(score), effective
