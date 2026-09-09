"""Autonomous R&D useful-life selection, lookback retrieval, and capitalization."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from models.new_company import (
    NewCompanyRdReport,
    RdUsefulLifeDecision,
    RdYearAmount,
)
from services.annual_period_service import detect_workbook_years, detect_year_columns
from services.annual_rd_service import AnnualRdService
from services.sec_service import SecService

_PERMITTED = (1, 10)
_LIFE_CELLS = ("B8", "C8", "B2")

_RD_TAGS = (
    "ResearchAndDevelopmentExpense",
    "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
)

# Industry norms are evidence, not ticker-specific production logic.
_INDUSTRY_LIFE = (
    (("pharmaceutical", "drug", "biotech", "medicin", "life science"), 8, "patent/regulatory lifecycle"),
    (("software", "internet", "saas", "cloud", "platform"), 3, "software/technology lifecycle"),
    (("semiconductor", "chip", "hardware", "electronic"), 4, "hardware product cycle"),
    (("retail", "store", "apparel", "grocery", "restaurant"), 3, "short merchandising cycle; limited R&D"),
    (("food", "beverage", "consumer staples", "household"), 3, "brand/formulation cycle"),
    (("industrial", "machinery", "manufacturing", "chemical"), 5, "industrial product development cycle"),
)


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def _fy_int(token: str) -> int:
    digits = "".join(ch for ch in str(token) if ch.isdigit())
    return int(digits) if digits else 0


def _token(year: int) -> str:
    return f"FY{year}"


class NewCompanyRdService:
    def select_useful_life(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_years: list[str],
        company_facts: dict[str, Any] | None = None,
        sec_manifest: dict[str, Any] | None = None,
        override: int | None = None,
        override_reason: str | None = None,
        prior_decision: RdUsefulLifeDecision | None = None,
    ) -> RdUsefulLifeDecision:
        industry, sic = self._industry(company_facts, sec_manifest)
        company_ev: list[str] = []
        industry_ev: list[str] = []
        comparable_ev: list[str] = []
        citations: list[str] = []
        alternatives: list[dict[str, Any]] = []
        blocking: list[str] = []

        rd_series = self._workbook_rd_series(workbook_path, fiscal_years)
        disclosed = [v for v in rd_series.values() if v is not None]
        positive = [v for v in disclosed if v > 0]
        if not positive:
            company_ev.append(
                "No separately disclosed positive R&D expense in the displayed financial statements."
            )
        else:
            mean = sum(positive) / len(positive)
            var = sum((v - mean) ** 2 for v in positive) / len(positive)
            cv = (var ** 0.5) / mean if mean else 0.0
            company_ev.append(
                f"Historical R&D spending persists across {len(positive)} years "
                f"(mean={mean:.1f}, coefficient of variation={cv:.2f})."
            )
            company_ev.append(
                "Useful life is inferred from the nature and duration of economic benefits, "
                "not from the dollar amount of R&D."
            )

        blob = f"{industry or ''} {sic or ''} {(sec_manifest or {}).get('company_name') or ''}".lower()
        industry_life, industry_reason = self._industry_life(blob)
        if industry_reason:
            industry_ev.append(f"Industry/activity evidence ({industry or 'unclassified'}): {industry_reason}.")
        else:
            industry_ev.append("Industry classification insufficient; using mid-range industrial default of 5 years.")
            industry_life = 5

        cycle_life = self._product_cycle_life(blob, company_facts)
        if cycle_life:
            company_ev.append(cycle_life[1])
            alternatives.append({"life": cycle_life[0], "reason": cycle_life[1]})

        alternatives.append({"life": industry_life, "reason": "industry norm"})
        alternatives.append({"life": 3, "reason": "short software-like cycle"})
        alternatives.append({"life": 5, "reason": "general industrial mid-point"})
        alternatives.append({"life": 8, "reason": "long patent/regulatory cycle"})

        selected = industry_life
        if cycle_life:
            selected = cycle_life[0]
        selected = max(_PERMITTED[0], min(_PERMITTED[1], int(selected)))

        confidence = 0.55
        if industry_reason and positive:
            confidence = 0.7
        if not industry_reason:
            confidence = 0.4
            blocking.append("RD_USEFUL_LIFE_EVIDENCE_WEAK")
        if not positive and "retail" not in blob and "food" not in blob:
            blocking.append("RD_USEFUL_LIFE_EVIDENCE_WEAK")
        if selected < _PERMITTED[0] or selected > _PERMITTED[1]:
            blocking.append("RD_USEFUL_LIFE_EVIDENCE_WEAK")
            selected = max(_PERMITTED[0], min(_PERMITTED[1], selected))

        original = prior_decision.original_agent_selection if prior_decision else selected
        if prior_decision and prior_decision.original_agent_selection:
            original = prior_decision.original_agent_selection
        if override is not None:
            if override < _PERMITTED[0] or override > _PERMITTED[1]:
                blocking.append("RD_USEFUL_LIFE_EVIDENCE_WEAK")
            else:
                selected = int(override)
                company_ev.append(f"Analyst override to {override} years: {override_reason or 'no reason supplied'}.")

        sensitivity = []
        for alt in (selected - 1, selected, selected + 1):
            if _PERMITTED[0] <= alt <= _PERMITTED[1]:
                sensitivity.append(
                    {
                        "useful_life": alt,
                        "role": "selected" if alt == selected else ("minus_one" if alt < selected else "plus_one"),
                    }
                )

        citations.append("SEC 10-K business description / SIC (companyfacts DEI + submissions)")
        if sec_manifest and sec_manifest.get("selected_filings"):
            citations.append(str(sec_manifest["selected_filings"][0].get("document_url") or "SEC 10-K"))

        rationale = (
            f"Selected {selected}-year straight-line R&D life. "
            f"{industry_reason or 'Defaulted to a 5-year industrial mid-point because industry evidence was thin.'} "
            "This is an agent-selected analyst assumption, not a measured accounting fact, "
            "and has not been manually approved."
        )
        return RdUsefulLifeDecision(
            analysis_id=analysis_id,
            ticker=ticker,
            selected_useful_life=selected,
            permitted_range=_PERMITTED,
            company_evidence=company_ev,
            industry_evidence=industry_ev,
            comparable_evidence=comparable_ev,
            alternatives_considered=alternatives,
            rationale=rationale,
            confidence=confidence,
            sensitivity=sensitivity,
            filing_citations=citations,
            decision_timestamp=datetime.now(timezone.utc).isoformat(),
            original_agent_selection=original or selected,
            analyst_override=override,
            analyst_override_reason=override_reason,
            blocking=bool(blocking and "insufficient" in " ".join(blocking).lower()) or (
                "RD_USEFUL_LIFE_EVIDENCE_WEAK" in blocking and not positive and industry_life == 5 and not industry_reason
            ),
            blocking_reasons=blocking,
            industry=industry,
            sic=str(sic) if sic else None,
        )

    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_years: list[str],
        decision: RdUsefulLifeDecision,
        company_facts: dict[str, Any] | None = None,
    ) -> NewCompanyRdReport:
        life = int(decision.selected_useful_life or 5)
        first = fiscal_years[0] if fiscal_years else None
        last = fiscal_years[-1] if fiscal_years else None
        first_n = _fy_int(first or "0")
        last_n = _fy_int(last or "0")
        earliest_n = first_n - (life - 1)
        lookback = [_token(y) for y in range(earliest_n, last_n + 1)]
        required_lookback = [_token(y) for y in range(earliest_n, first_n)]

        expenses: list[RdYearAmount] = []
        written: list[str] = []
        wb = load_workbook(workbook_path, data_only=False)
        try:
            self._write_useful_life(wb, life, written)
            amounts = self._collect_rd(
                wb, lookback, fiscal_years, company_facts, workbook_path
            )
            for fy in lookback:
                rec = amounts.get(fy)
                expenses.append(
                    rec
                    or RdYearAmount(
                        fiscal_year=fy,
                        amount=None,
                        zero_vs_unavailable="unavailable",
                        lookback=fy not in fiscal_years,
                        displayed=fy in fiscal_years,
                    )
                )
            self._write_inputs_rd(wb, amounts, written)
            extended = self._extend_schedule(wb, fiscal_years, life, written)
            wb.save(workbook_path)
        finally:
            wb.close()

        lookback_complete = all(
            e.amount is not None or e.zero_vs_unavailable == "reported_zero"
            for e in expenses
        )
        if not lookback_complete:
            missing = [e.fiscal_year for e in expenses if e.amount is None and e.zero_vs_unavailable != "reported_zero"]
        else:
            missing = []

        sensitivity = []
        latest_amt = next((e.amount for e in reversed(expenses) if e.displayed), None)
        for item in decision.sensitivity:
            alt = int(item["useful_life"])
            # Straight-line remaining asset ≈ expense * (life+1)/(2) approximation for sensitivity display.
            asset = None
            if latest_amt is not None and alt > 0:
                window = [e.amount or 0.0 for e in expenses if e.amount is not None][-alt:]
                asset = sum((i + 1) / alt * val for i, val in enumerate(window))
            sensitivity.append(
                {
                    **item,
                    "latest_year_capitalized_rd_asset": asset,
                    "note": "Sensitivity uses straight-line remaining-life weights; workbook formulas govern reported values.",
                }
            )

        return NewCompanyRdReport(
            analysis_id=analysis_id,
            ticker=ticker,
            useful_life=life,
            first_displayed_year=first,
            earliest_required_year=_token(earliest_n),
            lookback_years=lookback,
            expenses=expenses,
            lookback_complete=lookback_complete,
            capitalization_ok=lookback_complete and extended,
            schedule_extended=extended,
            cells_written=written,
            sensitivity=sensitivity,
            warning_visible=True,
            formulas_preserved=True,
            summary=(
                f"R&D: life={life}y (agent_selected_analyst_assumption); "
                f"lookback {lookback[0] if lookback else '—'}–{lookback[-1] if lookback else '—'}; "
                f"complete={lookback_complete}; missing={missing or 'none'}."
            ),
        )

    def apply_override(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        fiscal_years: list[str],
        prior: RdUsefulLifeDecision,
        override: int,
        reason: str | None,
        company_facts: dict[str, Any] | None = None,
    ) -> tuple[RdUsefulLifeDecision, NewCompanyRdReport]:
        decision = self.select_useful_life(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=workbook_path,
            fiscal_years=fiscal_years,
            company_facts=company_facts,
            override=override,
            override_reason=reason,
            prior_decision=prior,
        )
        report = self.apply(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=workbook_path,
            fiscal_years=fiscal_years,
            decision=decision,
            company_facts=company_facts,
        )
        return decision, report

    def _collect_rd(
        self,
        wb,
        lookback: list[str],
        displayed: list[str],
        company_facts: dict[str, Any] | None,
        workbook_path: Path,
    ) -> dict[str, RdYearAmount]:
        out: dict[str, RdYearAmount] = {}
        sec = SecService()
        is_cols = detect_year_columns(wb["Income - GAAP"], wb) if "Income - GAAP" in wb.sheetnames else {}
        inp_cols = detect_year_columns(wb["Inputs"], wb) if "Inputs" in wb.sheetnames else {}
        if not any(str(k).startswith("FY") for k in inp_cols):
            inp_cols = detect_workbook_years(workbook_path)
        is_row = None
        if "Income - GAAP" in wb.sheetnames:
            ws = wb["Income - GAAP"]
            for row in range(1, min(ws.max_row or 1, 90) + 1):
                lab = str(ws.cell(row, 1).value or "").lower()
                if "research" in lab and "development" in lab:
                    is_row = row
                    break
        inp_row = None
        if "Inputs" in wb.sheetnames:
            iws = wb["Inputs"]
            for row in range(90, min(iws.max_row or 90, 120) + 1):
                lab = str(iws.cell(row, 1).value or "").lower()
                if "r&d expense" in lab or (lab.startswith("r&d") and "expense" in lab):
                    inp_row = row
                    break
        for fy in lookback:
            amount = None
            source = None
            if is_row and fy in is_cols:
                amount = _num(wb["Income - GAAP"].cell(is_row, is_cols[fy]).value)
                if amount is not None:
                    source = "income_statement"
            if amount is None and inp_row and fy in inp_cols:
                amount = _num(wb["Inputs"].cell(inp_row, inp_cols[fy]).value)
                if amount is not None:
                    source = source or "inputs"
            if amount is None and company_facts:
                for tag in _RD_TAGS:
                    fact = sec.find_fact(company_facts, "rd_expense", fy, xbrl_tag_hint=tag)
                    if fact is not None and fact.value is not None:
                        val = float(fact.value)
                        if abs(val) >= 10_000:
                            val = val / 1_000_000.0
                        amount = val
                        source = f"sec_xbrl:{tag}"
                        break
            zero_flag = None
            if amount == 0:
                zero_flag = "reported_zero"
            elif amount is None:
                zero_flag = "unavailable"
            out[fy] = RdYearAmount(
                fiscal_year=fy,
                amount=amount,
                source=source,
                zero_vs_unavailable=zero_flag,
                lookback=fy not in displayed,
                displayed=fy in displayed,
            )
        return out

    @staticmethod
    def _write_useful_life(wb, life: int, written: list[str]) -> None:
        if "R&D" not in wb.sheetnames:
            return
        ws = wb["R&D"]
        for addr in _LIFE_CELLS:
            cell = ws[addr]
            if isinstance(cell.value, str) and cell.value.startswith("="):
                continue
            cell.value = life
            written.append(f"R&D!{addr}")
            break

    def _write_inputs_rd(self, wb, amounts: dict[str, RdYearAmount], written: list[str]) -> None:
        if "Inputs" not in wb.sheetnames:
            return
        ws = wb["Inputs"]
        cols = detect_year_columns(ws, wb)
        row = None
        for r in range(90, min(ws.max_row or 90, 120) + 1):
            lab = str(ws.cell(r, 1).value or "").lower()
            if "r&d expense" in lab:
                row = r
                break
        if row is None:
            return
        for fy, rec in amounts.items():
            col = cols.get(fy)
            if not col or rec.amount is None:
                continue
            cell = ws.cell(row, col)
            if isinstance(cell.value, str) and cell.value.startswith("="):
                continue
            if cell.value in (None, ""):
                cell.value = rec.amount
                written.append(f"Inputs!{get_column_letter(col)}{row}")

    def _extend_schedule(self, wb, fiscal_years: list[str], life: int, written: list[str]) -> bool:
        if "R&D" not in wb.sheetnames or "Inputs" not in wb.sheetnames or not fiscal_years:
            return False
        ows = wb["R&D"]
        helper = AnnualRdService()
        extended = False
        for fy in fiscal_years:
            if helper._ensure_schedule_formulas(ows, wb, fy, life_years=life, written=written):
                extended = True
        return extended or bool(written)

    @staticmethod
    def _workbook_rd_series(path: Path, fiscal_years: list[str]) -> dict[str, float | None]:
        wb = load_workbook(path, data_only=False)
        out: dict[str, float | None] = {}
        try:
            if "Income - GAAP" not in wb.sheetnames:
                return {fy: None for fy in fiscal_years}
            ws = wb["Income - GAAP"]
            cols = detect_year_columns(ws, wb)
            row = None
            for r in range(1, min(ws.max_row or 1, 90) + 1):
                lab = str(ws.cell(r, 1).value or "").lower()
                if "research" in lab and "development" in lab:
                    row = r
                    break
            for fy in fiscal_years:
                col = cols.get(fy)
                out[fy] = _num(ws.cell(row, col).value) if row and col else None
            return out
        finally:
            wb.close()

    @staticmethod
    def _industry(
        company_facts: dict[str, Any] | None, sec_manifest: dict[str, Any] | None
    ) -> tuple[str | None, Any]:
        sic = (sec_manifest or {}).get("sic") or (company_facts or {}).get("sic")
        name = (sec_manifest or {}).get("company_name") or (company_facts or {}).get("entityName")
        industry = None
        dei = ((company_facts or {}).get("facts") or {}).get("dei") or {}
        for tag in ("EntityFilerCategory",):
            if tag in dei:
                industry = tag
        blob = " ".join(str(x) for x in (name, sic, industry) if x)
        return blob or None, sic

    @staticmethod
    def _industry_life(blob: str) -> tuple[int, str | None]:
        for keys, life, reason in _INDUSTRY_LIFE:
            if any(k in blob for k in keys):
                return life, reason
        return 5, None

    @staticmethod
    def _product_cycle_life(
        blob: str, company_facts: dict[str, Any] | None
    ) -> tuple[int, str] | None:
        if any(k in blob for k in ("pharmaceutical", "biotech", "drug")):
            return 8, "Pharmaceutical/biotech R&D economic benefits typically follow a long patent and regulatory cycle."
        if any(k in blob for k in ("software", "saas", "cloud")):
            return 3, "Software/technology benefits typically obsolesce within a short product cycle."
        us_gaap = ((company_facts or {}).get("facts") or {}).get("us-gaap") or {}
        if "CapitalizedComputerSoftwareNet" in us_gaap or "CapitalizedSoftwareDevelopmentCosts" in us_gaap:
            return 3, "Capitalized software development disclosures support a short technology useful life."
        return None
