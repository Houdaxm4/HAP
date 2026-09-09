"""Extract Inputs-tab tax components from SEC companyfacts (10-K annuals)."""

from __future__ import annotations

from typing import Any

from canonical_model.inputs_bridge import InputsBridge
from canonical_model.primitives import FinancialPoint, FinancialSeries, LineItemProvenance
from services.sec_service import SecService

# Prefer continuing-operations totals; fall back to current tax expense tags.
_TAX_COMPONENT_TAGS: dict[str, list[str]] = {
    "tax_federal": [
        "FederalIncomeTaxExpenseBenefitContinuingOperations",
        "CurrentFederalTaxExpenseBenefit",
    ],
    "tax_state": [
        "StateAndLocalIncomeTaxExpenseBenefitContinuingOperations",
        "CurrentStateAndLocalTaxExpenseBenefit",
    ],
    "tax_foreign": [
        "ForeignIncomeTaxExpenseBenefitContinuingOperations",
        "CurrentForeignTaxExpenseBenefit",
    ],
    "tax_expense": [
        "IncomeTaxExpenseBenefit",
    ],
}


def populate_inputs_tax_from_sec(
    bridge: InputsBridge,
    company_facts: dict[str, Any],
    *,
    years: int = 10,
) -> InputsBridge:
    """
    Fill tax series in USD (absolute). Caller maps to Inputs millions via transformation.

    Does not invent values — missing tags/years stay absent (→ MISSING_SOURCE downstream).
    Sets tax_unit_flag=0 so Inputs table uses millions mode.
    """
    sec = SecService()
    latest = _latest_fy(company_facts, sec)
    if latest is None:
        return bridge
    year_list = list(range(latest - years + 1, latest + 1))
    bridge.tax_unit_flag = 0

    for field, tags in _TAX_COMPONENT_TAGS.items():
        series = FinancialSeries(name=field, currency="USD")
        for fy in year_list:
            fact = None
            used_tag = None
            for tag in tags:
                fact = sec.find_fact(
                    company_facts,
                    tag,
                    f"FY{fy}",
                    xbrl_tag_hint=tag,
                )
                if fact is not None and fact.value is not None:
                    used_tag = tag
                    break
            if fact is None or fact.value is None or used_tag is None:
                continue
            series.points.append(
                FinancialPoint(
                    period=f"FY{fy}",
                    value=float(fact.value),
                    currency=str(fact.unit or "USD"),
                    source="sec_edgar_10k",
                    confidence=0.95,
                    audited=True,
                    provenance=LineItemProvenance(
                        concept=used_tag,
                        xbrl_tag=used_tag,
                        filing_type=fact.form,
                        accession_number=fact.accession_number,
                        source_document=f"SEC {fact.form} FY{fy}",
                    ),
                )
            )
        setattr(bridge, field, series)
    return bridge


def _latest_fy(company_facts: dict[str, Any], sec: SecService) -> int | None:
    for tag in ("IncomeTaxExpenseBenefit", "Revenues", "NetIncomeLoss"):
        for year in range(2030, 1995, -1):
            fact = sec.find_fact(
                company_facts,
                tag,
                f"FY{year}",
                xbrl_tag_hint=tag,
            )
            if fact is not None and fact.value is not None:
                return year
    return None
