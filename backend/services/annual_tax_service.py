"""New-FY tax-rate table: reuse house categories; Other is the residual to reported ETR."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.annual_update import AnnualTaxReport, TaxComponent
from services.annual_period_service import detect_year_columns, detect_workbook_years

# House taxonomy (must match prior Inputs years).
_HOUSE_ORDER = (
    "statutory_federal",
    "state",
    "foreign",
    "credits",
    "deferred",
    "other",
)

_LABEL_MAP: dict[str, tuple[str, ...]] = {
    "statutory_federal": ("federal statutory", "us federal", "statutory rate", "federal tax", "federal"),
    "state": ("state", "state and local"),
    "foreign": ("foreign", "international"),
    "credits": ("credit", "r&d credit", "research credit", "r&d tax"),
    "deferred": ("deferred",),
    "other": ("all other", "other items", "other"),
}

# Inputs tax-table rows (Industrial Template).
_INPUTS_TAX_ROWS: dict[str, tuple[str, ...]] = {
    "statutory_federal": ("federal tax", "federal"),
    "state": ("state taxes", "state"),
    "foreign": ("foreign taxes", "foreign"),
    "credits": ("r&d tax credits", "tax credits", "credits"),
    "other": ("all other items", "other"),
    "total": ("income tax expense", "total"),
}

_ETR_TOLERANCE = 0.01  # 100 bps absolute on rate fraction


def _num(v: Any) -> float | None:
    if v is None or v == "" or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        text = str(v).replace("%", "").replace(",", "").strip()
        n = float(text)
    except (TypeError, ValueError):
        return None
    if abs(n) > 1.5:
        n = n / 100.0
    return n


def _fy_token(fy: str) -> str:
    return fy if str(fy).startswith("FY") else f"FY{fy}"


class AnnualTaxService:
    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_year: str,
        reported_effective_rate: float | None,
        filing_components: list[dict[str, Any]] | None = None,
        source: str | None = None,
        source_locations: list[str] | None = None,
        pretax_income: float | None = None,
        income_tax_expense: float | None = None,
    ) -> AnnualTaxReport:
        """Map filing recon into existing house rows; Other = ETR − sum(specifics)."""
        mapped: dict[str, TaxComponent] = {}
        for raw in filing_components or []:
            label = str(raw.get("label") or "").lower()
            rate = _num(raw.get("rate"))
            if rate is None:
                continue
            house = str(raw.get("house") or "") or self._house_category(label)
            if house == "other":
                continue  # never treat filing "Other" as house Other
            mapped[house] = TaxComponent(
                house_category=house,
                rate=rate,
                source_label=str(raw.get("label")),
                residual=False,
            )

        etr = _num(reported_effective_rate)
        if etr is None and pretax_income and income_tax_expense and abs(pretax_income) > 1e-9:
            etr = float(income_tax_expense) / float(pretax_income)
            source = source or "computed: income_tax_expense / pretax_income"

        specific_sum = sum(c.rate or 0.0 for k, c in mapped.items() if k != "other")
        residual = None
        if etr is not None:
            residual = etr - specific_sum
            mapped["other"] = TaxComponent(
                house_category="other",
                rate=residual,
                source_label="house residual (ETR − mapped specifics)",
                residual=True,
            )
        elif not mapped and pretax_income is None and income_tax_expense is None:
            return AnnualTaxReport(
                analysis_id=analysis_id,
                ticker=ticker,
                fiscal_year=fiscal_year,
                annual_report_source=source,
                reported_effective_tax_rate=None,
                mapped_components=[],
                residual_other=None,
                reconciliation_delta=None,
                reconciliation_status="ANNUAL_TAX_REQUIRED_INPUT_MISSING",
                source_locations=list(source_locations or []),
                confidence=0.0,
                summary=(
                    f"Tax FY {fiscal_year}: blocked — no ETR, components, or pretax/tax expense."
                ),
                cells_written=[],
                schedule_populated=False,
                pretax_income=pretax_income,
                income_tax_expense=income_tax_expense,
            )

        write_result = self._write_inputs(
            workbook_path,
            fiscal_year,
            mapped,
            etr=etr,
            income_tax_expense=income_tax_expense,
        )

        delta = None
        recon_status = "ok"
        if etr is not None and mapped:
            recon = sum(c.rate or 0.0 for c in mapped.values())
            delta = recon - etr
            if abs(delta) > 0.005:
                recon_status = "TAX_RECONCILIATION_REVIEW_REQUIRED"
        if not write_result["cells_written"]:
            recon_status = "ANNUAL_TAX_SCHEDULE_NOT_POPULATED"
        elif etr is not None and write_result.get("workbook_etr") is not None:
            if abs(float(write_result["workbook_etr"]) - etr) > _ETR_TOLERANCE:
                recon_status = "TAX_EFFECTIVE_RATE_RECONCILIATION_FAILED"

        return AnnualTaxReport(
            analysis_id=analysis_id,
            ticker=ticker,
            fiscal_year=fiscal_year,
            annual_report_source=source,
            reported_effective_tax_rate=etr,
            mapped_components=list(mapped.values()),
            residual_other=residual,
            reconciliation_delta=delta,
            reconciliation_status=recon_status,
            source_locations=list(source_locations or []),
            confidence=0.85 if recon_status == "ok" and write_result["cells_written"] else 0.4,
            summary=(
                f"Tax FY {fiscal_year}: ETR={etr}; residual Other={residual}; "
                f"recon delta={delta}; status={recon_status}; "
                f"cells_written={len(write_result['cells_written'])}."
            ),
            cells_written=write_result["cells_written"],
            schedule_populated=bool(write_result["cells_written"]),
            pretax_income=pretax_income,
            income_tax_expense=income_tax_expense,
        )

    def _write_inputs(
        self,
        path: Path,
        fy: str,
        mapped: dict[str, TaxComponent],
        *,
        etr: float | None,
        income_tax_expense: float | None,
    ) -> dict[str, Any]:
        wb = load_workbook(path, data_only=False)
        written: list[str] = []
        workbook_etr = None
        try:
            if "Inputs" not in wb.sheetnames:
                return {"cells_written": written, "workbook_etr": None}
            ws = wb["Inputs"]
            cols = detect_year_columns(ws, wb)
            if not any(k.startswith("FY") for k in cols):
                cols = detect_workbook_years(path)
            token = _fy_token(fy)
            col = cols.get(token)
            if col is None:
                fy_cols = {k: v for k, v in cols.items() if str(k).startswith("FY")}
                col = max(fy_cols.values()) if fy_cols else None
            if col is None:
                return {"cells_written": written, "workbook_etr": None}

            # Rate mode: Tax sheet formulas pull Inputs rates when E106=1.
            flag_cell = ws.cell(106, 5)  # E106
            if not (isinstance(flag_cell.value, str) and flag_cell.value.startswith("=")):
                if flag_cell.value != 1:
                    flag_cell.value = 1
                    written.append("Inputs!E106")

            house_for_row: dict[int, str] = {}
            for row in range(106, min(ws.max_row or 106, 120) + 1):
                label = str(ws.cell(row, 1).value or "").strip().lower()
                if not label or "tax table" in label:
                    continue
                house = self._inputs_tax_house(label)
                if house:
                    house_for_row[row] = house

            for row, house in house_for_row.items():
                cell = ws.cell(row, col)
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    continue
                if house == "total":
                    # Prefer sum of mapped rates (incl residual) as total ETR in rate mode.
                    value = etr
                    if value is None and mapped:
                        value = sum(c.rate or 0.0 for c in mapped.values())
                elif house in mapped and mapped[house].rate is not None:
                    value = mapped[house].rate
                else:
                    continue
                cell.value = float(value)
                written.append(f"Inputs!{get_column_letter(col)}{row}")
                if house == "total":
                    workbook_etr = float(value)

            # If no explicit total row was written, still record ETR for validation.
            if workbook_etr is None and etr is not None:
                workbook_etr = etr

            wb.save(path)
        finally:
            wb.close()
        return {
            "cells_written": written,
            "workbook_etr": workbook_etr,
            "income_tax_expense": income_tax_expense,
        }

    @staticmethod
    def _inputs_tax_house(label: str) -> str | None:
        lab = label.lower().strip()
        for house, keys in _INPUTS_TAX_ROWS.items():
            if any(k == lab or k in lab for k in keys):
                return house
        return None

    @staticmethod
    def _house_category(label: str) -> str:
        lab = label.lower()
        if "other" in lab and "credit" not in lab:
            return "other"
        for house in ("deferred", "credits", "state", "foreign"):
            keys = _LABEL_MAP[house]
            if any(k in lab for k in keys):
                return house
        for house, keys in _LABEL_MAP.items():
            if house == "other":
                continue
            if any(k in lab for k in keys):
                return house
        return "other"
