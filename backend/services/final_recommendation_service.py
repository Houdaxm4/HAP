"""Final investment recommendation synthesis from completed analytical artifacts.

Does not recompute financials. Separates Business Quality (price-independent)
from Investment Attractiveness (price-dependent). BUY requires ≥25% MOS.
"""

from __future__ import annotations

from typing import Any

from analysis_engine.recommendation_engine import RecommendationEngine, _RECOMMENDATION_LABELS
from analysis_engine.schemas import (
    BusinessQualityResult,
    Evidence,
    Finding,
    InvestmentAttractivenessResult,
    RecommendationReason,
    RiskItem,
)
from models.final_recommendation import EntryCondition, FinalRecommendationReport
from models.valuation_validation import ValuationAttractiveness
from services.valuation_validation_service import HOUSE_MOS_THRESHOLD

_BQ_BANDS: tuple[tuple[float, str], ...] = (
    (90.0, "EXCEPTIONAL_BUSINESS"),
    (80.0, "EXCELLENT_BUSINESS"),
    (70.0, "HIGH_QUALITY_BUSINESS"),
    (60.0, "AVERAGE_BUSINESS"),
    (0.0, "WEAK_BUSINESS"),
)

_IA_BANDS: tuple[tuple[float, str], ...] = (
    (90.0, "EXCEPTIONAL_OPPORTUNITY"),
    (80.0, "ATTRACTIVE_OPPORTUNITY"),
    (60.0, "FAIRLY_VALUED"),
    (50.0, "OVERVALUED"),
    (0.0, "HIGHLY_OVERVALUED"),
)


def _band(score: float | None, bands: tuple[tuple[float, str], ...]) -> str | None:
    if score is None:
        return None
    for threshold, label in bands:
        if score >= threshold:
            return label
    return bands[-1][1]


def _evidence(metric: str, value: float | None, source: str, confidence: float = 0.8) -> list[Evidence]:
    return [
        Evidence(
            kind="derived_metric",
            label=metric,
            metric=metric,
            value=value,
            confidence=confidence,
            source=source,
        )
    ]


