"""Autonomous R&D useful-life selection, lookback retrieval, and capitalization."""

from __future__ import annotations

import re

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
from services.hap_analysis_layout_service import HapAnalysisLayoutService
from services.sec_service import SecService

_PERMITTED = (1, 10)
_LIFE_CELLS = ("B8", "C8", "B2")
_EXTRA_LOOKBACK_ROW = 20

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
    (("industrial", "machinery", "manufacturing", "chemical", "irrigation", "agriculture", "farm"), 5, "industrial product development cycle"),
)


# Business-description evidence: phrases in the 10-K business section that show how long R&D benefits last.
# (group, life in years, reason, weighted phrases)
_BUSINESS_GROUPS: tuple[tuple[str, int, str, tuple[tuple[str, float], ...]], ...] = (
    ("pharma_biotech", 8, "drug and biologic development runs through clinical trials and regulatory approval, and benefits last through patent life",
     (("clinical trial", 3), ("fda approval", 3), ("new drug application", 3), ("drug candidate", 3), ("product candidate", 3),
      ("pipeline", 1), ("orphan drug", 2), ("biologic", 2), ("phase 3", 3), ("phase iii", 3), ("regulatory exclusivity", 2))),
    ("medical_devices", 6, "medical device development follows a multi-year design, validation and regulatory clearance cycle",
     (("510(k)", 3), ("premarket approval", 3), ("medical device", 2), ("clinical study", 2), ("clearance", 1), ("implant", 1))),
    ("aerospace_defense", 7, "aerospace and defense programs are developed over many years and earn returns over long program lives",
     (("aircraft", 1), ("defense contract", 2), ("military", 1), ("multi-year program", 3), ("airframe", 2), ("space systems", 2), ("long-term program", 2))),
    ("software_internet", 3, "software and internet products are rewritten or replaced within a few years",
     (("software-as-a-service", 3), ("saas", 3), ("subscription", 1), ("cloud", 1), ("software", 1), ("platform", 0.5),
      ("release", 0.5), ("developer", 1), ("mobile app", 2), ("end users", 0.5))),
    ("semiconductor_hardware", 4, "chip and hardware products follow a short design-win and product-generation cycle",
     (("semiconductor", 3), ("wafer", 3), ("foundry", 2), ("design win", 3), ("integrated circuit", 3), ("firmware", 1),
      ("hardware", 1), ("product generation", 2), ("fabless", 3))),
    ("ip_licensing", 5, "patent-licensing businesses earn returns through standards and technology generations, roughly five years each",
     (("licens", 1), ("patent portfolio", 3), ("standards", 1), ("royalt", 1.5), ("wireless", 1), ("standard-essential", 3))),
    ("consumer_retail", 3, "consumer and retail product cycles are short, so R&D benefits fade quickly",
     (("private label", 2), ("stores", 1), ("merchandise", 2), ("restaurants", 2), ("brands", 1), ("flavor", 1), ("packaged", 1), ("grocery", 2))),
    ("industrial_materials", 5, "industrial products and materials are developed over a few years and sold for many",
     (("engineered", 1), ("machinery", 2), ("manufactur", 0.5), ("chemical", 1), ("irrigation", 2), ("equipment", 0.5),
      ("industrial", 0.5), ("automotive", 1), ("steel", 1))),
)
_MIN_BUSINESS_SCORE = 12.0
_MIN_BUSINESS_MARGIN = 1.25


def _item1_window(text: str, max_chars: int = 90_000) -> str:
    """Business section of a 10-K (Item 1 up to Item 1A). Falls back to the opening of the filing."""
    starts = [m.start() for m in re.finditer(r"(?i)item\s*1\s*[\.\:\-\u2014]?\s*business", text)]
    # The table of contents also matches; the real section is the last start that leaves enough text before Item 1A.
    for start in reversed(starts):
        end_match = re.search(r"(?i)item\s*1a\s*[\.\:\-\u2014]?\s*risk", text[start + 500:])
        end = start + 500 + end_match.start() if end_match else start + max_chars
        if end - start > 3000:
            return text[start:min(end, start + max_chars)]
    return text[:max_chars]


