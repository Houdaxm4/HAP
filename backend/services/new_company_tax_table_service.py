"""Deterministic effective-tax-rate reconciliation table extraction.

Path: prior/template schema → candidate table → label/context mapping →
signed normalization → residual Other → arithmetic reconciliation.

An optional LLM classifier may resolve *ambiguous labels only* after the
deterministic map fails. It must receive the full candidate table, heading,
permitted categories, and schema, and its output must still reconcile.
"""

from __future__ import annotations

import re
from typing import Any, Callable

from models.new_company import TaxDisclosureStatus

_HOUSE_ORDER = (
    "statutory_federal",
    "state",
    "foreign",
    "credits",
    "other",
)

_LABEL_MAP: dict[str, tuple[str, ...]] = {
    "statutory_federal": (
        "federal statutory",
        "us federal statutory",
        "statutory u.s. federal",
        "federal income tax",
        "u.s. federal",
        "statutory rate",
        "federal tax",
        "federal",
    ),
    "state": ("state and local", "state tax", "state income", "state"),
    "foreign": ("foreign rate", "foreign tax", "international", "foreign"),
    "credits": (
        "research and development tax credit",
        "research credit",
        "r&d tax credit",
        "r&d credit",
        "tax credit",
        "credits",
    ),
}

_PERCENT_HINTS = ("percent", "percentage", "%", "rate reconciliation", "effective tax rate")
_DOLLAR_HINTS = ("in millions", "in thousands", "$", "usd", "amount")
_DECREASE_HINTS = ("decrease", "benefit", "(increase) decrease", "decrease (increase)")
_PAREN_RE = re.compile(r"^\(.*\)$")
_NUM_RE = re.compile(r"[-+]?\d[\d,]*\.?\d*")


