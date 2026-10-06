"""Annual Update primary deliverables: fiscal-year Excel name and Annual Update.docx."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.annual_update import (
    AnnualAnalystJudgmentReport,
    AnnualDeliverablesReport,
    AnnualExpectedReturnReport,
    AnnualOutputGateReport,
    AnnualPerformanceReport,
    AnnualResearchReport,
    AnnualValuationOutputs,
    DISCLOSE_DISTORTED_BASE,
    YoYMetric,
)
from services.annual_period_service import detect_year_columns
from services.annual_valuation_extract_service import AnnualValuationExtractService
from services.deliverable_naming import email_deliverable_name, excel_deliverable_name
from services.deliverable_text import dedupe, headline_lines
from services.email_draft_service import EmailDraftService, file_name
from services.workbook_values import ensure_calculated


def _is_dated(label: Any) -> bool:
    """A usable 'as of' label contains a date or period; template placeholders such as 'CRF as-of / current' do not."""
    return isinstance(label, str) and any(ch.isdigit() for ch in label)


def _fmt(v, *, pct: bool = False) -> str:
    if v is None:
        return "unavailable"
    if pct:
        # Accept either fraction or already-percent magnitudes.
        x = float(v)
        if abs(x) <= 1.5:
            x *= 100.0
        return f"{x:.2f}%"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


def _pct_chg(a, b) -> float | None:
    if a is None or b in (None, 0):
        return None
    return a / b - 1.0


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


class AnnualDeliverablesService:
    def produce(
        self,
        *,
        analysis_id: str,
        ticker: str,
        fiscal_year: int,
        completed_workbook_path: Path,
        output_dir: Path,
        performance: AnnualPerformanceReport,
        research: AnnualResearchReport | None = None,
        judgment: AnnualAnalystJudgmentReport | None = None,
        expected_return: AnnualExpectedReturnReport | None = None,
        gate: AnnualOutputGateReport | None = None,
    ) -> AnnualDeliverablesReport:
        excel_name = excel_deliverable_name(fiscal_year=fiscal_year, ticker=ticker, analysis_type="Annual Update")
        output_dir.mkdir(parents=True, exist_ok=True)
        excel_path = output_dir / excel_name
        shutil.copy2(completed_workbook_path, excel_path)
        ensure_calculated(excel_path, analysis_id=analysis_id, ticker=ticker, fiscal_year=fiscal_year)
        email = EmailDraftService().produce_safe(
            analysis_type="annual_update",
            ticker=ticker,
            workbook_path=excel_path,
            output_dir=output_dir,
            base_name=email_deliverable_name(fiscal_year=fiscal_year, ticker=ticker),
        )
        return AnnualDeliverablesReport(
            analysis_id=analysis_id,
            ticker=ticker,
            fiscal_year=fiscal_year,
            excel_filename=excel_name,
            excel_path=str(excel_path),
            email_filename=file_name(email["text_path"]),
            email_path=email["text_path"],
            eml_path=email["eml_path"],
            summary=f"Deliverables: {excel_name}; {file_name(email['text_path'])}",
        )

    def build_performance(
        self,
        *,
        analysis_id: str,
        ticker: str,
        fiscal_year: int,
        workbook_path: Path,
        research: AnnualResearchReport | None,
        valuation: AnnualValuationOutputs | None = None,
        gate: AnnualOutputGateReport | None = None,
    ) -> AnnualPerformanceReport:
        valuation = valuation or AnnualValuationExtractService().extract(workbook_path)
        yoy = self._read_yoy(workbook_path, fiscal_year)
        highlights = self._build_highlights(fiscal_year, yoy, valuation)
        mgmt = list(research.management_explanations[:4]) if research else []
        risks = list((research.hap_interpretations[:2] if research else []))
        risks.append("See 10-K risk factors; HAP does not fabricate unidentified risks.")

        quality = self._quality_view(yoy, valuation)
        attractiveness = self._attractiveness(valuation)
        conclusion = self._conclusion(quality, attractiveness, gate)

        open_issues: list[str] = []
        if gate:
            open_issues.extend(gate.blockers)
            open_issues.extend(gate.warnings[:6])
        open_issues.extend(valuation.warnings)

        return AnnualPerformanceReport(
            analysis_id=analysis_id,
            ticker=ticker,
            fiscal_year=fiscal_year,
            year_highlights=highlights,
            yoy=yoy,
            current_price=valuation.current_price,
            current_pe10=valuation.current_pe10,
            current_max_buy=valuation.max_buy,
            current_margin_of_safety=valuation.enterprise_mos,
            current_expected_return=valuation.expected_annual_return,
            current_expected_return_with_div=valuation.expected_return_with_dividends,
            current_graham_entry=valuation.graham_target_return_entry_price,
            graham_intrinsic=valuation.current_graham_intrinsic_value,
            company_value_per_share=valuation.company_value_per_share,
            owner_earnings_growth=valuation.owner_earnings_growth,
            roic_wacc_current=valuation.roic_wacc,
            roce_current=valuation.roce,
            investment_conclusion=conclusion,
            company_quality=quality,
            valuation_attractiveness=attractiveness,
            confidence=0.7 if not (gate and gate.blockers) else 0.35,
            open_issues=open_issues,
            valuation=valuation,
            management_commentary=mgmt,
            material_risks=risks,
            summary=f"Annual performance snapshot for {ticker} FY{fiscal_year}.",
        )

    def _read_yoy(self, path: Path, fiscal_year: int) -> list[YoYMetric]:
        wb = load_workbook(path, data_only=False)
        out: list[YoYMetric] = []
        try:
            if "Income - GAAP" not in wb.sheetnames:
                return out
            ws = wb["Income - GAAP"]
            cols = detect_year_columns(ws, wb)
            cy = cols.get(f"FY{fiscal_year}")
            py = cols.get(f"FY{fiscal_year - 1}")
            if not cy or not py:
                return out
            wanted = [
                ("Revenue", ("revenue",), "USD_millions"),
                ("Gross Profit", ("gross profit",), "USD_millions"),
                ("Operating Income", ("operating income", "operating income (loss)"), "USD_millions"),
                ("Pretax Income", ("pretax income", "income before tax"), "USD_millions"),
                ("Net Income", ("net income", "net income (loss)"), "USD_millions"),
                ("Diluted EPS", ("diluted eps", "earnings per share diluted", "eps"), "USD"),
                ("R&D Expense", ("research & development", "research and development"), "USD_millions"),
                ("Income Tax Expense", ("income tax expense",), "USD_millions"),
            ]
            for name, aliases, units in wanted:
                for row in range(1, min(ws.max_row or 1, 90) + 1):
                    lab = str(ws.cell(row, 1).value or "").strip().lower()
                    if not lab:
                        continue
                    if any(a == lab or lab.endswith(a) or a in lab for a in aliases):
                        # Prefer exact-ish match; skip indented detail when parent exists
                        if lab.startswith("+") or lab.startswith("-"):
                            if name not in {"R&D Expense"}:
                                continue
                        cur = _num(ws.cell(row, cy).value)
                        prior = _num(ws.cell(row, py).value)
                        if cur is None and prior is None:
                            break
                        out.append(
                            YoYMetric(
                                metric=name,
                                current=cur,
                                prior=prior,
                                pct_change=_pct_chg(cur, prior),
                                units=units,
                            )
                        )
                        break
            if "Cash Flow - Standardized" in wb.sheetnames:
                cf = wb["Cash Flow - Standardized"]
                ccols = detect_year_columns(cf, wb)
                ccy, cpy = ccols.get(f"FY{fiscal_year}"), ccols.get(f"FY{fiscal_year - 1}")
                if ccy and cpy:
                    for row in range(1, min(cf.max_row or 1, 60) + 1):
                        lab = str(cf.cell(row, 1).value or "").strip().lower()
                        if "operating" in lab and "cash" in lab:
                            cur, prior = _num(cf.cell(row, ccy).value), _num(cf.cell(row, cpy).value)
                            out.append(
                                YoYMetric(
                                    metric="Cash from Operations",
                                    current=cur,
                                    prior=prior,
                                    pct_change=_pct_chg(cur, prior),
                                    units="USD_millions",
                                )
                            )
                            break
        finally:
            wb.close()
        return out

    @staticmethod
    def _build_highlights(
        fiscal_year: int, yoy: list[YoYMetric], valuation: AnnualValuationOutputs
    ) -> list[str]:
        highlights: list[str] = []
        by_name = {m.metric: m for m in yoy}
        for key in ("Revenue", "Operating Income", "Net Income", "Diluted EPS", "Cash from Operations"):
            m = by_name.get(key)
            if not m or m.pct_change is None:
                continue
            direction = "rose" if m.pct_change >= 0 else "fell"
            highlights.append(
                f"FY{fiscal_year} {key} {direction} {_fmt(m.pct_change, pct=True)} "
                f"to {_fmt(m.current)} from {_fmt(m.prior)}."
            )
        if valuation.current_pe10 is not None:
            asof = f" as of {valuation.current_pe10_as_of}" if _is_dated(valuation.current_pe10_as_of) else ""
            highlights.append(f"Current PE10 is {_fmt(valuation.current_pe10)}x{asof}.")
        if valuation.pe10_fiscal_year is not None:
            asof = f" as of {valuation.pe10_fiscal_as_of}" if _is_dated(valuation.pe10_fiscal_as_of) else ""
            label = valuation.pe10_fiscal_year_label or "fiscal-year"
            highlights.append(f"{label} closing PE10 is {_fmt(valuation.pe10_fiscal_year)}x{asof}.")
        if valuation.expected_annual_return is not None:
            highlights.append(
                f"Expected annual return (Expected Returns!E14) at the current price is "
                f"{_fmt(valuation.expected_annual_return, pct=True)}."
            )
        if not highlights:
            highlights.append(
                f"Fiscal {fiscal_year} operating results were taken from the completed HAP workbook."
            )
        return highlights[:8]

    @staticmethod
    def _quality_view(yoy: list[YoYMetric], valuation: AnnualValuationOutputs) -> str:
        rev = next((m for m in yoy if m.metric == "Revenue"), None)
        ni = next((m for m in yoy if m.metric == "Net Income"), None)
        if rev and rev.pct_change is not None and ni and ni.pct_change is not None:
            if rev.pct_change > 0 and ni.pct_change > 0:
                return "Improving operating trajectory versus the prior year."
            if ni.pct_change < -0.2:
                return "Profitability weakened versus the prior year; quality needs review."
        if valuation.owner_earnings_growth is not None and valuation.owner_earnings_growth < -0.5:
            return "Owner-earnings signal is unstable; do not treat quality as established."
        return "Operating quality is mixed/indeterminate from available YoY evidence."

    @staticmethod
    def _attractiveness(valuation: AnnualValuationOutputs) -> str:
        # Prefer workbook Expected Returns!E14; never treat Inputs!B69 as E14.
        er = valuation.expected_annual_return
        if er is not None:
            x = er * 100 if abs(er) <= 1.5 else er
            if x >= 12:
                return "Valuation appears attractive on Expected Returns!E14."
            if x >= 8:
                return "Valuation is borderline on Expected Returns!E14; wait for a wider margin."
            return "Valuation looks expensive / low expected return on Expected Returns!E14."
        if valuation.enterprise_mos is not None:
            mos = valuation.enterprise_mos
            if mos >= 0.25:
                return "Valuation appears attractive on Graham margin-of-safety (25%+)."
            if mos >= 0.10:
                return "Valuation is near entry on Graham margin-of-safety."
            return "Valuation looks expensive on Graham margin-of-safety."
        return (
            "Valuation attractiveness indeterminate — Expected Returns!E14 not available "
            "(workbook recalculation required)."
        )

    @staticmethod
    def _conclusion(quality: str, attractiveness: str, gate: AnnualOutputGateReport | None) -> str:
        if gate and gate.blockers:
            return (
                "NEEDS REVIEW — no final investment recommendation. "
                "Blocking validation issues (including any incomplete workbook recalculation) "
                "prevent authorization of the investment conclusion. "
                f"Quality: {quality} Attractiveness: {attractiveness}"
            )
        return f"{attractiveness} Company quality: {quality}"
