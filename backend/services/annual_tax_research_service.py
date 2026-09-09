"""Extract annual tax reconciliation inputs from SEC companyfacts."""

from __future__ import annotations

from typing import Any

from models.annual_update import ResearchQuestion
from services.sec_service import SecService

# Absolute USD tags for component extraction (annual FY).
_TAX_COMPONENT_TAGS: dict[str, list[str]] = {
    "statutory_federal": [
        "IncomeTaxReconciliationIncomeTaxExpenseBenefitAtFederalStatutoryIncomeTaxRate",
        "FederalIncomeTaxExpenseBenefitContinuingOperations",
        "CurrentFederalTaxExpenseBenefit",
    ],
    "state": [
        "IncomeTaxReconciliationStateAndLocalIncomeTaxes",
        "StateAndLocalIncomeTaxExpenseBenefitContinuingOperations",
        "CurrentStateAndLocalTaxExpenseBenefit",
    ],
    "foreign": [
        "IncomeTaxReconciliationForeignIncomeTaxRateDifferential",
        "ForeignIncomeTaxExpenseBenefitContinuingOperations",
        "CurrentForeignTaxExpenseBenefit",
    ],
    "credits": [
        "IncomeTaxReconciliationTaxCreditsResearch",
        "ResearchAndDevelopmentTaxCredit",
    ],
    "deferred": [
        "DeferredFederalIncomeTaxExpenseBenefit",
        "DeferredStateAndLocalIncomeTaxExpenseBenefit",
    ],
}

_PRETAX_TAGS = [
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesDomestic",
]

_TAX_EXPENSE_TAGS = [
    "IncomeTaxExpenseBenefit",
    "IncomeTaxExpenseBenefitContinuingOperations",
]

_ETR_TAGS = [
    "EffectiveIncomeTaxRateContinuingOperations",
    "EffectiveIncomeTaxRateReconciliationAtFederalStatutoryIncomeTaxRate",
]


def _fy_year(fiscal_year: str) -> int:
    digits = "".join(ch for ch in str(fiscal_year) if ch.isdigit())
    return int(digits) if digits else 0


def _find_10k_fy_entry(company_facts: dict[str, Any], tag: str, fy: int) -> dict[str, Any] | None:
    """Best 10-K annual fact for filing fiscal year (handles non-December year-ends)."""
    payload = company_facts.get("facts", {}).get("us-gaap", {}).get(tag, {})
    best: dict[str, Any] | None = None
    best_key = ("", "")
    for unit_entries in (payload.get("units") or {}).values():
        for entry in unit_entries:
            if entry.get("form") != "10-K" or entry.get("fp") != "FY":
                continue
            if entry.get("fy") != fy or entry.get("val") is None:
                continue
            end = str(entry.get("end") or "")
            filed = str(entry.get("filed") or "")
            key = (end, filed)
            if key > best_key:
                best_key = key
                best = entry
    return best


class AnnualTaxResearchService:
    """Semantic tax extraction: ETR + reconciliation components from SEC XBRL."""

    def extract_tax_inputs(
        self,
        *,
        company_facts: dict[str, Any] | None,
        fiscal_year: str,
        ticker: str,
    ) -> tuple[dict[str, Any], list[ResearchQuestion]]:
        questions: list[ResearchQuestion] = []
        if not company_facts:
            questions.append(
                ResearchQuestion(
                    question=f"What is the reported effective tax rate for {fiscal_year}?",
                    concept="tax_effective_rate",
                    sources_searched=["sec_companyfacts"],
                    unsuccessful=True,
                    rationale="No SEC companyfacts available.",
                )
            )
            return {}, questions

        sec = SecService()
        period = fiscal_year if fiscal_year.startswith("FY") else f"FY{fiscal_year}"
        fy = _fy_year(period)

        etr = None
        etr_source = None
        for tag in _ETR_TAGS:
            fact = sec.find_fact(company_facts, tag, period, xbrl_tag_hint=tag)
            if fact is not None and fact.value is not None:
                val = float(fact.value)
                etr = val / 100.0 if abs(val) > 1.5 else val
                etr_source = f"SEC XBRL {tag}"
                break

        pretax_entry = None
        tax_entry = None
        for tag in _PRETAX_TAGS:
            pretax_entry = _find_10k_fy_entry(company_facts, tag, fy)
            if pretax_entry:
                break
        if pretax_entry is None:
            for tag in _PRETAX_TAGS:
                fact = sec.find_fact(company_facts, tag, period, xbrl_tag_hint=tag)
                if fact is not None and fact.value is not None:
                    pretax_entry = {"val": fact.value, "form": fact.form, "filed": fact.filed}
                    break

        for tag in _TAX_EXPENSE_TAGS:
            tax_entry = _find_10k_fy_entry(company_facts, tag, fy)
            if tax_entry:
                break
        if tax_entry is None:
            for tag in _TAX_EXPENSE_TAGS:
                fact = sec.find_fact(company_facts, tag, period, xbrl_tag_hint=tag)
                if fact is not None and fact.value is not None:
                    tax_entry = {"val": fact.value, "form": fact.form, "filed": fact.filed}
                    break

        pretax = float(pretax_entry["val"]) if pretax_entry else None
        tax_expense = float(tax_entry["val"]) if tax_entry else None

        if etr is None and pretax and tax_expense and abs(pretax) > 1:
            etr = tax_expense / pretax
            etr_source = "computed: 10-K IncomeTaxExpenseBenefit / pretax income"

        components: list[dict[str, Any]] = []
        locations: list[str] = []
        for house, tags in _TAX_COMPONENT_TAGS.items():
            for tag in tags:
                entry = _find_10k_fy_entry(company_facts, tag, fy)
                if entry is None:
                    fact = sec.find_fact(company_facts, tag, period, xbrl_tag_hint=tag)
                    if fact is None or fact.value is None:
                        continue
                    if pretax is None or abs(pretax) < 1:
                        continue
                    rate = float(fact.value) / pretax
                    label = fact.label or tag
                else:
                    if pretax is None or abs(pretax) < 1:
                        continue
                    rate = float(entry["val"]) / pretax
                    label = tag
                components.append({"label": label, "rate": rate, "house": house})
                locations.append(f"SEC {tag} FY{fy} 10-K")
                break

        if etr is not None:
            questions.append(
                ResearchQuestion(
                    question=f"What is the reported effective tax rate for {period}?",
                    concept="tax_effective_rate",
                    sources_searched=[
                        "sec_xbrl_effective_rate",
                        "sec_xbrl_10k_pretax_tax_expense",
                    ],
                    extracted_value=round(etr, 6),
                    source_selected=etr_source,
                    confidence=0.85 if etr_source and "computed" not in etr_source else 0.75,
                    rationale=f"ETR {etr:.2%} for {ticker} {period} from {etr_source}.",
                )
            )
        else:
            questions.append(
                ResearchQuestion(
                    question=f"What is the reported effective tax rate for {period}?",
                    concept="tax_effective_rate",
                    sources_searched=[
                        "sec_xbrl_effective_rate",
                        "sec_xbrl_10k_pretax_tax_expense",
                    ],
                    unsuccessful=True,
                    rationale="Could not derive ETR from SEC XBRL for requested fiscal year.",
                )
            )

        payload: dict[str, Any] = {
            "reported_effective_rate": etr,
            "components": [
                {"label": c["label"], "rate": c["rate"], "house": c["house"]}
                for c in components
            ],
            "source": etr_source or "sec_edgar_10k",
            "locations": locations,
            "pretax_income": pretax,
            "income_tax_expense": tax_expense,
        }
        return payload, questions