class NewCompanyTaxTableService:
    """Parse a candidate ETR reconciliation table into house categories."""

    def extract(
        self,
        *,
        fiscal_year: str,
        candidate_table: list[dict[str, Any]],
        heading: str | None = None,
        prior_schema: list[str] | None = None,
        accession_number: str | None = None,
        note_location: str | None = None,
        pretax_income: float | None = None,
        income_tax_expense: float | None = None,
        llm_classifier: Callable[..., dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        heading_l = (heading or "").lower()
        units = self._detect_units(heading_l, candidate_table)
        decrease_col = any(h in heading_l for h in _DECREASE_HINTS)

        mapped_rates: dict[str, float] = {}
        mappings: list[dict[str, Any]] = []
        unmapped: list[dict[str, Any]] = []
        reported_other = 0.0
        has_reported_other = False
        raw_lines: list[dict[str, Any]] = []
        signs_normalized = False

        for row in candidate_table:
            label = str(row.get("label") or "").strip()
            raw_val = row.get("rate", row.get("value", row.get(fiscal_year)))
            signed, parsed_from_parens = self._signed_number(
                raw_val, decrease_column=decrease_col, units=units, pretax=pretax_income
            )
            signs_normalized = signs_normalized or parsed_from_parens or decrease_col
            raw_lines.append(
                {
                    "label": label,
                    "raw_value": raw_val,
                    "normalized_signed_rate": signed,
                    "fiscal_year": fiscal_year,
                }
            )
            if signed is None or not label:
                continue
            house = str(row.get("house") or "") or self.house_category(label)
            if house == "other" and not row.get("house"):
                # Ambiguous leftover labels may use constrained fallback.
                if llm_classifier is not None and self._is_ambiguous(label):
                    classified = self._constrained_llm(
                        llm_classifier,
                        label=label,
                        signed=signed,
                        candidate_table=candidate_table,
                        heading=heading,
                        prior_schema=prior_schema or list(_HOUSE_ORDER),
                    )
                    house = classified or house
            if house == "deferred":
                unmapped.append({"label": label, "rate": signed, "reason": "deferred_excluded_from_inputs_other"})
                mappings.append({"label": label, "house": "deferred", "rate": signed, "confidence": 0.9})
                continue
            if house == "other":
                reported_other += signed
                has_reported_other = True
                mappings.append({"label": label, "house": "other", "rate": signed, "confidence": 0.7, "residual": False})
                continue
            mapped_rates[house] = mapped_rates.get(house, 0.0) + signed
            mappings.append({"label": label, "house": house, "rate": signed, "confidence": 0.95})

        etr = self._etr(candidate_table, units, pretax_income, income_tax_expense)
        specific = sum(
            mapped_rates.get(k, 0.0)
            for k in ("statutory_federal", "state", "foreign", "credits")
        )
        residual = (etr - specific) if etr is not None else None
        other_calc = None
        if residual is not None:
            other_calc = (
                "Other = Effective tax rate − statutory/federal − state − foreign − R&D tax-credit rate"
            )
            mapped_rates["other"] = residual

        disclosure = self._disclosure(mapped_rates, has_reported_other)
        recon_delta = None
        recon_status = "ok"
        if etr is not None:
            recon = (
                (mapped_rates.get("statutory_federal") or 0.0)
                + (mapped_rates.get("state") or 0.0)
                + (mapped_rates.get("foreign") or 0.0)
                + (mapped_rates.get("credits") or 0.0)
                + (mapped_rates.get("other") or 0.0)
            )
            recon_delta = recon - etr
            if abs(recon_delta) > 0.005:
                recon_status = "TAX_RECONCILIATION_REVIEW_REQUIRED"

        computed = None
        if pretax_income and abs(pretax_income) > 1e-9 and income_tax_expense is not None:
            computed = income_tax_expense / pretax_income
            if etr is not None and abs(computed - etr) > 0.03:
                recon_status = "TAX_EFFECTIVE_RATE_RECONCILIATION_FAILED"

        category_complete = mapped_rates.get("statutory_federal") is not None and etr is not None
        components = [
            {"label": house, "rate": rate, "house": house}
            for house, rate in mapped_rates.items()
            if house != "other"
        ]
        return {
            "fiscal_year": fiscal_year,
            "reported_effective_rate": etr,
            "components": components,
            "mapped_rates": mapped_rates,
            "residual_other": residual,
            "reported_other": reported_other if has_reported_other else None,
            "unmapped_lines": unmapped,
            "category_mappings": mappings,
            "disclosure_status": {k: v.value for k, v in disclosure.items()},
            "other_calculation": other_calc,
            "reconciliation_delta": recon_delta,
            "reconciliation_status": recon_status,
            "computed_effective_rate": computed,
            "units": "rate_fraction",
            "table_units": units,
            "signs_normalized": signs_normalized,
            "raw_filing_lines": raw_lines,
            "accession_number": accession_number,
            "note_or_table_location": note_location or heading,
            "source": "sec_10k_etr_reconciliation_table",
            "locations": [loc for loc in (note_location, heading, accession_number) if loc],
            "category_coverage_complete": category_complete,
            "confidence": 0.85 if category_complete and recon_status == "ok" else 0.45,
            "pretax_income": pretax_income,
            "income_tax_expense": income_tax_expense,
        }

    @staticmethod
    def house_category(label: str) -> str:
        lab = label.lower()
        if "other" in lab and "credit" not in lab:
            return "other"
        if "deferred" in lab:
            return "deferred"
        if "credit" in lab or "r&d" in lab:
            return "credits"
        if "state" in lab:
            return "state"
        if "foreign" in lab or "international" in lab:
            return "foreign"
        if "statutory" in lab or ("federal" in lab and "net of federal" not in lab):
            return "statutory_federal"
        return "other"

    @staticmethod
    def _is_ambiguous(label: str) -> bool:
        lab = label.lower()
        if not lab or lab in {"total", "effective tax rate", "etr"}:
            return False
        return NewCompanyTaxTableService.house_category(label) == "other" and "other" not in lab

    @staticmethod
    def _constrained_llm(
        classifier: Callable[..., dict[str, Any]],
        *,
        label: str,
        signed: float,
        candidate_table: list[dict[str, Any]],
        heading: str | None,
        prior_schema: list[str],
    ) -> str | None:
        result = classifier(
            label=label,
            value=signed,
            candidate_table=candidate_table,
            heading=heading,
            permitted_categories=list(_HOUSE_ORDER),
            prior_workbook_schema=prior_schema,
        )
        house = str((result or {}).get("house") or "")
        if house in _HOUSE_ORDER:
            return house
        return None

    @staticmethod
    def _detect_units(heading: str, rows: list[dict[str, Any]]) -> str:
        if any(h in heading for h in _PERCENT_HINTS) and not any(h in heading for h in ("in millions", "in thousands")):
            return "percent"
        if any(h in heading for h in _DOLLAR_HINTS) and "%" not in heading:
            return "dollars"
        magnitudes: list[float] = []
        for row in rows:
            val = row.get("rate", row.get("value"))
            if isinstance(val, (int, float)) and not isinstance(val, bool):
                magnitudes.append(abs(float(val)))
        if magnitudes and max(magnitudes) > 5:
            return "dollars"
        return "percent"

    @staticmethod
    def _signed_number(
        raw: Any,
        *,
        decrease_column: bool,
        units: str,
        pretax: float | None,
    ) -> tuple[float | None, bool]:
        if raw is None or raw == "" or isinstance(raw, bool):
            return None, False
        from_parens = False
        if isinstance(raw, (int, float)):
            n = float(raw)
        else:
            text = str(raw).strip().replace("−", "-")
            from_parens = bool(_PAREN_RE.match(text.replace(" ", ""))) or (
                text.startswith("(") and ")" in text
            )
            cleaned = text.replace("%", "").replace(",", "").replace("(", "").replace(")", "")
            try:
                n = float(cleaned)
            except (TypeError, ValueError):
                m = _NUM_RE.search(text)
                if not m:
                    return None, False
                n = float(m.group(0).replace(",", ""))
            if from_parens:
                n = -abs(n)
        if decrease_column and n > 0:
            n = -n
            from_parens = True
        if units == "percent":
            if abs(n) >= 1.0:
                n = n / 100.0
        elif units == "dollars":
            if pretax is None or abs(pretax) < 1e-9:
                return None, from_parens
            n = n / pretax
        return n, from_parens

    @staticmethod
    def _etr(
        rows: list[dict[str, Any]],
        units: str,
        pretax: float | None,
        tax_expense: float | None,
    ) -> float | None:
        for row in rows:
            lab = str(row.get("label") or "").lower()
            if "effective" in lab and "tax" in lab:
                signed, _ = NewCompanyTaxTableService._signed_number(
                    row.get("rate", row.get("value")),
                    decrease_column=False,
                    units=units,
                    pretax=pretax,
                )
                if signed is not None:
                    return signed
        if pretax and abs(pretax) > 1e-9 and tax_expense is not None:
            return tax_expense / pretax
        return None

    @staticmethod
    def _disclosure(
        mapped: dict[str, float], has_reported_other: bool
    ) -> dict[str, TaxDisclosureStatus]:
        out: dict[str, TaxDisclosureStatus] = {}
        for house in ("statutory_federal", "state", "foreign", "credits", "other"):
            if house not in mapped:
                out[house] = (
                    TaxDisclosureStatus.INCLUDED_IN_OTHER
                    if has_reported_other or mapped.get("other") is not None
                    else TaxDisclosureStatus.UNRESOLVED
                )
            elif mapped[house] == 0:
                out[house] = TaxDisclosureStatus.REPORTED_ZERO
            else:
                out[house] = TaxDisclosureStatus.REPORTED
        return out
