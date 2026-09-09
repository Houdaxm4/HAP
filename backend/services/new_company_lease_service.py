"""Ten-year lease footnote extraction and long-term discount-rate estimation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.new_company import (
    LeaseRateProposal,
    LeaseRateReview,
    LeaseYearData,
    NewCompanyLeaseReport,
)
from services.annual_period_service import detect_year_columns
from services.sec_service import SecService

_COMMITMENT_TAGS = {
    "year_1": (
        "LesseeOperatingLeaseLiabilityPaymentsDueNextTwelveMonths",
        "OperatingLeasesFutureMinimumPaymentsDueCurrent",
        "FutureMinimumLeasePaymentsOperatingLeasesCurrent",
    ),
    "year_2": (
        "LesseeOperatingLeaseLiabilityPaymentsDueYearTwo",
        "OperatingLeasesFutureMinimumPaymentsDueInTwoYears",
    ),
    "year_3": (
        "LesseeOperatingLeaseLiabilityPaymentsDueYearThree",
        "OperatingLeasesFutureMinimumPaymentsDueInThreeYears",
    ),
    "year_4": (
        "LesseeOperatingLeaseLiabilityPaymentsDueYearFour",
        "OperatingLeasesFutureMinimumPaymentsDueInFourYears",
    ),
    "year_5": (
        "LesseeOperatingLeaseLiabilityPaymentsDueYearFive",
        "OperatingLeasesFutureMinimumPaymentsDueInFiveYears",
    ),
    "thereafter": (
        "LesseeOperatingLeaseLiabilityPaymentsDueAfterYearFive",
        "OperatingLeasesFutureMinimumPaymentsDueThereafter",
    ),
    "total_undiscounted": (
        "LesseeOperatingLeaseLiabilityPaymentsDue",
        "OperatingLeasesFutureMinimumPaymentsDue",
        "FutureMinimumLeasePaymentsReceivableUnderOperatingLeases",
    ),
    "current_liability": ("OperatingLeaseLiabilityCurrent",),
    "long_term_liability": ("OperatingLeaseLiabilityNoncurrent",),
    "rou_asset": ("OperatingLeaseRightOfUseAsset",),
    "lease_cost": ("OperatingLeaseCost", "LeaseCost"),
    "remaining_term": ("OperatingLeaseWeightedAverageRemainingLeaseTerm",),
    "reported_discount_rate": (
        "OperatingLeaseWeightedAverageDiscountRatePercent",
        "OperatingLeaseWeightedAverageDiscountRate",
    ),
}

_IBR_TAGS = (
    "LesseeOperatingLeaseIncrementalBorrowingRate",
    "IncrementalBorrowingRate",
)

_RATE_ROW = 18
_RISK_FREE_FALLBACK = 0.04


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def _scale(val: float) -> float:
    return val / 1_000_000.0 if abs(val) >= 10_000 else val


def _as_rate(val: float) -> float:
    return val / 100.0 if abs(val) > 1.5 else val


class NewCompanyLeaseService:
    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_years: list[str],
        company_facts: dict[str, Any] | None = None,
        wacc: float | None = None,
        after_tax_cost_of_debt: float | None = None,
        treasury_yield: float | None = None,
        credit_spread: float | None = None,
        market_date: str | None = None,
        comparable_rates: list[float] | None = None,
    ) -> NewCompanyLeaseReport:
        sec = SecService()
        years: list[LeaseYearData] = []
        warnings: list[str] = []
        written: list[str] = []
        regimes: set[str] = set()

        for fy in fiscal_years:
            rec, raw = self._year_from_facts(sec, company_facts, fy)
            rec.raw_labels = raw
            years.append(rec)
            regimes.add(rec.regime)
            if rec.total_undiscounted is None and rec.rou_asset is None and rec.year_1 is None:
                warnings.append(f"LEASE_HISTORY_INCOMPLETE: {fy}")

        mixed = "pre_asc_842" in regimes and "post_asc_842" in regimes
        if mixed:
            warnings.append(
                "Lease history spans pre-ASC 842 commitments and post-ASC 842 liabilities; "
                "undiscounted commitments are not mixed with discounted liabilities."
            )

        proposal = self.estimate_rate(
            years=years,
            wacc=wacc,
            after_tax_cost_of_debt=after_tax_cost_of_debt,
            treasury_yield=treasury_yield,
            credit_spread=credit_spread,
            market_date=market_date,
            comparable_rates=comparable_rates,
        )
        self._write_workbook(workbook_path, years, proposal.proposed_rate, written)

        latest = years[-1] if years else None
        review = LeaseRateReview(
            analysis_id=analysis_id,
            ticker=ticker,
            status="LEASE_RATE_REVIEW_PENDING",
            proposed_rate=proposal.proposed_rate,
            supporting_evidence=proposal.company_evidence,
            prior_or_comparable_rates=list(comparable_rates or []),
            calculated_lease_asset=latest.rou_asset if latest else None,
            calculated_lease_liability=(
                (latest.current_liability or 0) + (latest.long_term_liability or 0)
                if latest and (latest.current_liability is not None or latest.long_term_liability is not None)
                else None
            ),
            sensitivity=proposal.sensitivity,
            proposal=proposal,
            blocking=True,
            audit_trail=[
                {
                    "event": "LEASE_RATE_ESTIMATED",
                    "rate": proposal.proposed_rate,
                    "methodology": proposal.methodology,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            ],
            summary=(
                f"Proposed long-term lease rate {proposal.proposed_rate} via {proposal.methodology}. "
                "Analyst approval is required before COMPLETE."
            ),
        )
        complete = sum(1 for y in years if y.year_1 is not None or y.rou_asset is not None) >= max(1, len(years) // 2)
        return NewCompanyLeaseReport(
            analysis_id=analysis_id,
            ticker=ticker,
            years=years,
            complete=complete,
            mixed_regimes=mixed,
            warnings=warnings,
            proposal=proposal,
            review=review,
            cells_written=written,
            summary=(
                f"Leases: {len(years)} years; mixed_asc842={mixed}; "
                f"proposed_rate={proposal.proposed_rate}; review=pending."
            ),
        )

    def estimate_rate(
        self,
        *,
        years: list[LeaseYearData],
        wacc: float | None = None,
        after_tax_cost_of_debt: float | None = None,
        treasury_yield: float | None = None,
        credit_spread: float | None = None,
        market_date: str | None = None,
        comparable_rates: list[float] | None = None,
    ) -> LeaseRateProposal:
        attempts: list[dict[str, Any]] = []
        evidence: list[str] = []
        latest = next((y for y in reversed(years) if y.reported_discount_rate is not None), None)
        duration = next((y.remaining_term for y in reversed(years) if y.remaining_term), None)

        # 1. Company-reported weighted-average operating-lease discount rate
        if latest and latest.reported_discount_rate is not None:
            rate = _as_rate(latest.reported_discount_rate)
            attempts.append({"rank": 1, "method": "reported_weighted_average_discount_rate", "rate": rate})
            evidence.append(f"{latest.fiscal_year} reported operating-lease WtdAvg discount rate {rate:.4f}.")
            return self._proposal(rate, "reported_weighted_average_discount_rate", 1, duration, treasury_yield, credit_spread, evidence, attempts, market_date)

        # 2. Incremental borrowing rate
        ibr = next((y for y in reversed(years) if any(
            r.get("field") == "incremental_borrowing_rate" for r in y.raw_labels
        )), None)
        if ibr:
            raw = next(r for r in ibr.raw_labels if r.get("field") == "incremental_borrowing_rate")
            rate = _as_rate(float(raw["value"]))
            attempts.append({"rank": 2, "method": "incremental_borrowing_rate", "rate": rate})
            evidence.append(f"{ibr.fiscal_year} incremental borrowing rate {rate:.4f}.")
            return self._proposal(rate, "incremental_borrowing_rate", 2, duration, treasury_yield, credit_spread, evidence, attempts, market_date)

        # 3. Inferred from undiscounted payments vs reported liability
        inferred = self._infer_from_liability(years)
        attempts.append({"rank": 3, "method": "inferred_undiscounted_vs_liability", "rate": inferred})
        if inferred is not None:
            evidence.append(f"Inferred discount rate {inferred:.4f} from undiscounted commitments vs lease liability.")
            return self._proposal(inferred, "inferred_undiscounted_vs_liability", 3, duration, treasury_yield, credit_spread, evidence, attempts, market_date)

        # 4. Company debt yield / after-tax cost of debt
        if after_tax_cost_of_debt is not None:
            pretax = after_tax_cost_of_debt / 0.79 if after_tax_cost_of_debt < 0.2 else after_tax_cost_of_debt
            attempts.append({"rank": 4, "method": "debt_yield_adjusted", "rate": pretax})
            evidence.append(f"After-tax cost of debt {after_tax_cost_of_debt:.4f} grossed up for lease-term unsecured borrowing.")
            return self._proposal(float(pretax), "debt_yield_adjusted", 4, duration, treasury_yield, credit_spread, evidence, attempts, market_date)
        if wacc is not None:
            attempts.append({"rank": 4, "method": "wacc_proxy_rejected_prefer_debt", "rate": None})

        # 5. Risk-free + credit spread
        rf = treasury_yield if treasury_yield is not None else _RISK_FREE_FALLBACK
        spread = credit_spread if credit_spread is not None else 0.015
        blended = rf + spread
        attempts.append({"rank": 5, "method": "risk_free_plus_credit_spread", "rate": blended, "rf": rf, "spread": spread})
        evidence.append(f"Benchmark yield {rf:.4f} plus company credit spread {spread:.4f}.")
        # 6. Comparables last resort only if 5 is somehow unusable
        if comparable_rates and treasury_yield is None and credit_spread is None and after_tax_cost_of_debt is None:
            med = sorted(comparable_rates)[len(comparable_rates) // 2]
            attempts.append({"rank": 6, "method": "comparable_or_sector", "rate": med})
            evidence.append(f"Last-resort sector/comparable median {med:.4f}.")
            return self._proposal(med, "comparable_or_sector", 6, duration, treasury_yield, credit_spread, evidence, attempts, market_date)
        return self._proposal(blended, "risk_free_plus_credit_spread", 5, duration, rf, spread, evidence, attempts, market_date)

    def apply_review(
        self,
        review: LeaseRateReview,
        *,
        action: str,
        rate: float | None = None,
        reason: str | None = None,
        workbook_path: Path | None = None,
    ) -> LeaseRateReview:
        trail = list(review.audit_trail)
        now = datetime.now(timezone.utc).isoformat()
        if action == "request_more_evidence":
            trail.append({"event": "LEASE_RATE_MORE_EVIDENCE_REQUESTED", "reason": reason, "timestamp": now})
            return review.model_copy(
                update={
                    "status": "LEASE_RATE_REVIEW_PENDING",
                    "analyst_action": action,
                    "analyst_reason": reason,
                    "audit_trail": trail,
                    "blocking": True,
                    "summary": "Analyst requested more evidence; review still pending.",
                }
            )
        if action == "approve":
            approved = review.proposed_rate
            trail.append({"event": "LEASE_RATE_APPROVED", "rate": approved, "reason": reason, "timestamp": now})
            status = "approved"
            code = "LEASE_RATE_ESTIMATED"
        elif action == "correct":
            if rate is None:
                raise ValueError("correct action requires a rate")
            approved = float(rate)
            trail.append(
                {
                    "event": "LEASE_RATE_ANALYST_OVERRIDDEN",
                    "proposed": review.proposed_rate,
                    "approved": approved,
                    "reason": reason,
                    "timestamp": now,
                }
            )
            status = "overridden"
            code = "LEASE_RATE_ANALYST_OVERRIDDEN"
        else:
            raise ValueError(f"Unknown lease review action: {action}")

        if workbook_path is not None and approved is not None:
            self._write_rate(workbook_path, approved)

        return review.model_copy(
            update={
                "status": status,
                "approved_rate": approved,
                "analyst_action": action,
                "analyst_reason": reason,
                "audit_trail": trail,
                "blocking": False,
                "summary": f"{code}: approved_rate={approved} (proposed={review.proposed_rate}).",
            }
        )

    def _year_from_facts(
        self, sec: SecService, company_facts: dict[str, Any] | None, fy: str
    ) -> tuple[LeaseYearData, list[dict[str, Any]]]:
        raw: list[dict[str, Any]] = []
        data: dict[str, Any] = {"fiscal_year": fy}
        post = pre = False
        if not company_facts:
            return LeaseYearData(fiscal_year=fy, regime="unknown"), raw
        for field, tags in _COMMITMENT_TAGS.items():
            for tag in tags:
                fact = sec.find_fact(company_facts, field, fy, xbrl_tag_hint=tag)
                if fact is None or fact.value is None:
                    continue
                val = float(fact.value)
                if field in {"reported_discount_rate", "remaining_term"}:
                    if field == "reported_discount_rate":
                        val = _as_rate(val)
                else:
                    val = _scale(val)
                data[field] = val
                raw.append({"field": field, "label": tag, "value": val, "form": fact.form, "accn": fact.accession_number})
                if "OperatingLeaseLiability" in tag or "RightOfUse" in tag:
                    post = True
                if "FutureMinimum" in tag:
                    pre = True
                break
        for tag in _IBR_TAGS:
            fact = sec.find_fact(company_facts, "ibr", fy, xbrl_tag_hint=tag)
            if fact is not None and fact.value is not None:
                raw.append(
                    {
                        "field": "incremental_borrowing_rate",
                        "label": tag,
                        "value": _as_rate(float(fact.value)),
                        "form": fact.form,
                    }
                )
                break
        if post and not pre:
            regime = "post_asc_842"
        elif pre and not post:
            regime = "pre_asc_842"
        elif pre and post:
            regime = "mixed"
        else:
            regime = "unknown"
        data["regime"] = regime
        data["source"] = "sec_edgar_10k"
        return LeaseYearData.model_validate(data), raw

    @staticmethod
    def _infer_from_liability(years: list[LeaseYearData]) -> float | None:
        for y in reversed(years):
            liability = None
            if y.current_liability is not None or y.long_term_liability is not None:
                liability = (y.current_liability or 0.0) + (y.long_term_liability or 0.0)
            undiscounted = y.total_undiscounted
            if undiscounted is None:
                parts = [y.year_1, y.year_2, y.year_3, y.year_4, y.year_5, y.thereafter]
                if any(p is not None for p in parts):
                    undiscounted = sum(p or 0.0 for p in parts)
            if not liability or not undiscounted or liability <= 0 or undiscounted <= 0:
                continue
            if undiscounted <= liability:
                continue
            term = y.remaining_term or 8.0
            # annuity approximation: PV = PMT * (1-(1+r)^-n)/r ≈ liability; undiscounted ≈ PMT*n
            pmt = undiscounted / max(term, 1.0)
            if pmt <= 0:
                continue
            lo, hi = 0.001, 0.25
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                pv = pmt * (1 - (1 + mid) ** (-term)) / mid
                if pv > liability:
                    lo = mid
                else:
                    hi = mid
            return round(0.5 * (lo + hi), 4)
        return None

    def _write_workbook(
        self,
        path: Path,
        years: list[LeaseYearData],
        rate: float | None,
        written: list[str],
    ) -> None:
        wb = load_workbook(path, data_only=False)
        try:
            if "Leases" not in wb.sheetnames:
                return
            ws = wb["Leases"]
            cols = detect_year_columns(ws, wb)
            field_rows = {
                "year_1": 10,
                "year_2": 11,
                "year_3": 12,
                "year_4": 13,
                "year_5": 14,
                "thereafter": 15,
                "total_undiscounted": 16,
            }
            for y in years:
                col = cols.get(y.fiscal_year)
                if not col:
                    continue
                for field, row in field_rows.items():
                    val = getattr(y, field)
                    if val is None:
                        continue
                    cell = ws.cell(row, col)
                    if isinstance(cell.value, str) and cell.value.startswith("="):
                        continue
                    if cell.value in (None, ""):
                        cell.value = val
                        written.append(f"Leases!{get_column_letter(col)}{row}")
                if rate is not None:
                    cell = ws.cell(_RATE_ROW, col)
                    if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                        if cell.value in (None, ""):
                            cell.value = rate
                            written.append(f"Leases!{get_column_letter(col)}{_RATE_ROW}")
            wb.save(path)
        finally:
            wb.close()

    @staticmethod
    def _write_rate(path: Path, rate: float) -> None:
        wb = load_workbook(path, data_only=False)
        try:
            if "Leases" not in wb.sheetnames:
                return
            ws = wb["Leases"]
            cols = detect_year_columns(ws, wb)
            fy_cols = [c for k, c in cols.items() if str(k).startswith("FY")]
            for col in fy_cols:
                cell = ws.cell(_RATE_ROW, col)
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    continue
                cell.value = rate
            wb.save(path)
        finally:
            wb.close()

    @staticmethod
    def _proposal(
        rate: float,
        method: str,
        rank: int,
        duration: float | None,
        benchmark: float | None,
        spread: float | None,
        evidence: list[str],
        attempts: list[dict[str, Any]],
        market_date: str | None,
    ) -> LeaseRateProposal:
        lo = max(rate - 0.01, 0.001)
        hi = rate + 0.01
        return LeaseRateProposal(
            proposed_rate=round(float(rate), 6),
            methodology=method,
            methodology_rank=rank,
            market_date=market_date,
            estimated_lease_duration=duration,
            benchmark_rate=benchmark,
            credit_spread=spread,
            company_evidence=evidence,
            confidence={1: 0.9, 2: 0.85, 3: 0.7, 4: 0.6, 5: 0.45, 6: 0.3}.get(rank, 0.4),
            sensitivity=[
                {"rate": round(lo, 4), "role": "lower"},
                {"rate": round(rate, 4), "role": "proposed"},
                {"rate": round(hi, 4), "role": "upper"},
            ],
            hierarchy_attempts=attempts,
        )
