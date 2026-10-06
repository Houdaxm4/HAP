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
from services.hap_analysis_layout_service import HapAnalysisLayoutService
from services.sec_service import SecService
from services.tab_notes import add_notes, note

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

_FINANCE_TAGS = {
    "finance_current_liability": ("FinanceLeaseLiabilityCurrent",),
    "finance_long_term_liability": ("FinanceLeaseLiabilityNoncurrent",),
    "finance_rou_asset": ("FinanceLeaseRightOfUseAsset",),
    "finance_cost": ("FinanceLeaseInterestExpense", "FinanceLeaseCost"),
    "finance_undiscounted": (
        "LesseeFinanceLeaseLiabilityPaymentsDue",
        "FutureMinimumLeasePaymentsFinanceLeases",
    ),
}

_IBR_TAGS = (
    "LesseeOperatingLeaseIncrementalBorrowingRate",
    "IncrementalBorrowingRate",
)

_RATE_ROW = 18
_SUPPORTED = {"disclosed", "disclosed_historical", "derived", "estimated"}


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

        filing_cache: dict[str, Any] = {}
        for fy in fiscal_years:
            rec, raw = self._year_from_facts(sec, company_facts, fy)
            if rec.regime in {"unknown", "pre_asc_842"} and rec.year_1 is None and rec.rou_asset is None and rec.total_undiscounted is None:
                rec, raw = self._commitments_from_filing(sec, ticker, fy, rec, raw, filing_cache)
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
        supported = (
            proposal.classification in _SUPPORTED and proposal.proposed_rate is not None
        )
        applied_rate = proposal.proposed_rate if supported else None
        self._write_workbook(workbook_path, years, applied_rate, written)

        latest = years[-1] if years else None
        now = datetime.now(timezone.utc).isoformat()
        if supported:
            review = LeaseRateReview(
                analysis_id=analysis_id,
                ticker=ticker,
                status="autonomous_selected",
                proposed_rate=proposal.proposed_rate,
                selected_rate=proposal.proposed_rate,
                approved_rate=None,
                decision_class="AUTONOMOUS_AGENT_DECISION",
                classification=proposal.classification,
                supporting_evidence=proposal.company_evidence,
                prior_or_comparable_rates=list(comparable_rates or []),
                calculated_lease_asset=latest.rou_asset if latest else None,
                calculated_lease_liability=(
                    (latest.current_liability or 0) + (latest.long_term_liability or 0)
                    if latest
                    and (latest.current_liability is not None or latest.long_term_liability is not None)
                    else None
                ),
                sensitivity=proposal.sensitivity,
                proposal=proposal,
                blocking=False,
                audit_trail=[
                    {
                        "event": "AUTONOMOUS_AGENT_DECISION",
                        "rate": proposal.proposed_rate,
                        "methodology": proposal.methodology,
                        "classification": proposal.classification,
                        "timestamp": now,
                    }
                ],
                summary=(
                    f"AUTONOMOUS_AGENT_DECISION: selected_rate={proposal.proposed_rate} "
                    f"({proposal.classification} via {proposal.methodology}). "
                    "Optional analyst override is available; routine approval is not required."
                ),
            )
        else:
            review = LeaseRateReview(
                analysis_id=analysis_id,
                ticker=ticker,
                status="LEASE_RATE_EVIDENCE_INSUFFICIENT",
                proposed_rate=None,
                selected_rate=None,
                approved_rate=None,
                decision_class="EVIDENCE_INSUFFICIENT",
                classification="insufficient",
                supporting_evidence=proposal.company_evidence,
                prior_or_comparable_rates=list(comparable_rates or []),
                calculated_lease_asset=latest.rou_asset if latest else None,
                calculated_lease_liability=(
                    (latest.current_liability or 0) + (latest.long_term_liability or 0)
                    if latest
                    and (latest.current_liability is not None or latest.long_term_liability is not None)
                    else None
                ),
                sensitivity=proposal.sensitivity,
                proposal=proposal,
                blocking=False,
                audit_trail=[
                    {
                        "event": "LEASE_RATE_EVIDENCE_INSUFFICIENT",
                        "methodology": proposal.methodology,
                        "timestamp": now,
                    }
                ],
                summary=(
                    "LEASE_RATE_EVIDENCE_INSUFFICIENT: no company-disclosed or derived rate "
                    "could be supported. No rate was fabricated. Gate F fails; the run does "
                    "not pause for routine approval."
                ),
            )
        notes = self.write_decision_notes(workbook_path, review)
        review = review.model_copy(update={"notes_written": notes})
        written.extend(notes)
        complete = all(
            y.year_1 is not None
            or y.rou_asset is not None
            or y.total_undiscounted is not None
            or y.finance_rou_asset is not None
            for y in years
        ) and bool(years)
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
                f"selected_rate={review.selected_rate}; "
                f"decision={review.decision_class}; status={review.status}."
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
        latest_year = years[-1] if years else None
        duration = next((y.remaining_term for y in reversed(years) if y.remaining_term), None)

        def _src(year: LeaseYearData | None) -> tuple[str | None, str | None]:
            if year is None:
                return None, None
            form = next((str(r.get("form")) for r in year.raw_labels if r.get("form")), None)
            accn = next((str(r.get("accn")) for r in year.raw_labels if r.get("accn")), None)
            return form, accn

        # A. Company-disclosed weighted-average operating-lease discount rate — latest year.
        if latest_year and latest_year.reported_discount_rate is not None:
            rate = _as_rate(latest_year.reported_discount_rate)
            form, accn = _src(latest_year)
            attempts.append({"rank": 1, "method": "reported_weighted_average_discount_rate", "rate": rate})
            evidence.append(
                f"{latest_year.fiscal_year} reported operating-lease WtdAvg discount rate {rate:.4f}."
            )
            return self._proposal(
                rate,
                "reported_weighted_average_discount_rate",
                1,
                duration,
                treasury_yield,
                credit_spread,
                evidence,
                attempts,
                market_date,
                classification="disclosed",
                source_fiscal_year=latest_year.fiscal_year,
                source_form=form,
                source_accession=accn,
                limitations="Company-disclosed ASC 842 weighted-average discount rate for the latest fiscal year.",
            )

        # B. Historical company-disclosed rate if the latest year is missing.
        historical = next((y for y in reversed(years) if y.reported_discount_rate is not None), None)
        if historical is not None:
            rate = _as_rate(historical.reported_discount_rate)
            form, accn = _src(historical)
            attempts.append({"rank": 2, "method": "historical_reported_weighted_average_discount_rate", "rate": rate})
            latest_label = latest_year.fiscal_year if latest_year else "latest year"
            evidence.append(
                f"{historical.fiscal_year} reported operating-lease WtdAvg discount rate {rate:.4f}. "
                f"{latest_label} did not disclose a current rate."
            )
            return self._proposal(
                rate,
                "historical_reported_weighted_average_discount_rate",
                2,
                duration,
                treasury_yield,
                credit_spread,
                evidence,
                attempts,
                market_date,
                classification="disclosed_historical",
                source_fiscal_year=historical.fiscal_year,
                source_form=form,
                source_accession=accn,
                limitations=(
                    f"Used a prior-year disclosed rate ({historical.fiscal_year}) because the "
                    f"latest period did not report a weighted-average discount rate. Applicability "
                    "depends on whether the company's lease portfolio and credit profile are still comparable."
                ),
            )

        # C. Incremental borrowing rate (company-disclosed).
        ibr = next((y for y in reversed(years) if any(
            r.get("field") == "incremental_borrowing_rate" for r in y.raw_labels
        )), None)
        if ibr:
            raw = next(r for r in ibr.raw_labels if r.get("field") == "incremental_borrowing_rate")
            rate = _as_rate(float(raw["value"]))
            attempts.append({"rank": 3, "method": "incremental_borrowing_rate", "rate": rate})
            evidence.append(f"{ibr.fiscal_year} incremental borrowing rate {rate:.4f}.")
            return self._proposal(
                rate,
                "incremental_borrowing_rate",
                3,
                duration,
                treasury_yield,
                credit_spread,
                evidence,
                attempts,
                market_date,
                classification="disclosed",
                source_fiscal_year=ibr.fiscal_year,
                source_form=str(raw.get("form") or "") or None,
                source_accession=str(raw.get("accn") or "") or None,
                limitations="Company-disclosed incremental borrowing rate used as the lease discount rate.",
            )

        # C. Inferred from undiscounted payments vs reported liability.
        inferred = self._infer_from_liability(years)
        attempts.append({"rank": 4, "method": "inferred_undiscounted_vs_liability", "rate": inferred})
        if inferred is not None:
            evidence.append(
                f"Inferred discount rate {inferred:.4f} from undiscounted commitments vs lease liability."
            )
            src_year = next(
                (y.fiscal_year for y in reversed(years) if (y.current_liability or y.long_term_liability) and (y.total_undiscounted or y.year_1)),
                None,
            )
            return self._proposal(
                inferred,
                "inferred_undiscounted_vs_liability",
                4,
                duration,
                treasury_yield,
                credit_spread,
                evidence,
                attempts,
                market_date,
                classification="derived",
                source_fiscal_year=src_year,
                limitations="Derived from the relationship between undiscounted lease payments and the reported liability; not a company-stated rate.",
            )

        # C. After-tax cost of debt when that input is evidenced.
        if after_tax_cost_of_debt is not None:
            pretax = after_tax_cost_of_debt / 0.79 if after_tax_cost_of_debt < 0.2 else after_tax_cost_of_debt
            attempts.append({"rank": 5, "method": "debt_yield_adjusted", "rate": pretax})
            evidence.append(
                f"After-tax cost of debt {after_tax_cost_of_debt:.4f} grossed up for lease-term unsecured borrowing."
            )
            return self._proposal(
                float(pretax),
                "debt_yield_adjusted",
                5,
                duration,
                treasury_yield,
                credit_spread,
                evidence,
                attempts,
                market_date,
                classification="estimated",
                limitations="Estimated from evidenced after-tax cost of debt; not a lease footnote disclosure.",
            )
        if wacc is not None:
            attempts.append({"rank": 5, "method": "wacc_proxy_rejected_prefer_debt", "rate": None})
            evidence.append("WACC was available but was not used as a lease-rate proxy.")

        if treasury_yield is not None and credit_spread is not None:
            blended = treasury_yield + credit_spread
            attempts.append(
                {
                    "rank": 6,
                    "method": "risk_free_plus_credit_spread",
                    "rate": blended,
                    "rf": treasury_yield,
                    "spread": credit_spread,
                }
            )
            evidence.append(
                f"Benchmark yield {treasury_yield:.4f} plus company credit spread {credit_spread:.4f}."
            )
            return self._proposal(
                blended,
                "risk_free_plus_credit_spread",
                6,
                duration,
                treasury_yield,
                credit_spread,
                evidence,
                attempts,
                market_date,
                classification="estimated",
                limitations="Estimated from evidenced treasury yield and credit spread; not a company-disclosed lease rate.",
            )

        if comparable_rates:
            med = sorted(comparable_rates)[len(comparable_rates) // 2]
            attempts.append({"rank": 7, "method": "comparable_or_sector_not_used", "rate": med})
            evidence.append(
                f"Comparable/sector median {med:.4f} was observed but not substituted as the selected rate."
            )

        evidence.append(
            "No company-disclosed weighted-average lease discount rate, incremental borrowing rate, "
            "or evidenced derivation inputs were available. No rate was fabricated."
        )
        attempts.append({"rank": 99, "method": "insufficient_evidence", "rate": None})
        return self._proposal(
            None,
            "insufficient_evidence",
            99,
            duration,
            treasury_yield,
            credit_spread,
            evidence,
            attempts,
            market_date,
            classification="insufficient",
            limitations="Insufficient evidence to select a defensible long-term lease discount rate.",
        )

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
                    "decision_class": review.decision_class,
                    "summary": "Analyst requested more evidence; optional review is pending.",
                }
            )
        if action == "approve":
            selected = review.selected_rate if review.selected_rate is not None else review.proposed_rate
            trail.append(
                {
                    "event": "ANALYST_ACKNOWLEDGED",
                    "rate": selected,
                    "reason": reason,
                    "timestamp": now,
                }
            )
            status = review.status if review.status != "LEASE_RATE_REVIEW_PENDING" else "autonomous_selected"
            decision_class = review.decision_class or "AUTONOMOUS_AGENT_DECISION"
            if decision_class == "EVIDENCE_INSUFFICIENT":
                decision_class = "AUTONOMOUS_AGENT_DECISION"
            code = "ANALYST_ACKNOWLEDGED"
            approved = None
            analyst_action = "acknowledge"
        elif action == "correct":
            if rate is None:
                raise ValueError("correct action requires a rate")
            selected = float(rate)
            trail.append(
                {
                    "event": "ANALYST_OVERRIDE",
                    "proposed": review.proposed_rate,
                    "selected": selected,
                    "reason": reason,
                    "timestamp": now,
                }
            )
            status = "overridden"
            code = "ANALYST_OVERRIDE"
            approved = selected
            analyst_action = "correct"
            decision_class = "ANALYST_OVERRIDE"
        else:
            raise ValueError(f"Unknown lease review action: {action}")

        if workbook_path is not None and selected is not None:
            self._write_rate(workbook_path, selected)
            notes = self.write_decision_notes(
                workbook_path,
                review.model_copy(
                    update={
                        "selected_rate": selected,
                        "decision_class": decision_class,
                        "classification": "estimated" if decision_class == "ANALYST_OVERRIDE" else review.classification,
                    }
                ),
            )
        else:
            notes = list(review.notes_written)

        return review.model_copy(
            update={
                "status": status,
                "selected_rate": selected,
                "approved_rate": approved,
                "analyst_action": analyst_action,
                "analyst_reason": reason,
                "decision_class": decision_class,
                "audit_trail": trail,
                "blocking": False,
                "notes_written": notes,
                "summary": f"{code}: selected_rate={selected} (proposed={review.proposed_rate}).",
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
        for field, tags in _FINANCE_TAGS.items():
            for tag in tags:
                fact = sec.find_fact(company_facts, field, fy, xbrl_tag_hint=tag)
                if fact is None or fact.value is None:
                    continue
                val = float(fact.value)
                data[field] = _scale(val) if "term" not in field else val
                raw.append(
                    {
                        "field": field,
                        "label": tag,
                        "value": data[field],
                        "form": fact.form,
                        "accn": fact.accession_number,
                    }
                )
                post = True
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
    def _commitments_from_filing(sec: SecService, ticker: str, fy: str, rec: LeaseYearData, raw: list, cache: dict[str, Any]):
        """A pre-ASC 842 year with no structured lease data: read the commitments table in that year's own 10-K note."""
        from services.lease_text_parsers import parse_operating_lease_commitments
        from services.new_company_buyback_service import html_to_text

        if "by_year" not in cache:
            try:
                cik = sec.resolve_cik(ticker)
                filings = sec.list_recent_filings(cik, forms={"10-K", "10-K/A"})
            except Exception:  # noqa: BLE001 - a fallback: the year stays incomplete and the gate says so
                cik, filings = None, []
            by_year: dict[int, dict[str, Any]] = {}
            for filing in filings:
                year = filing.get("fiscal_year")
                if year and filing.get("document_url"):
                    current = by_year.get(int(year))
                    if current is None or (current.get("filing_type") != "10-K" and filing.get("filing_type") == "10-K"):
                        by_year[int(year)] = filing          # the original 10-K, not a Part III amendment (10-K/A)
            cache.update({"by_year": by_year, "cik": cik})
        filing = cache["by_year"].get(int(fy[2:])) if str(fy).startswith("FY") and fy[2:].isdigit() else None
        if filing is None:
            return rec, raw
        try:
            html = sec.fetch_document_text(filing["document_url"], cik=cache["cik"], cache_name=f"10k_lease_{fy[2:]}.htm")
        except Exception:  # noqa: BLE001
            return rec, raw
        parsed = parse_operating_lease_commitments(html_to_text(html))
        if not parsed:
            return rec, raw
        label = f"sec_10k_text:operating_lease_commitments:{fy}"
        update = {**parsed, "regime": "pre_asc_842", "source": "sec_edgar_10k_text"}
        raw = list(raw) + [{"field": key, "label": label, "value": value, "form": "10-K"} for key, value in parsed.items()]
        return rec.model_copy(update=update), raw

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
            label_fields = {
                "rou asset": "rou_asset",
                "right-of-use": "rou_asset",
                "current liability": "current_liability",
                "long-term liability": "long_term_liability",
                "long term liability": "long_term_liability",
                "lease cost": "lease_cost",
                "lease expense": "lease_cost",
                "remaining term": "remaining_term",
                "finance rou": "finance_rou_asset",
                "finance lease liability current": "finance_current_liability",
            }
            rate_row = _RATE_ROW
            for row in range(1, min(ws.max_row or 1, 40) + 1):
                lab = str(ws.cell(row, 1).value or "").strip().lower()
                for needle, field in label_fields.items():
                    if needle in lab:
                        field_rows[field] = row
                if any(
                    n in lab
                    for n in ("long-term rate", "long term rate", "discount rate", "lease rate")
                ):
                    rate_row = row
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
                    cell = ws.cell(rate_row, col)
                    if not (isinstance(cell.value, str) and cell.value.startswith("=")):
                        cell.value = rate
                        written.append(f"Leases!{get_column_letter(col)}{rate_row}")
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
            rate_row = _RATE_ROW
            for row in range(1, min(ws.max_row or 1, 40) + 1):
                lab = str(ws.cell(row, 1).value or "").strip().lower()
                if any(
                    n in lab
                    for n in ("long-term rate", "long term rate", "discount rate", "lease rate")
                ):
                    rate_row = row
                    break
            fy_cols = [c for k, c in cols.items() if str(k).startswith("FY")]
            for col in fy_cols:
                cell = ws.cell(rate_row, col)
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    continue
                cell.value = rate
            wb.save(path)
        finally:
            wb.close()

    @staticmethod
    def write_decision_notes(path: Path, review: LeaseRateReview) -> list[str]:
        wb = load_workbook(path, data_only=False)
        try:
            if "Leases" not in wb.sheetnames:
                return []
            proposal = review.proposal
            rate = review.selected_rate if review.selected_rate is not None else review.proposed_rate
            rate_txt = f"{rate * 100:.2f}%" if isinstance(rate, (int, float)) else "not selected"
            ws = wb["Leases"]
            rate_row = _RATE_ROW
            for row in range(1, min(ws.max_row or 1, 40) + 1):
                lab = str(ws.cell(row, 1).value or "").strip().lower()
                if any(
                    n in lab
                    for n in ("long-term rate", "long term rate", "discount rate", "lease rate")
                ):
                    rate_row = row
                    break
            cols = detect_year_columns(ws, wb)
            fy_cols = [c for k, c in cols.items() if str(k).startswith("FY")]
            formula_addrs: list[str] = []
            value_addrs: list[str] = []
            for col in fy_cols:
                cell = ws.cell(rate_row, col)
                addr = f"Leases!{get_column_letter(col)}{rate_row}"
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    formula_addrs.append(addr)
                elif cell.value not in (None, ""):
                    value_addrs.append(addr)
            sample_formula = None
            if fy_cols:
                raw = ws.cell(rate_row, fy_cols[0]).value
                if isinstance(raw, str) and raw.startswith("="):
                    sample_formula = raw
            uses_template_long_term = bool(formula_addrs)
            if uses_template_long_term:
                model_input = (
                    f"Leases row {rate_row} formulas preserved"
                    + (f" (example {formula_addrs[0]}={sample_formula})" if sample_formula else "")
                    + ". NPV/PV of lease commitments use this Estimated Long-Term Rate "
                    "(Interest Expense / Total Debt). The disclosed ASC 842 weighted-average "
                    "rate is not substituted for that template methodology."
                )
                applied = (
                    f"HAP ANALYSIS notes only. Disclosed {rate_txt} was not written over "
                    f"{len(formula_addrs)} formula cell(s) on Leases row {rate_row}."
                )
            else:
                model_input = (
                    f"Leases row {rate_row} "
                    + (", ".join(value_addrs[:3]) if value_addrs else f"(no FY formulas on row {rate_row})")
                )
                applied = (
                    f"Selected {rate_txt} written to Leases row {rate_row} where cells were not formulas."
                )
            form = (proposal.source_form if proposal else None) or "SEC filing"
            year = (proposal.source_fiscal_year if proposal else None) or ""
            sources = {
                "disclosed": f"the company's {form} {year} lease note".replace("  ", " "),
                "disclosed_historical": f"the company's earlier {form} lease note",
                "derived": "the company's lease commitments and lease liability in the 10-K",
                "estimated": "the company's debt cost and market benchmark rates",
            }
            source = sources.get(review.classification or "", "the company's 10-K")
            how = {
                "disclosed": "it is the discount rate the company itself reports for its operating leases",
                "disclosed_historical": "the latest year gives no rate, so the most recent reported rate was used",
                "derived": "the company gives no rate, so it was worked out from the lease payments and the lease liability",
                "estimated": "the company gives no rate, so it was estimated from its cost of debt",
            }.get(review.classification or "", "it is the best supported rate available")
            lines = [
                note(f"Lease discount rate set at {rate_txt}", how, source),
            ]
            written = add_notes(ws, lines, replace_containing=("Lease discount rate set at",))
            wb.save(path)
            return written
        finally:
            wb.close()

    @staticmethod
    def _proposal(
        rate: float | None,
        method: str,
        rank: int,
        duration: float | None,
        benchmark: float | None,
        spread: float | None,
        evidence: list[str],
        attempts: list[dict[str, Any]],
        market_date: str | None,
        *,
        classification: str,
        source_fiscal_year: str | None = None,
        source_form: str | None = None,
        source_accession: str | None = None,
        limitations: str | None = None,
    ) -> LeaseRateProposal:
        rounded = round(float(rate), 6) if rate is not None else None
        lo = max((rate or 0) - 0.01, 0.001) if rate is not None else None
        hi = (rate + 0.01) if rate is not None else None
        sensitivity: list[dict[str, Any]] = []
        if rate is not None and lo is not None and hi is not None:
            sensitivity = [
                {"rate": round(lo, 4), "role": "lower"},
                {"rate": round(rate, 4), "role": "proposed"},
                {"rate": round(hi, 4), "role": "upper"},
            ]
        return LeaseRateProposal(
            proposed_rate=rounded,
            methodology=method,
            methodology_rank=rank,
            classification=classification,
            source_fiscal_year=source_fiscal_year,
            source_form=source_form,
            source_accession=source_accession,
            limitations=limitations,
            market_date=market_date,
            estimated_lease_duration=duration,
            benchmark_rate=benchmark,
            credit_spread=spread,
            company_evidence=evidence,
            confidence={1: 0.9, 2: 0.75, 3: 0.85, 4: 0.7, 5: 0.6, 6: 0.5}.get(rank, 0.2),
            sensitivity=sensitivity,
            hierarchy_attempts=attempts,
        )