class FinalRecommendationService:
    """Synthesize final HAP recommendation from milestone artifacts."""

    def __init__(self, recommendation_engine: RecommendationEngine | None = None) -> None:
        self.recommendation_engine = recommendation_engine or RecommendationEngine()

    def synthesize(
        self,
        *,
        analysis_id: str,
        ticker: str,
        valuation: dict[str, Any] | None = None,
        roic: dict[str, Any] | None = None,
        expected_return: dict[str, Any] | None = None,
        statement_validation: dict[str, Any] | None = None,
        analyst_review: dict[str, Any] | None = None,
        engine_business_quality_score: float | None = None,
        engine_investment_attractiveness_score: float | None = None,
    ) -> FinalRecommendationReport:
        valuation = valuation or {}
        roic = roic or {}
        expected_return = expected_return or {}
        statement_validation = statement_validation or {}
        analyst_review = analyst_review or {}

        price = _f(valuation.get("current_price"))
        intrinsic = _f(valuation.get("workbook_intrinsic_value")) or _f(
            valuation.get("independent_intrinsic_value")
        )
        mos = _f(valuation.get("margin_of_safety"))
        entry = _f(valuation.get("required_entry_price"))
        val_attr = valuation.get("attractiveness")
        if hasattr(val_attr, "value"):
            val_attr = val_attr.value
        val_status = str(val_attr) if val_attr else valuation.get("decision")
        if hasattr(val_status, "value"):
            val_status = val_status.value

        er_decision = expected_return.get("expected_return_decision") or expected_return.get(
            "overall_decision"
        )
        if hasattr(er_decision, "value"):
            er_decision = er_decision.value
        er_attractiveness = expected_return.get("attractiveness")

        roic_assess = self._roic_wacc_assessment(roic)
        disc_count = int(statement_validation.get("discrepancy_count") or 0)
        material_findings = int(analyst_review.get("material_count") or 0)

        bq_score, bq_reasons_for, bq_reasons_against, bq_conf = self._business_quality(
            roic=roic,
            roic_assess=roic_assess,
            disc_count=disc_count,
            material_findings=material_findings,
            engine_score=engine_business_quality_score,
            # Explicitly ignore price for BQ
            current_price=price,
        )
        ia_score, ia_reasons_for, ia_reasons_against, ia_conf, ia_missing = self._investment_attractiveness(
            mos=mos,
            val_status=str(val_status) if val_status else None,
            price=price,
            intrinsic=intrinsic,
            er_decision=str(er_decision) if er_decision else None,
            er_attractiveness=str(er_attractiveness) if er_attractiveness else None,
            engine_score=engine_investment_attractiveness_score,
        )

        bq_result = BusinessQualityResult(
            score=bq_score,
            confidence=bq_conf,
            classification=_band(bq_score, _BQ_BANDS) or "WEAK_BUSINESS",
            classification_label=_band(bq_score, _BQ_BANDS) or "WEAK_BUSINESS",
            strengths=[
                Finding(
                    finding_id=f"bq:for:{i}",
                    code="BQ_STRENGTH",
                    severity="positive",
                    category="business_quality",
                    summary=s,
                    evidence=_evidence("business_quality", bq_score, "final_recommendation"),
                    confidence=bq_conf,
                )
                for i, s in enumerate(bq_reasons_for)
            ],
            weaknesses=[
                RiskItem(
                    risk_id=f"bq:against:{i}",
                    code="BQ_WEAKNESS",
                    severity="warning",
                    summary=s,
                    evidence=_evidence("business_quality", bq_score, "final_recommendation"),
                    confidence=bq_conf,
                )
                for i, s in enumerate(bq_reasons_against)
            ],
        )
        ia_result = InvestmentAttractivenessResult(
            score=ia_score,
            confidence=ia_conf,
            classification=_band(ia_score, _IA_BANDS) or "HIGHLY_OVERVALUED",
            classification_label=_band(ia_score, _IA_BANDS) or "HIGHLY_OVERVALUED",
            strengths=[
                Finding(
                    finding_id=f"ia:for:{i}",
                    code="IA_STRENGTH",
                    severity="positive",
                    category="investment_attractiveness",
                    summary=s,
                    evidence=_evidence("investment_attractiveness", ia_score, "final_recommendation"),
                    confidence=ia_conf,
                )
                for i, s in enumerate(ia_reasons_for)
            ],
            weaknesses=[
                RiskItem(
                    risk_id=f"ia:against:{i}",
                    code="IA_WEAKNESS",
                    severity="warning",
                    summary=s,
                    evidence=_evidence("investment_attractiveness", ia_score, "final_recommendation"),
                    confidence=ia_conf,
                )
                for i, s in enumerate(ia_reasons_against)
            ],
        )

        if ia_missing or bq_score is None or ia_score is None:
            code = "INSUFFICIENT_DATA"
            label = _RECOMMENDATION_LABELS[code]
            conf = min(bq_conf, ia_conf) * 0.5
            eng_reasons: list[RecommendationReason] = []
        else:
            eng = self.recommendation_engine.recommend(bq_result, ia_result)
            code = eng.recommendation
            label = eng.recommendation_label
            conf = eng.confidence
            eng_reasons = list(eng.reasons)
            code, label = self._apply_mos_buy_gate(
                code=code,
                label=label,
                bq_score=bq_score,
                mos=mos,
                price=price,
                intrinsic=intrinsic,
            )
            code, label = self._apply_expensive_quality_wait(
                code=code,
                label=label,
                bq_score=bq_score,
                mos=mos,
                val_status=str(val_status) if val_status else None,
            )

        reasons_for = list(dict.fromkeys(bq_reasons_for + ia_reasons_for))
        reasons_against = list(dict.fromkeys(bq_reasons_against + ia_reasons_against))
        key_risks = self._key_risks(
            mos=mos,
            disc_count=disc_count,
            material_findings=material_findings,
            roic_assess=roic_assess,
            val_status=str(val_status) if val_status else None,
        )

        # Confidence penalties for unresolved data issues
        if disc_count > 0:
            conf = max(0.2, conf - min(0.25, 0.03 * disc_count))
        if material_findings > 0:
            conf = max(0.2, conf - min(0.15, 0.04 * material_findings))
        if price is None or intrinsic is None:
            conf = min(conf, 0.45)

        entry_condition = None
        if code in {"WAIT_FOR_BETTER_PRICE", "HOLD", "WATCH"} and intrinsic is not None:
            pct = None
            if price is not None and entry is not None and price > 0:
                pct = (price - entry) / price
            entry_condition = EntryCondition(
                current_price=price,
                intrinsic_value=intrinsic,
                required_entry_price=entry,
                margin_of_safety=mos,
                required_mos_threshold=HOUSE_MOS_THRESHOLD,
                pct_decline_to_entry=pct,
                note=(
                    f"Wait for price ≤ entry ${entry:.2f} to achieve ≥{HOUSE_MOS_THRESHOLD:.0%} MOS"
                    if entry is not None
                    else "Entry price unavailable"
                ),
            )

        rationale = self._rationale(
            code=code,
            bq_score=bq_score,
            ia_score=ia_score,
            mos=mos,
            roic_assess=roic_assess,
            val_status=str(val_status) if val_status else None,
        )

        refs = [
            r
            for r in [
                "roic_validation_report.json",
                "expected_return_validation_report.json",
                "valuation_validation_report.json",
                "statement_validation_report.json",
                "analyst_review_report.json",
            ]
            if True
        ]
        if eng_reasons:
            refs.append("analysis_engine.recommendation_engine")

        return FinalRecommendationReport(
            analysis_id=analysis_id,
            ticker=ticker,
            business_quality_score=bq_score,
            business_quality_classification=_band(bq_score, _BQ_BANDS),
            investment_attractiveness_score=ia_score,
            investment_attractiveness_classification=_band(ia_score, _IA_BANDS),
            valuation_status=str(val_status) if val_status else None,
            expected_return_status=str(er_decision) if er_decision else None,
            roic_wacc_assessment=roic_assess,
            current_price=price,
            intrinsic_value=intrinsic,
            margin_of_safety=mos,
            entry_price=entry,
            reasons_for=reasons_for,
            reasons_against=reasons_against,
            key_risks=key_risks,
            entry_condition=entry_condition,
            confidence=round(conf, 3),
            final_recommendation=code,
            recommendation_label=label,
            recommendation_rationale=rationale,
            evidence_references=refs,
            evidence={
                "mos_threshold": HOUSE_MOS_THRESHOLD,
                "discrepancy_count": disc_count,
                "material_analyst_findings": material_findings,
                "engine_reason_codes": [r.code for r in eng_reasons],
                "price_excluded_from_business_quality": True,
            },
            summary=(
                f"{ticker}: BQ={bq_score} ({_band(bq_score, _BQ_BANDS)}), "
                f"IA={ia_score} ({_band(ia_score, _IA_BANDS)}), "
                f"recommendation={code}, confidence={conf:.2f}."
            ),
        )

    # ------------------------------------------------------------------

    def _roic_wacc_assessment(self, roic: dict[str, Any]) -> str:
        hist = roic.get("historical_spread_interpretation") or ""
        periods = roic.get("periods") or []
        spreads = [
            p.get("roic_minus_wacc")
            for p in periods
            if isinstance(p, dict) and p.get("roic_minus_wacc") is not None
        ]
        if spreads:
            positive = sum(1 for s in spreads if s > 0.02)
            negative = sum(1 for s in spreads if s < -0.02)
            if positive == len(spreads):
                return "consistently_positive_value_creation"
            if negative == len(spreads):
                return "consistently_negative_value_destruction"
            if negative > positive:
                return "mostly_negative_spread"
            return "mixed_spread"
        if "value creation" in hist.lower() or "positive" in hist.lower():
            return "consistently_positive_value_creation"
        if "value destruction" in hist.lower() or "negative" in hist.lower():
            return "consistently_negative_value_destruction"
        if hist:
            return "review_required"
        return "insufficient_roic_evidence"

    def _business_quality(
        self,
        *,
        roic: dict[str, Any],
        roic_assess: str,
        disc_count: int,
        material_findings: int,
        engine_score: float | None,
        current_price: float | None,
    ) -> tuple[float, list[str], list[str], float]:
        # current_price intentionally unused for scoring (kept for API clarity / tests)
        _ = current_price
        reasons_for: list[str] = []
        reasons_against: list[str] = []

        if engine_score is not None:
            score = float(engine_score)
            reasons_for.append(
                f"Analysis-engine Business Quality score {score:.1f} used as foundation "
                "(price not included in BQ)."
            )
            conf = 0.85
        else:
            # Artifact-only path
            if roic_assess == "consistently_positive_value_creation":
                score = 90.0
                reasons_for.append(
                    "ROIC exceeded WACC consistently over the reviewed period, "
                    "indicating sustained economic value creation."
                )
                conf = 0.82
            elif roic_assess == "mixed_spread":
                score = 72.0
                reasons_for.append("ROIC−WACC was positive in some years but mixed historically.")
                conf = 0.7
            elif roic_assess == "mostly_negative_spread":
                score = 55.0
                reasons_against.append(
                    "ROIC−WACC was mostly negative, weighing against business-quality strength."
                )
                conf = 0.7
            elif roic_assess == "consistently_negative_value_destruction":
                score = 45.0
                reasons_against.append(
                    "ROIC was below WACC across the reviewed history (economic value destruction)."
                )
                conf = 0.75
            else:
                score = 65.0
                reasons_against.append(
                    "Insufficient ROIC/WACC evidence for a high-confidence business-quality score."
                )
                conf = 0.55

            overall = roic.get("overall_decision")
            if hasattr(overall, "value"):
                overall = overall.value
            if overall == "MATERIAL_REVIEW":
                reasons_against.append(
                    "ROIC review flagged MATERIAL_REVIEW items (e.g., tax/classification judgment)."
                )
                conf = min(conf, 0.75)
                # Do not demote exceptional ROIC economics solely for review flags;
                # confidence already reduced.


        if disc_count >= 5:
            reasons_against.append(
                f"{disc_count} statement-validation discrepancies remain unresolved — "
                "confidence reduced (BQ not lowered solely for price)."
            )
            conf = max(0.35, conf - 0.1)
        if material_findings >= 3:
            reasons_against.append(
                f"{material_findings} material analyst-review findings require ongoing monitoring."
            )
            conf = max(0.35, conf - 0.05)

        if score >= 80 and not any("ROIC exceeded WACC" in r for r in reasons_for):
            if roic_assess == "consistently_positive_value_creation":
                reasons_for.append(
                    "ROIC exceeded WACC consistently over the reviewed period, "
                    "indicating sustained economic value creation."
                )

        return score, reasons_for, reasons_against, conf

    def _investment_attractiveness(
        self,
        *,
        mos: float | None,
        val_status: str | None,
        price: float | None,
        intrinsic: float | None,
        er_decision: str | None,
        er_attractiveness: str | None,
        engine_score: float | None,
    ) -> tuple[float | None, list[str], list[str], float, bool]:
        reasons_for: list[str] = []
        reasons_against: list[str] = []

        if price is None or price <= 0 or intrinsic is None:
            reasons_against.append(
                "Current price or intrinsic value missing — investment attractiveness indeterminate."
            )
            return None, reasons_for, reasons_against, 0.4, True

        # Primary: house valuation attractiveness / MOS
        status = (val_status or "").upper()
        if status == ValuationAttractiveness.ATTRACTIVE.value or (
            mos is not None and mos >= HOUSE_MOS_THRESHOLD
        ):
            score = 88.0 if (mos or 0) >= 0.35 else 82.0
            reasons_for.append(
                f"Current margin of safety is {mos:.1%} vs house threshold "
                f"{HOUSE_MOS_THRESHOLD:.0%} — valuation entry criteria satisfied."
            )
            conf = 0.85
        elif status == ValuationAttractiveness.NEAR_ENTRY.value or (
            mos is not None and mos >= HOUSE_MOS_THRESHOLD - 0.05
        ):
            score = 62.0
            reasons_against.append(
                f"Margin of safety {None if mos is None else f'{mos:.1%}'} is near but below "
                f"the {HOUSE_MOS_THRESHOLD:.0%} buy threshold."
            )
            conf = 0.8
        elif status == ValuationAttractiveness.WAIT.value or (
            mos is not None and 0 <= mos < HOUSE_MOS_THRESHOLD - 0.05
        ):
            # Keep IA ≥50 so high-BQ names become WAIT/WATCH, not AVOID-only on price.
            score = 52.0
            reasons_against.append(
                f"Price is below intrinsic but MOS "
                f"{None if mos is None else f'{mos:.1%}'} fails the {HOUSE_MOS_THRESHOLD:.0%} house rule "
                "(undervalued ≠ buyable)."
            )
            conf = 0.8
        elif status == ValuationAttractiveness.EXPENSIVE.value or (mos is not None and mos < 0):
            # Score in OVERVALUED band (≥50): quality names → WAIT_FOR_BETTER_PRICE, not AVOID.
            score = 52.0
            reasons_against.append(
                f"Current price ${price:.2f} is above Graham intrinsic ${intrinsic:.2f} "
                f"(MOS {mos:.1%}) — valuation classified EXPENSIVE."
            )
            conf = 0.85
        else:
            score = 50.0
            reasons_against.append("Valuation status incomplete; attractiveness capped.")
            conf = 0.55

        if er_decision == "SOURCE_MISSING":
            reasons_against.append(
                "Expected-return output incomplete (e.g., missing price inputs historically) — "
                "does not improve attractiveness."
            )
            conf = min(conf, 0.75)
        elif er_attractiveness in {"attractive", "acceptable"}:
            reasons_for.append(
                f"Expected-return review attractiveness={er_attractiveness} supports opportunity quality."
            )
            score = min(100.0, score + 3.0)

        # Optional blend with engine IA without letting it override MOS gate via inflation
        if engine_score is not None:
            blended = 0.5 * score + 0.5 * float(engine_score)
            if mos is not None and mos < 0:
                score = min(max(blended, 50.0), 55.0)
            elif mos is not None and mos < HOUSE_MOS_THRESHOLD:
                score = min(blended, 65.0)
            else:
                score = blended
            reasons_for.append(
                f"Analysis-engine Investment Attractiveness {engine_score:.1f} blended with "
                "artifact valuation (MOS remains binding)."
            )

        return score, reasons_for, reasons_against, conf, False

    def _apply_mos_buy_gate(
        self,
        *,
        code: str,
        label: str,
        bq_score: float,
        mos: float | None,
        price: float | None,
        intrinsic: float | None,
    ) -> tuple[str, str]:
        _ = price, intrinsic
        if code not in {"BUY", "STRONG_BUY"}:
            return code, label
        if mos is not None and mos >= HOUSE_MOS_THRESHOLD:
            return code, label
        if bq_score >= 70:
            return "WAIT_FOR_BETTER_PRICE", _RECOMMENDATION_LABELS["WAIT_FOR_BETTER_PRICE"]
        return "HOLD", _RECOMMENDATION_LABELS["HOLD"]

    def _apply_expensive_quality_wait(
        self,
        *,
        code: str,
        label: str,
        bq_score: float,
        mos: float | None,
        val_status: str | None,
    ) -> tuple[str, str]:
        """High-quality + expensive/insufficient MOS → WAIT, not BUY and not vague WATCH."""
        if bq_score < 70:
            return code, label
        if code in {"BUY", "STRONG_BUY", "AVOID", "INSUFFICIENT_DATA"}:
            return code, label
        expensive = (val_status or "").upper() == "EXPENSIVE" or (mos is not None and mos < 0)
        insufficient_mos = mos is not None and mos < HOUSE_MOS_THRESHOLD
        if expensive or insufficient_mos:
            return "WAIT_FOR_BETTER_PRICE", _RECOMMENDATION_LABELS["WAIT_FOR_BETTER_PRICE"]
        return code, label

    def _key_risks(
        self,
        *,
        mos: float | None,
        disc_count: int,
        material_findings: int,
        roic_assess: str,
        val_status: str | None,
    ) -> list[str]:
        risks: list[str] = []
        if mos is not None and mos < HOUSE_MOS_THRESHOLD:
            risks.append(
                f"Insufficient margin of safety versus {HOUSE_MOS_THRESHOLD:.0%} house threshold."
            )
        if val_status == "EXPENSIVE":
            risks.append("Valuation premium to Graham intrinsic value may reverse.")
        if "negative" in roic_assess:
            risks.append("Negative ROIC−WACC history signals weak economic profitability.")
        if disc_count:
            risks.append(f"{disc_count} unresolved statement discrepancies.")
        if material_findings:
            risks.append(f"{material_findings} material analyst-review items remain open.")
        risks.append(
            "Graham IV embeds historical EPS CAGR; forward growth below history would lower intrinsic value."
        )
        return risks

    def _rationale(
        self,
        *,
        code: str,
        bq_score: float | None,
        ia_score: float | None,
        mos: float | None,
        roic_assess: str,
        val_status: str | None,
    ) -> str:
        return (
            f"Recommendation {code} synthesizes Business Quality "
            f"({bq_score}, ROIC/WACC={roic_assess}) with Investment Attractiveness "
            f"({ia_score}, valuation={val_status}, MOS={mos}). "
            f"BUY requires MOS≥{HOUSE_MOS_THRESHOLD:.0%}; price does not alter Business Quality."
        )


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