def business_life_evidence(text: str | None) -> tuple[int, list[str], list[dict[str, Any]]] | None:
    """Pick an R&D useful life from the 10-K business text.

    Returns (life, evidence lines, ranked group scores) or None when the text does not clearly point to one business type.
    """
    if not text or len(text) < 3000:
        return None
    window = _item1_window(text).lower()
    scored: list[tuple[float, str, int, str, list[str]]] = []
    for group, life, reason, phrases in _BUSINESS_GROUPS:
        score = 0.0
        hits: list[str] = []
        for phrase, weight in phrases:
            n = window.count(phrase)
            if n:
                score += weight * min(n, 15)
                hits.append(f"{phrase} x{n}")
        scored.append((score, group, life, reason, hits))
    scored.sort(key=lambda item: item[0], reverse=True)
    ranking = [{"group": g, "score": round(sc, 1), "life": life} for sc, g, life, _r, _h in scored if sc > 0]
    top, second = scored[0], scored[1]
    if top[0] < _MIN_BUSINESS_SCORE:
        return None
    if second[0] > 0 and top[0] / second[0] < _MIN_BUSINESS_MARGIN:
        blended = int((top[2] * top[0] + second[2] * second[0]) / (top[0] + second[0]) + 0.5)
        evidence = [
            f"The 10-K business section mixes two activities: {top[1].replace('_', ' ')} ({', '.join(top[4][:4])}) and "
            f"{second[1].replace('_', ' ')} ({', '.join(second[4][:4])}). The life is blended to {blended} years."
        ]
        return blended, evidence, ranking
    evidence = [
        f"The 10-K business section points to {top[1].replace('_', ' ')}: {top[3]}. "
        f"Key phrases: {', '.join(top[4][:5])}."
    ]
    return top[2], evidence, ranking


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
        business_text: str | None = None,
        business_source: str | None = None,
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
            company_ev.append(
                f"R&D expense is separately disclosed in {len(positive)} displayed years. "
                "Useful life is based on the economic duration of R&D benefits, not on the dollar amount spent."
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
        business = business_life_evidence(business_text)
        if business is not None:
            selected = business[0]
            company_ev.extend(business[1])
            alternatives.insert(0, {"life": business[0], "reason": "10-K business description", "ranking": business[2][:4]})
            if industry_life != business[0]:
                industry_ev.append(
                    f"SIC/name evidence suggested {industry_life} years, but the business description is more specific and decided."
                )
        selected = max(_PERMITTED[0], min(_PERMITTED[1], int(selected)))

        confidence = 0.55
        if industry_reason and positive:
            confidence = 0.7
        if business is not None and positive:
            confidence = 0.8
        if not industry_reason and business is None:
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
        trail = list(prior_decision.audit_trail) if prior_decision else []
        if override is not None:
            if override < _PERMITTED[0] or override > _PERMITTED[1]:
                blocking.append("RD_USEFUL_LIFE_EVIDENCE_WEAK")
            else:
                selected = int(override)
                company_ev.append(f"Analyst override to {override} years: {override_reason or 'no reason supplied'}.")
            trail.append(
                {
                    "event": "ANALYST_OVERRIDE",
                    "original": original,
                    "override": selected,
                    "reason": override_reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        else:
            trail.append(
                {
                    "event": "AUTONOMOUS_AGENT_DECISION",
                    "life": selected,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

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
        if business is not None and business_source:
            citations.append(f"10-K Item 1 business description: {business_source}")
        if sec_manifest and sec_manifest.get("selected_filings"):
            citations.append(str(sec_manifest["selected_filings"][0].get("document_url") or "SEC 10-K"))

        rationale = (
            f"Selected {selected}-year straight-line R&D capitalization life. "
            f"{(business[1][0] if business else None) or industry_reason or 'Industry/SIC evidence was thin, so HAP used a 5-year industrial economic mid-point rather than deriving life from annual R&D spending.'} "
            "This is an AUTONOMOUS_AGENT_DECISION, not a measured accounting fact. "
            "An analyst may override it with a documented reason."
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
            audit_trail=trail,
            warning=(
                "R&D useful life is an autonomous agent decision. "
                "Override it if the economic life of the company's R&D differs from this selection."
            ),
            blocking=False,
            blocking_reasons=blocking,
            industry=industry,
            sic=str(sic) if sic else None,
        )

    @staticmethod
    def fetch_business_text(
        sec_manifest: dict[str, Any] | None, *, cache_dir: Path | None = None
    ) -> tuple[str | None, str | None]:
        """Latest 10-K in the manifest as plain text. Returns (text, url); (None, None) when it cannot be fetched."""
        from services.new_company_buyback_service import html_to_text
        from services.sec_service import SecServiceError

        if not sec_manifest:
            return None, None
        cik = str(sec_manifest.get("cik") or "")
        sec = SecService(cache_dir=cache_dir)
        for filing in sec_manifest.get("selected_filings") or []:
            if str(filing.get("filing_type") or "").upper() not in {"10-K", "10-K/A"}:
                continue
            url = filing.get("document_url")
            if not url or "Archives/edgar" not in str(url):
                continue
            try:
                html = sec.fetch_document_text(url, cik=cik or None, cache_name=f"10k_business_{filing.get('fiscal_year')}.htm")
            except (SecServiceError, OSError):
                continue
            return html_to_text(html), str(url)
        return None, None

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
            extra_needed = self._write_lookback_prewindow(
                wb, amounts, first, life, written
            )
            extended = self._extend_schedule(wb, fiscal_years, life, written)
            self._apply_selected_life_formulas(
                wb, fiscal_years, life, extra_needed, written
            )
            notes = self._write_decision_notes(wb, decision, lookback, written)
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
        warning = (
            "HAP ANALYSIS: R&D useful life is an autonomous agent decision. "
            "Override it if the economic life differs."
        )
        for addr in _LIFE_CELLS:
            cell = ws[addr]
            if isinstance(cell.value, str) and cell.value.startswith("="):
                continue
            cell.value = life
            written.append(f"R&D!{addr}")
            break
        # Visible warning — do not overwrite formulas.
        warn_cell = ws["A1"]
        existing = str(warn_cell.value or "")
        if not (isinstance(warn_cell.value, str) and warn_cell.value.startswith("=")):
            if "ANALYST WARNING" not in existing and "HAP ANALYSIS" not in existing:
                warn_cell.value = warning
                written.append("R&D!A1")

    @staticmethod
    def _write_decision_notes(wb, decision: RdUsefulLifeDecision, lookback: list[str], written: list[str]) -> list[str]:
        if "R&D" not in wb.sheetnames:
            return []
        override = (
            f"Analyst override to {decision.analyst_override} years ({decision.analyst_override_reason})."
            if decision.analyst_override is not None
            else "None — AUTONOMOUS_AGENT_DECISION"
        )
        lookback_txt = f"{lookback[0]}–{lookback[-1]}" if lookback else "—"
        rows = [
            ("R&D useful life (selected)", f"{decision.selected_useful_life} years"),
            ("Decision class", "ANALYST_OVERRIDE" if decision.analyst_override is not None else "AUTONOMOUS_AGENT_DECISION"),
            ("Source disclosures", "; ".join((decision.filing_citations or [])[:2]) or "—"),
            (
                "Economic rationale",
                decision.rationale or "; ".join((decision.industry_evidence or [])[:2]),
            ),
            (
                "Capitalization methodology",
                f"Straight-line remaining-life weights over {decision.selected_useful_life} years; "
                f"lookback {lookback_txt}. R&D!B8 is the designated useful-life input. "
                f"Asset (row 3) and amortization (row 4) formulas are generated from that life.",
            ),
            (
                "Workbook input cell",
                f"R&D!B8 = {decision.selected_useful_life} years "
                "(template life cell; not derived from annual R&D spend).",
            ),
            (
                "Dependent calculation / schedule",
                "R&D rows 3–4 (capitalized asset and amortization) for each displayed FY; "
                "Invested Capital Capitalized R&D references R&D row 3. Pre-window expense "
                f"values and extra lookback on R&D row {_EXTRA_LOOKBACK_ROW} feed the {decision.selected_useful_life}-year window.",
            ),
            (
                "Material uncertainty",
                "; ".join(decision.blocking_reasons) or "Optional analyst override is available.",
            ),
            ("Override", override),
        ]
        notes = HapAnalysisLayoutService().write_notes_section(wb["R&D"], rows)
        written.extend(notes)
        return notes

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
        return extended

    def _write_lookback_prewindow(
        self,
        wb,
        amounts: dict[str, RdYearAmount],
        first_displayed: str | None,
        life: int,
        written: list[str],
    ) -> int:
        if "R&D" not in wb.sheetnames or not first_displayed:
            return 0
        ows = wb["R&D"]
        pre = AnnualRdService._prewindow_expense_columns(ows)
        first_n = _fy_int(first_displayed)
        for i, col in enumerate(reversed(pre)):
            rec = amounts.get(_token(first_n - 1 - i))
            if rec is None or rec.amount is None:
                continue
            cell = ows.cell(2, col)
            if (isinstance(cell.value, str) and cell.value.startswith("=")) or cell.value in (None, ""):
                cell.value = float(rec.amount)
                written.append(f"R&D!{get_column_letter(col)}2")
        needed_pre = max(int(life) - 1, 0)
        extra_needed = max(0, needed_pre - len(pre))
        if extra_needed:
            label = ows.cell(_EXTRA_LOOKBACK_ROW, 1)
            if label.value in (None, "") or (
                isinstance(label.value, str) and "HAP" in str(label.value).upper()
            ):
                if not (isinstance(label.value, str) and label.value.startswith("=")):
                    label.value = "HAP R&D lookback (years before template pre-window)"
                    written.append(f"R&D!A{_EXTRA_LOOKBACK_ROW}")
            for i in range(extra_needed):
                fy_n = first_n - len(pre) - extra_needed + i
                rec = amounts.get(_token(fy_n))
                if rec is None or rec.amount is None:
                    continue
                cell = ows.cell(_EXTRA_LOOKBACK_ROW, 2 + i)
                if isinstance(cell.value, str) and cell.value.startswith("="):
                    continue
                cell.value = float(rec.amount)
                written.append(f"R&D!{get_column_letter(2 + i)}{_EXTRA_LOOKBACK_ROW}")
        return extra_needed

    @staticmethod
    def _is_life_adaptable(val: Any) -> bool:
        if val in (None, ""):
            return True
        if not isinstance(val, str) or not val.startswith("="):
            return False
        compact = val.replace(" ", "").upper()
        if "B8" in compact:
            return True
        if "/3" in compact or "2/3" in compact:
            return True
        return False

    @staticmethod
    def _expense_window_addrs(col: int, life: int, pre_cols: list[int], extra_needed: int) -> list[str]:
        addrs: list[str] = []
        min_col = min(pre_cols) if pre_cols else 2
        c = col
        while len(addrs) < life and c >= min_col:
            addrs.append(f"{get_column_letter(c)}2")
            c -= 1
        need = life - len(addrs)
        for i in range(need):
            extra_index = extra_needed - 1 - i
            if extra_index < 0:
                break
            addrs.append(f"{get_column_letter(2 + extra_index)}{_EXTRA_LOOKBACK_ROW}")
        return addrs

    @staticmethod
    def _asset_formula(addrs: list[str], life: int) -> str:
        parts: list[str] = []
        for i, addr in enumerate(addrs):
            remaining = life - i
            if remaining <= 0:
                break
            if remaining == life:
                parts.append(addr)
            else:
                parts.append(f"{addr}*{remaining}/{life}")
        if not parts:
            return "=0"
        return "=IFERROR(" + "+".join(parts) + ",0)"

    @staticmethod
    def _amort_formula(addrs: list[str], life: int) -> str:
        if not addrs:
            return "=0"
        return f"=IFERROR(({'+'.join(addrs)})/{life},0)"

    def _apply_selected_life_formulas(
        self,
        wb,
        fiscal_years: list[str],
        life: int,
        extra_needed: int,
        written: list[str],
    ) -> None:
        if "R&D" not in wb.sheetnames or "Inputs" not in wb.sheetnames or life < 1:
            return
        ows = wb["R&D"]
        inp_cols = detect_year_columns(wb["Inputs"], wb)
        rd_cols = {fy: c + 2 for fy, c in inp_cols.items() if str(fy).startswith("FY")}
        pre = AnnualRdService._prewindow_expense_columns(ows)
        for fy in fiscal_years:
            col = rd_cols.get(fy)
            if not col:
                continue
            addrs = self._expense_window_addrs(col, life, pre, extra_needed)
            asset_cell = ows.cell(3, col)
            amort_cell = ows.cell(4, col)
            if self._is_life_adaptable(asset_cell.value):
                asset_cell.value = self._asset_formula(addrs, life)
                written.append(f"R&D!{get_column_letter(col)}3")
            if self._is_life_adaptable(amort_cell.value):
                amort_cell.value = self._amort_formula(addrs, life)
                written.append(f"R&D!{get_column_letter(col)}4")

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
        sic = (
            (sec_manifest or {}).get("sic")
            or (sec_manifest or {}).get("sicCode")
            or (company_facts or {}).get("sic")
        )
        name = (sec_manifest or {}).get("company_name") or (company_facts or {}).get("entityName")
        sic_desc = (sec_manifest or {}).get("sic_description") or (sec_manifest or {}).get("sicDescription")
        industry = sic_desc or name
        blob = " ".join(str(x) for x in (name, sic, sic_desc, industry) if x)
        return blob or None, sic

    @staticmethod
    def _industry_life(blob: str) -> tuple[int, str | None]:
        for keys, life, reason in _INDUSTRY_LIFE:
            if any(k in blob for k in keys):
                return life, reason
        sic_digits = "".join(ch for ch in blob if ch.isdigit())
        if len(sic_digits) >= 2:
            sic_map = {
                "28": (8, "SIC 28xx pharmaceutical/chemical patent and regulatory cycle"),
                "35": (5, "SIC 35xx industrial machinery development cycle"),
                "36": (4, "SIC 36xx electronics/hardware product cycle"),
                "37": (5, "SIC 37xx industrial equipment development cycle"),
                "53": (3, "SIC 53xx general merchandise retail; limited R&D"),
                "56": (3, "SIC 56xx apparel retail; limited R&D"),
                "57": (3, "SIC 57xx home furnishings retail; limited R&D"),
                "59": (3, "SIC 59xx catalog/e-commerce retail; limited R&D"),
                "73": (3, "SIC 73xx software/services technology cycle"),
            }
            mapped = sic_map.get(sic_digits[:2])
            if mapped:
                return mapped
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
