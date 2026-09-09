"""Annual Update primary deliverables: {YEAR} {TICKER} FA.xlsx and Annual Update.docx."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt, RGBColor
from openpyxl import load_workbook

from models.annual_update import (
    AnnualAnalystJudgmentReport,
    AnnualDeliverablesReport,
    AnnualExpectedReturnReport,
    AnnualOutputGateReport,
    AnnualPerformanceReport,
    AnnualResearchReport,
    AnnualValuationOutputs,
    YoYMetric,
)
from services.annual_period_service import detect_year_columns
from services.annual_valuation_extract_service import AnnualValuationExtractService


def excel_word_names(year: int, ticker: str) -> tuple[str, str]:
    t = ticker.upper()
    return f"{year} {t} FA.xlsx", f"{year} {t} Annual Update.docx"


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
        excel_name, word_name = excel_word_names(fiscal_year, ticker)
        output_dir.mkdir(parents=True, exist_ok=True)
        excel_path = output_dir / excel_name
        word_path = output_dir / word_name
        shutil.copy2(completed_workbook_path, excel_path)
        self._write_word(
            word_path,
            ticker,
            fiscal_year,
            performance,
            research,
            judgment,
            expected_return,
            gate,
        )
        return AnnualDeliverablesReport(
            analysis_id=analysis_id,
            ticker=ticker,
            fiscal_year=fiscal_year,
            excel_filename=excel_name,
            excel_path=str(excel_path),
            word_filename=word_name,
            word_path=str(word_path),
            summary=f"Deliverables: {excel_name}; {word_name}",
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
            asof = f" as of {valuation.current_pe10_as_of}" if valuation.current_pe10_as_of else ""
            highlights.append(f"Current PE10 is {_fmt(valuation.current_pe10)}x{asof}.")
        if valuation.pe10_fiscal_year is not None:
            asof = f" as of {valuation.pe10_fiscal_as_of}" if valuation.pe10_fiscal_as_of else ""
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

    def _write_word(
        self,
        path: Path,
        ticker: str,
        year: int,
        perf: AnnualPerformanceReport,
        research: AnnualResearchReport | None,
        judgment: AnnualAnalystJudgmentReport | None = None,
        expected_return: AnnualExpectedReturnReport | None = None,
        gate: AnnualOutputGateReport | None = None,
    ) -> None:
        doc = Document()
        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)
        title = doc.add_heading(f"{year} {ticker} Annual Update", level=0)
        title.runs[0].font.color.rgb = RGBColor(0x1F, 0x3A, 0x5F)

        doc.add_heading("1. Executive Investment Conclusion", level=1)
        if gate and gate.blockers:
            doc.add_paragraph(
                "Final investment recommendation: NOT AUTHORIZED. "
                "Workbook recalculation and/or output gates failed; this document is diagnostic only."
            )
        doc.add_paragraph(perf.investment_conclusion or "Conclusion unavailable.")
        doc.add_paragraph(f"Company quality: {perf.company_quality or 'unavailable'}")
        doc.add_paragraph(f"Valuation attractiveness: {perf.valuation_attractiveness or 'unavailable'}")
        if gate and gate.blockers:
            doc.add_paragraph(
                "Status: NEEDS REVIEW. Blocking issues: " + "; ".join(gate.blockers[:5])
            )
        else:
            doc.add_paragraph(f"Confidence: {_fmt(perf.confidence)}")

        doc.add_heading("2. Fiscal-Year Highlights", level=1)
        for h in perf.year_highlights:
            if h.lower().startswith("sec ") and "filed" in h.lower():
                continue  # never list filing dates as business highlights
            doc.add_paragraph(h, style="List Bullet")

        doc.add_heading(f"3. FY{year} versus FY{year - 1}", level=1)
        if perf.yoy:
            table = doc.add_table(rows=1, cols=4)
            hdr = table.rows[0].cells
            hdr[0].text, hdr[1].text, hdr[2].text, hdr[3].text = "Metric", "Current", "Prior", "% chg"
            for row in perf.yoy:
                cells = table.add_row().cells
                cells[0].text = row.metric
                cells[1].text = _fmt(row.current)
                cells[2].text = _fmt(row.prior)
                cells[3].text = _fmt(row.pct_change, pct=True)
        else:
            doc.add_paragraph(
                "YoY operating metrics were not available from the Income statement columns."
            )

        if research and research.management_explanations:
            doc.add_heading("Management Explanation", level=2)
            for m in research.management_explanations:
                doc.add_paragraph(m)

        doc.add_heading("4. Economic Returns", level=1)
        v = perf.valuation
        if v:
            doc.add_paragraph(
                f"NOPAT: {_fmt(v.nopat)}; Invested capital: {_fmt(v.invested_capital)}; "
                f"ROIC: {_fmt(v.roic, pct=True)}."
            )
        doc.add_paragraph(
            f"ROIC−WACC: current {_fmt(perf.roic_wacc_current, pct=True)}; "
            f"prior {_fmt(perf.roic_wacc_prior, pct=True)}; "
            f"10-year average {_fmt(perf.roic_wacc_10y, pct=True)}."
        )
        doc.add_paragraph(
            f"ROCE: current {_fmt(perf.roce_current, pct=True)}; "
            f"prior {_fmt(perf.roce_prior, pct=True)}; "
            f"10-year average {_fmt(perf.roce_10y, pct=True)}."
        )
        doc.add_paragraph(
            "Economic-return formulas remain workbook-driven; values above appear only when "
            "Excel-recalculated cached results are available."
        )

        doc.add_heading("5. Business Quality and Risks", level=1)
        doc.add_paragraph(perf.company_quality or "Quality assessment unavailable.")
        for r in perf.material_risks[:5]:
            doc.add_paragraph(r, style="List Bullet")
        if research and research.earnings_call_status == "EARNINGS_CALL_SOURCE_UNAVAILABLE":
            doc.add_paragraph("Earnings-call transcript: unavailable.")

        doc.add_heading("6. Current Data and Valuation", level=1)
        doc.add_paragraph(f"Current Price: {_fmt(perf.current_price)}")
        v = perf.valuation
        if v and v.pe10_fiscal_year is not None:
            doc.add_paragraph(
                f"FY closing PE10 ({v.pe10_fiscal_year_label or 'fiscal'}): "
                f"{_fmt(v.pe10_fiscal_year)}x"
                + (f" as of {v.pe10_fiscal_as_of}" if v.pe10_fiscal_as_of else "")
            )
        doc.add_paragraph(
            f"Current PE10: {_fmt(perf.current_pe10)}"
            + (
                f" as of {v.current_pe10_as_of}"
                if v and v.current_pe10_as_of
                else ""
            )
        )
        doc.add_paragraph(f"Maximum Buy Price: {_fmt(perf.current_max_buy)}")
        doc.add_paragraph(
            f"Expected Annual Return (Expected Returns!E14): "
            f"{_fmt(perf.current_expected_return, pct=True)}"
        )
        doc.add_paragraph(
            f"Expected Return including dividends (Expected Returns!F14): "
            f"{_fmt(perf.current_expected_return_with_div, pct=True)}"
        )
        if v and v.bloomberg_expected_return_at_current_price is not None:
            doc.add_paragraph(
                f"Bloomberg CRF Expected Return @ Current Price (Inputs!B69 — distinct metric): "
                f"{_fmt(v.bloomberg_expected_return_at_current_price, pct=True)}"
            )
        doc.add_paragraph(f"Enterprise value / company value per share: {_fmt(perf.company_value_per_share)}")
        doc.add_paragraph(f"Enterprise margin of safety: {_fmt(perf.current_margin_of_safety, pct=True)}")
        if v:
            doc.add_paragraph(
                f"Current Graham intrinsic value: {_fmt(v.current_graham_intrinsic_value)}"
            )
            doc.add_paragraph(
                f"Graham margin-of-safety entry price (25% MOS purchase price): "
                f"{_fmt(v.graham_margin_of_safety_entry_price)}"
            )
            doc.add_paragraph(
                f"Graham target-return entry price "
                f"({_fmt(v.graham_target_annualized_return, pct=True)} over "
                f"{v.graham_projection_horizon_years or 7} years): "
                f"{_fmt(v.graham_target_return_entry_price)}"
            )
            doc.add_paragraph(
                f"Graham expected annualized return: "
                f"{_fmt(v.graham_expected_annualized_return, pct=True)}"
            )
        else:
            doc.add_paragraph(f"Graham intrinsic value: {_fmt(perf.graham_intrinsic)}")
            doc.add_paragraph(f"Graham entry price: {_fmt(perf.current_graham_entry)}")

        doc.add_heading("7. Method Comparison", level=1)
        if v:
            doc.add_paragraph(
                f"Expected Returns!E14/F14: {_fmt(v.expected_annual_return, pct=True)} / "
                f"{_fmt(v.expected_return_with_dividends, pct=True)}. "
                f"Inputs!B69 Bloomberg CRF Expected Return @ Current Price is a separate "
                f"proprietary metric ({_fmt(v.bloomberg_expected_return_at_current_price, pct=True)}) "
                f"and is not a substitute for E14."
            )
            doc.add_paragraph(
                f"Owner-earnings / Enterprise Value: company value/share {_fmt(v.company_value_per_share)}; "
                f"OE growth {_fmt(v.owner_earnings_growth, pct=True)} "
                f"(annualized {_fmt(v.owner_earnings_growth_annualized, pct=True)})."
            )
            doc.add_paragraph(
                f"Graham: intrinsic {_fmt(v.current_graham_intrinsic_value)}; "
                f"MOS entry {_fmt(v.graham_margin_of_safety_entry_price)}; "
                f"target-return entry {_fmt(v.graham_target_return_entry_price)}; "
                f"expected {_fmt(v.graham_expected_annualized_return, pct=True)}; "
                f"target {_fmt(v.graham_target_annualized_return, pct=True)}."
            )
            if v.warnings:
                doc.add_paragraph("Valuation warnings:")
                for w in v.warnings:
                    doc.add_paragraph(w, style="List Bullet")
            else:
                doc.add_paragraph(
                    "Methods are compared using workbook-extracted figures; "
                    "disagreement requires judgment rather than silent averaging."
                )
        else:
            doc.add_paragraph("Valuation outputs were not extracted.")

        doc.add_heading("8. Analyst Judgment", level=1)
        if expected_return:
            growth = expected_return.selected_growth_rate
            reasonableness = expected_return.reasonableness
            if growth is None and reasonableness and "reasonable" in reasonableness.lower():
                reasonableness = "reviewed — numerical assumption unavailable"
            doc.add_paragraph(
                f"Expected Return judgment: {reasonableness} — "
                f"{expected_return.selected_methodology} at {_fmt(growth, pct=True)}. "
                f"{expected_return.rationale}"
            )
        if judgment and judgment.graham_eps_growth:
            g = judgment.graham_eps_growth
            label = g.reasonableness_classification or "reviewed"
            if g.selected_value is None and label and "reasonable" in label.lower():
                label = "reviewed — value unavailable"
            doc.add_paragraph(
                f"Graham EPS growth: {label} — {g.change_type}: "
                f"{_fmt(g.original_value, pct=True)} → {_fmt(g.selected_value, pct=True)}. {g.rationale}"
            )
        if judgment and judgment.owner_earnings_growth:
            o = judgment.owner_earnings_growth
            label = o.reasonableness_classification or "reviewed"
            if o.selected_value is None and label and (
                "reasonable" in label.lower() or "sustainable" in label.lower()
            ):
                label = "reviewed — unknown growth not treated as sustainable"
            doc.add_paragraph(
                f"Owner Earnings growth: {label} — {o.change_type}: "
                f"{_fmt(o.original_value, pct=True)} → {_fmt(o.selected_value, pct=True)}. {o.rationale}"
            )

        doc.add_heading("9. Validation and Open Issues", level=1)
        if perf.open_issues:
            for issue in perf.open_issues[:10]:
                doc.add_paragraph(issue, style="List Bullet")
        else:
            doc.add_paragraph("No material blocking validation issues recorded.")

        if research and research.research_questions:
            doc.add_heading("Research Trail", level=2)
            for q in research.research_questions[:6]:
                if q.concept == "tax_effective_rate" and gate and "ANNUAL_TAX_SCHEDULE_NOT_POPULATED" in gate.blockers:
                    status = "unresolved — ETR researched but tax schedule not written"
                elif q.unsuccessful:
                    status = "unresolved"
                else:
                    status = f"resolved via {q.source_selected}"
                doc.add_paragraph(f"{q.concept}: {q.question} — {status}", style="List Bullet")

        doc.add_heading("10. Sources and Provenance", level=1)
        if research:
            for s in research.sources[:8]:
                line = f"{s.source_kind}: {s.title}"
                if s.url and "sec.gov" not in (s.url or ""):
                    line += f" — {s.url}"
                doc.add_paragraph(line, style="List Bullet")
            sec_filings = [s for s in research.sources if s.url and "sec.gov" in s.url]
            if sec_filings:
                doc.add_paragraph(
                    f"SEC EDGAR filings referenced: {len(sec_filings)} (details in provenance artifacts)."
                )
        if perf.valuation and perf.valuation.sources:
            doc.add_paragraph("Workbook extraction sources:")
            for k, v in list(perf.valuation.sources.items())[:8]:
                doc.add_paragraph(f"{k}: {v}", style="List Bullet")
        doc.save(path)
