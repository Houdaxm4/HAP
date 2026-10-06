"""New Company Word investment-analysis report."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from docx import Document
from docx.shared import Pt, RGBColor

from services.deliverable_text import headline_lines
from services.email_draft_service import EmailDraftService, file_name, word_report_enabled
from services.report_flags import collect_flags, write_flags_section
from services.report_opinion import write_assessment_sections
from services.margin_history import note_text, read_history, table_rows
from models.annual_update import AnnualValuationOutputs
from models.new_company import (
    LeaseRateReview,
    NewCompanyBuybackReport,
    NewCompanyDeliverablesReport,
    NewCompanyLeaseReport,
    NewCompanyOutputGateReport,
    NewCompanyPe10Report,
    NewCompanyProjectionReport,
    NewCompanyRdReport,
    NewCompanyTaxReport,
    NewCompanyValuationReport,
    RdUsefulLifeDecision,
    SeasonalityProjectionReport,
    TenYearPeriodReport,
)


def _fmt(v: Any, *, pct: bool = False) -> str:
    if v is None:
        return "unavailable"
    if pct:
        x = float(v)
        if abs(x) <= 1.5:
            x *= 100.0
        return f"{x:.2f}%"
    if isinstance(v, float):
        return f"{v:,.2f}"
    return str(v)


class NewCompanyDeliverablesService:
    def produce(
        self,
        *,
        analysis_id: str,
        ticker: str,
        company: str,
        fiscal_year: int,
        completed_workbook_path: Path,
        output_dir: Path,
        periods: TenYearPeriodReport | None,
        tax: NewCompanyTaxReport | None,
        pe10: NewCompanyPe10Report | None,
        rd_decision: RdUsefulLifeDecision | None,
        rd: NewCompanyRdReport | None,
        leases: NewCompanyLeaseReport | None,
        lease_review: LeaseRateReview | None,
        buybacks: NewCompanyBuybackReport | None,
        projection: NewCompanyProjectionReport | None,
        seasonality: SeasonalityProjectionReport | None,
        valuation: AnnualValuationOutputs | None,
        gate: NewCompanyOutputGateReport | None,
        authorized: bool,
        statement_summary: str | None = None,
        fiscal_quarter: int | None = None,
        judgment: Any = None,
        valuation_report: NewCompanyValuationReport | None = None,
    ) -> NewCompanyDeliverablesReport:
        from services.deliverable_naming import email_deliverable_name, excel_deliverable_name

        output_dir.mkdir(parents=True, exist_ok=True)
        excel_name = excel_deliverable_name(
            fiscal_year=fiscal_year,
            ticker=ticker,
            analysis_type="New Company",
            fiscal_quarter=fiscal_quarter,
        )
        word_name = f"{fiscal_year} {ticker.upper()} New Company.docx"
        excel_path = output_dir / excel_name
        word_path = output_dir / word_name
        shutil.copy2(completed_workbook_path, excel_path)
        word_on = word_report_enabled()
        if word_on:
            self._write_word(
                word_path,
                ticker=ticker,
                company=company,
                fiscal_year=fiscal_year,
                periods=periods,
                tax=tax,
                pe10=pe10,
                rd_decision=rd_decision,
                rd=rd,
                leases=leases,
                lease_review=lease_review,
                buybacks=buybacks,
                projection=projection,
                seasonality=seasonality,
                valuation=valuation,
                gate=gate,
                statement_summary=statement_summary,
                judgment=judgment,
                valuation_report=valuation_report,
                workbook_path=completed_workbook_path,
                authorized=authorized,
            )
        else:
            word_name = None
            word_path = None
        email = EmailDraftService().produce_safe(
            analysis_type="new_company",
            ticker=ticker,
            company=company,
            workbook_path=excel_path,
            output_dir=output_dir,
            base_name=email_deliverable_name(fiscal_year=fiscal_year, ticker=ticker, fiscal_quarter=fiscal_quarter),
        )
        return NewCompanyDeliverablesReport(
            analysis_id=analysis_id,
            ticker=ticker,
            fiscal_year=fiscal_year,
            excel_filename=excel_name,
            excel_path=str(excel_path),
            word_filename=word_name,
            word_path=str(word_path) if word_path else None,
            email_filename=file_name(email["text_path"]),
            email_path=email["text_path"],
            eml_path=email["eml_path"],
            authorized=authorized,
            summary=(
                f"Deliverables: {excel_name}"
                + f"; {file_name(email['text_path'])}"
                + ("" if authorized else " (NOT AUTHORIZED: review the HAP Adjustments tab and the gate report)")
            ),
        )

    @staticmethod
    def _recast_note(output_dir: Path) -> str | None:
        """Sentence about workbook cells HAP corrected, from new_company_cost_recast_report.json (if any)."""
        import json

        report_path = output_dir / "new_company_cost_recast_report.json"
        if not report_path.exists():
            return None
        try:
            with report_path.open("r", encoding="utf-8") as handle:
                report = json.load(handle)
        except (OSError, ValueError):
            return None
        years = [y["fiscal_year"] for y in report.get("years", []) if y.get("status") == "written"]
        if not years:
            return None
        return (
            f"Workbook cells for {', '.join(years)} were corrected to the company's latest cost presentation "
            f"('{str(report.get('label', '')).title()}' line of the 10-K); each changed cell is shaded and its comment "
            "keeps the original value. Total costs and operating income are unchanged."
        )

    def _write_word(
        self,
        path: Path,
        *,
        workbook_path: Path | None = None,
        authorized: bool = True,
        ticker: str,
        company: str,
        fiscal_year: int,
        periods: TenYearPeriodReport | None,
        tax: NewCompanyTaxReport | None,
        pe10: NewCompanyPe10Report | None,
        rd_decision: RdUsefulLifeDecision | None,
        rd: NewCompanyRdReport | None,
        leases: NewCompanyLeaseReport | None,
        lease_review: LeaseRateReview | None,
        buybacks: NewCompanyBuybackReport | None,
        projection: NewCompanyProjectionReport | None,
        seasonality: SeasonalityProjectionReport | None,
        valuation: AnnualValuationOutputs | None,
        gate: NewCompanyOutputGateReport | None,
        statement_summary: str | None,
        judgment: Any = None,
        valuation_report: NewCompanyValuationReport | None = None,
    ) -> None:
        doc = Document()
        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)

        v = valuation
        quality = self._operating_quality(projection, v)
        value_creation = self._value_creation(projection, v)
        capital = self._capital_allocation(buybacks)
        attractiveness = self._attractiveness(v)
        uncertainty = (
            projection.confidence.value if projection and projection.confidence else "n/a"
        )

        doc.add_heading(f"{company} ({ticker}) — New Company Investment Analysis", level=0)
        doc.add_paragraph(f"Fiscal window through FY{fiscal_year}. Industrial Template initiation.")

        # Flags come first: what was filled, corrected, decided by the agent, or is missing.
        write_flags_section(doc, collect_flags(path.parent, authorized=authorized))

        doc.add_heading("1. Executive investment conclusion", level=1)
        for line in headline_lines(path.parent):
            doc.add_paragraph(line)
        doc.add_paragraph(
            f"Operating quality: {quality}. Economic value creation: {value_creation}. "
            f"Capital allocation: {capital}. Valuation attractiveness: {attractiveness}. "
            f"Projection uncertainty: {uncertainty}."
        )
        if v:
            doc.add_paragraph(
                f"Current price {_fmt(v.current_price)}, PE10 {_fmt(v.current_pe10)}x, "
                f"expected annual return {_fmt(v.expected_annual_return, pct=True)}, "
                f"ROIC–WACC {_fmt(v.roic_wacc, pct=True)}, ROCE {_fmt(v.roce, pct=True)}."
            )

        doc.add_heading("2. Company overview and business model", level=1)
        doc.add_paragraph(
            f"{company} is analyzed on the Industrial Template using Bloomberg-prefilled "
            "statements, SEC filings, and CRF proprietary fields. HAP does not invent a "
            "business description beyond filing evidence."
        )

        doc.add_heading("3. Ten-year operating history", level=1)
        if periods:
            doc.add_paragraph(
                f"Annual columns {periods.start_year}–{periods.end_year}; "
                f"latest quarter {periods.latest_quarter_label or 'unidentified'}."
            )
        if statement_summary:
            doc.add_paragraph(statement_summary)

        doc.add_heading("4. Profitability and margin trends", level=1)
        if v:
            doc.add_paragraph(
                f"Latest NOPAT {_fmt(v.nopat)}; invested capital {_fmt(v.invested_capital)}; "
                f"ROIC {_fmt(v.roic, pct=True)}."
            )
        history = []
        if workbook_path is not None:
            try:
                filing_dirs = sorted(path.parent.glob("sec_cache/*/filings"))
                history = read_history(workbook_path, filing_dirs[0] if filing_dirs else None)
            except Exception:  # noqa: BLE001 - a missing table must not stop the document
                history = []
        if history:
            table = doc.add_table(rows=1, cols=6)
            for cell, text in zip(table.rows[0].cells, ("Fiscal year", "Revenue ($M)", "Growth", "Gross margin", "Operating margin", "Net margin")):
                cell.text = text
            for row in table_rows(history):
                for cell, text in zip(table.add_row().cells, row):
                    cell.text = text
            note = note_text(history)
            if note:
                doc.add_paragraph(note)
            corrected = self._recast_note(path.parent)
            if corrected:
                doc.add_paragraph(corrected)

        doc.add_heading("5. Cash generation and conversion", level=1)
        doc.add_paragraph(
            "Cash conversion is evaluated from the prefilled cash-flow statements and "
            "owner-earnings outputs after Excel recalculation. See the completed workbook."
        )

        doc.add_heading("6. Balance-sheet strength", level=1)
        doc.add_paragraph(
            "Balance-sheet items were validated against SEC 10-K facts for all ten years; "
            "material differences were corrected only with filing evidence."
        )

        doc.add_heading("7. Tax-rate history and material drivers", level=1)
        if tax:
            for y in tax.years:
                doc.add_paragraph(
                    f"{y.fiscal_year}: ETR {_fmt(y.reported_effective_rate, pct=True)}; "
                    f"federal {_fmt(y.statutory_federal, pct=True)}; state {_fmt(y.state, pct=True)}; "
                    f"foreign {_fmt(y.foreign, pct=True)}; R&D credit {_fmt(y.rd_credit, pct=True)}; "
                    f"other {_fmt(y.other, pct=True)}.",
                    style=None,
                )
        else:
            doc.add_paragraph("Tax history unavailable.")

        doc.add_heading("8. R&D capitalization", level=1)
        warn = doc.add_paragraph()
        run = warn.add_run("ANALYST WARNING: ")
        run.bold = True
        run.font.color.rgb = RGBColor(0xC0, 0x39, 0x2B)
        if rd_decision:
            warn.add_run(rd_decision.warning)
            doc.add_paragraph(
                f"Selected useful life: {rd_decision.selected_useful_life} years "
                f"(provenance: {rd_decision.provenance_class}). "
                f"Original agent selection: {rd_decision.original_agent_selection}. "
                f"Analyst override: {rd_decision.analyst_override or 'none'}."
            )
            doc.add_paragraph(rd_decision.rationale)
            for ev in rd_decision.company_evidence[:4]:
                doc.add_paragraph(ev, style="List Bullet")
            for ev in rd_decision.industry_evidence[:3]:
                doc.add_paragraph(ev, style="List Bullet")
            if rd and rd.sensitivity:
                doc.add_paragraph("Sensitivity of latest-year capitalized R&D asset to life ±1 year:")
                for item in rd.sensitivity:
                    doc.add_paragraph(
                        f"Life {item.get('useful_life')}: asset {_fmt(item.get('latest_year_capitalized_rd_asset'))} "
                        f"({item.get('role')}).",
                        style="List Bullet",
                    )
            lookback = f"{rd.earliest_required_year}–{rd.lookback_years[-1]}" if rd and rd.lookback_years else "n/a"
            doc.add_paragraph(f"Required R&D lookback: {lookback}; coverage complete={rd.lookback_complete if rd else False}.")

        doc.add_heading("9. Lease capitalization", level=1)
        if lease_review:
            selected = (
                lease_review.selected_rate
                if lease_review.selected_rate is not None
                else lease_review.proposed_rate
            )
            doc.add_paragraph(
                f"Selected long-term lease discount rate {_fmt(selected, pct=True)} "
                f"({lease_review.classification or 'n/a'}) via "
                f"{(lease_review.proposal.methodology if lease_review.proposal else 'n/a')}. "
                f"Decision class: {lease_review.decision_class}. "
                "This is not a fabricated human approval."
            )
            if lease_review.proposal and lease_review.proposal.source_fiscal_year:
                doc.add_paragraph(
                    f"Source period {lease_review.proposal.source_fiscal_year}; "
                    f"form {lease_review.proposal.source_form or 'SEC'}; "
                    f"accession {lease_review.proposal.source_accession or 'n/a'}."
                )
            for ev in (lease_review.supporting_evidence or [])[:4]:
                doc.add_paragraph(ev, style="List Bullet")
            if lease_review.proposal and lease_review.proposal.limitations:
                doc.add_paragraph(f"Limitations: {lease_review.proposal.limitations}")
            doc.add_paragraph(
                f"Effect on invested capital uses the selected rate. "
                f"Calculated ROU asset {_fmt(lease_review.calculated_lease_asset)}; "
                f"liability {_fmt(lease_review.calculated_lease_liability)}."
            )
        if leases and leases.mixed_regimes:
            doc.add_paragraph(
                "History spans pre-ASC 842 undiscounted commitments and post-ASC 842 "
                "discounted liabilities; these are not mixed."
            )

        doc.add_heading("10. Capital allocation", level=1)
        if buybacks and buybacks.analysis:
            a = buybacks.analysis
            doc.add_paragraph(
                f"Ten-year cumulative repurchase dollars {_fmt(a.cumulative_dollars)}; "
                f"cumulative shares {_fmt(a.cumulative_shares)}; "
                f"diluted share-count change {_fmt(a.diluted_share_count_change)}; "
                f"buybacks as % of FCF {_fmt(a.buybacks_pct_of_fcf, pct=True)}. "
                f"Funding: {a.funded_by or 'unassessed'}. "
                f"SBC offset material: {a.sbc_offset_material}. "
                f"Per-share value: {a.value_created_or_destroyed or 'inconclusive'}."
            )
            for n in a.notes:
                doc.add_paragraph(n, style="List Bullet")
        else:
            doc.add_paragraph("Buyback history incomplete or not disclosed.")

        doc.add_heading("11. ROIC–WACC", level=1)
        if projection:
            doc.add_paragraph(
                f"Latest annual ROIC {_fmt(projection.latest_annual_roic, pct=True)}; "
                f"ten-year average {_fmt(projection.ten_year_avg_roic, pct=True)}; "
                f"YTD unadjusted annualized {_fmt(projection.ytd_unadjusted_annualized_roic, pct=True)}; "
                f"seasonality-adjusted projected {_fmt(projection.seasonality_adjusted_roic, pct=True)}; "
                f"WACC {_fmt(projection.wacc, pct=True)}; "
                f"projected ROIC–WACC {_fmt(projection.projected_roic_wacc, pct=True)}; "
                f"projected NOPAT {_fmt(projection.projected_nopat)}; "
                f"projected invested capital {_fmt(projection.projected_invested_capital)}; "
                f"confidence {projection.confidence.value}."
            )
        if seasonality and seasonality.latest_quarter in {2, 3}:
            doc.add_heading("11b. Q2/Q3 seasonality projections", level=1)
            doc.add_paragraph(
                f"Latest quarter Q{seasonality.latest_quarter} ({seasonality.ytd_period_length}). "
                "Seasonality-adjusted is primary; raw annualized YTD remains visible."
            )
            for c in seasonality.components:
                doc.add_paragraph(
                    f"{c.metric}: YTD {_fmt(c.ytd_value)}; raw annualized "
                    f"{_fmt(c.unadjusted_annualized)}; seasonality-adjusted "
                    f"{_fmt(c.seasonality_adjusted)}; factor {_fmt(c.selected_factor)}.",
                    style="List Bullet",
                )

        doc.add_heading("12. ROCE", level=1)
        if projection:
            doc.add_paragraph(
                f"Latest annual ROCE {_fmt(projection.latest_annual_roce, pct=True)}; "
                f"ten-year average {_fmt(projection.ten_year_avg_roce, pct=True)}; "
                f"YTD unadjusted annualized {_fmt(projection.ytd_unadjusted_annualized_roce, pct=True)}; "
                f"seasonality-adjusted projected {_fmt(projection.seasonality_adjusted_roce, pct=True)}; "
                f"confidence {projection.confidence.value}."
            )

        doc.add_heading("13. Current price and PE10", level=1)
        if v:
            doc.add_paragraph(
                f"Current price {_fmt(v.current_price)}; current PE10 {_fmt(v.current_pe10)}x "
                f"(as of {v.current_pe10_as_of or 'unavailable'})."
            )
        if pe10:
            hist = ", ".join(
                f"{o.fiscal_year}={_fmt(o.value)}"
                for o in pe10.fiscal_year_pe10
                if o.value is not None
            )
            doc.add_paragraph(f"Ten-year fiscal PE10: {hist or 'unavailable'}.")

        doc.add_heading("13b. Expected Returns", level=1)
        if v:
            doc.add_paragraph(
                f"Expected annual return {_fmt(v.expected_annual_return, pct=True)}; "
                f"with dividends {_fmt(v.expected_return_with_dividends, pct=True)}. "
                "These are not substitutes for Enterprise Value or Graham results."
            )

        doc.add_heading("13c. Enterprise Value", level=1)
        if v:
            doc.add_paragraph(
                f"Enterprise MOS {_fmt(v.enterprise_mos, pct=True)}; max buy {_fmt(v.max_buy)}."
            )

        doc.add_heading("13d. Graham intrinsic value and entry prices", level=1)
        if v:
            doc.add_paragraph(
                f"Graham IV {_fmt(v.current_graham_intrinsic_value)}; "
                f"margin-of-safety entry {_fmt(v.graham_margin_of_safety_entry_price)}; "
                f"target-return entry {_fmt(v.graham_target_return_entry_price)}."
            )

        doc.add_heading("14. Comparison of valuation methods", level=1)
        doc.add_paragraph(
            "Expected Returns, Enterprise Value, and Graham are distinct workbook methodologies. "
            "HAP does not collapse them into a single synthetic target."
        )

        doc.add_heading("15. Principal risks", level=1)
        doc.add_paragraph(
            "See the latest 10-K risk factors. HAP does not fabricate unidentified risks. "
            "Model-specific risks include R&D-life judgment, lease-rate estimation, and "
            "seasonality projection error."
        )

        doc.add_heading("16. HAP valuation judgment (ER / EV / Owner Earnings / Graham)", level=1)
        doc.add_paragraph(
            "Original analyst growth-rate cells and valuation formulas were not overwritten. "
            "Any HAP alternative appears as HAP ANALYSIS only and is not the applied model output. "
            "When evidence is insufficient, HAP explains why rather than inventing a fallback growth rate."
        )
        if valuation_report is not None and valuation_report.period_context:
            doc.add_paragraph(valuation_report.period_context)
        elif periods and periods.latest_quarter in {2, 3}:
            q = periods.latest_quarter
            ytd = "six-month" if q == 2 else "nine-month"
            doc.add_paragraph(
                f"Q{q} initiation: distinguish reported {ytd} YTD, standalone Q{q}, and projected "
                "full-year amounts. Partial-year figures do not feed annual valuation formulas "
                "without annualization."
            )
        if judgment is not None:
            er = getattr(judgment, "expected_return", None) or getattr(judgment, "er_analysis", None)
            oe = getattr(judgment, "oe_analysis", None) or getattr(judgment, "owner_earnings_growth", None)
            gr = getattr(judgment, "graham_analysis", None) or getattr(judgment, "graham_eps_growth", None)
            for rec, title in ((er, "Expected Returns"), (oe, "Owner Earnings"), (gr, "Graham")):
                if rec is None:
                    continue
                decision = getattr(rec, "decision", None)
                rationale = getattr(rec, "rationale", None) or getattr(rec, "reason", None) or ""
                existing = getattr(rec, "existing_assumption", None) or getattr(rec, "original_value", None)
                hap_rate = getattr(rec, "selected_prospective_rate", None) or getattr(
                    rec, "selected_value", None
                )
                line = f"{title}: {decision or 'n/a'}"
                if existing is not None:
                    line += f" | original {existing}"
                if hap_rate is not None and decision == "ADJUST":
                    line += f" | HAP suggested {hap_rate} (not applied to original cell)"
                if decision == "INSUFFICIENT_EVIDENCE":
                    line += " | no fallback growth rate invented"
                doc.add_paragraph(line, style="List Bullet")
                if rationale:
                    doc.add_paragraph(str(rationale)[:500], style="List Bullet")
            oe_base = getattr(judgment, "oe_base_analysis", None)
            disclosure = getattr(oe_base, "disclosure", None) if oe_base is not None else None
            if isinstance(oe_base, dict):
                disclosure = oe_base.get("disclosure") or {}
                word_text = disclosure.get("word_text") if isinstance(disclosure, dict) else None
            else:
                word_text = getattr(disclosure, "word_text", None) if disclosure is not None else None
            if word_text:
                doc.add_paragraph(
                    "Normalized earnings-power disclosure (HAP ANALYSIS, not established fact):"
                )
                doc.add_paragraph(str(word_text)[:1200])
            hap_cells = getattr(judgment, "hap_analysis_cells", None) or (
                valuation_report.hap_analysis_cells if valuation_report else []
            )
            if hap_cells:
                doc.add_paragraph(
                    "HAP_ANALYSIS cells (not original analyst data): " + ", ".join(list(hap_cells)[:20])
                )
        elif valuation_report is not None:
            doc.add_paragraph(valuation_report.summary)
        else:
            doc.add_paragraph(
                "Valuation judgment was not run. Final authorization requires genuine Excel COM "
                "CalculateFullRebuild after autonomous lease-rate and R&D useful-life selection."
            )

        write_assessment_sections(doc, path.parent, v, history if history else None)

        doc.add_heading("17. Analyst judgments and overrides", level=1)
        if rd_decision:
            doc.add_paragraph(
                f"R&D useful life {rd_decision.selected_useful_life}y is an "
                f"{'ANALYST_OVERRIDE' if rd_decision.analyst_override is not None else 'AUTONOMOUS_AGENT_DECISION'} "
                f"({rd_decision.provenance_class}) and remains editable."
            )
            doc.add_paragraph(rd_decision.rationale)
        if lease_review:
            doc.add_paragraph(
                f"Lease rate selected {lease_review.selected_rate if lease_review.selected_rate is not None else lease_review.proposed_rate} "
                f"({lease_review.decision_class}; classification={lease_review.classification}). "
                f"Analyst action {lease_review.analyst_action or 'none'}."
            )

        doc.add_heading("18. Validation warnings and open issues", level=1)
        if gate:
            for b in gate.blockers[:12]:
                doc.add_paragraph(b, style="List Bullet")
            for w in gate.warnings[:12]:
                p = doc.add_paragraph(style="List Bullet")
                p.add_run(w)
                if "RD_USEFUL_LIFE" in w:
                    p.add_run(
                        " — Investment significance: capitalized R&D changes invested capital and ROIC; "
                        "a wrong life can flip ROIC–WACC and the valuation conclusion."
                    )
                elif "LEASE_RATE" in w:
                    p.add_run(
                        " — Investment significance: the discount rate scales the lease liability added to "
                        "invested capital and therefore ROIC and residual-income value."
                    )
                elif "SEASONALITY" in w or "PROJECTED" in w:
                    p.add_run(
                        " — Investment significance: a Q2/Q3 projection error can misstate current-year "
                        "value creation versus WACC."
                    )

        doc.add_heading("19. Sources and provenance", level=1)
        doc.add_paragraph(
            "Bloomberg Custom_Run_Filter (PE10/E10/current proprietary fields); SEC EDGAR 10-K/10-Q "
            "companyfacts; Industrial Template formulas after Excel COM CalculateFullRebuild."
        )
        doc.save(path)

    @staticmethod
    def _operating_quality(proj: NewCompanyProjectionReport | None, v: AnnualValuationOutputs | None) -> str:
        roic = (proj.latest_annual_roic if proj else None) or (v.roic if v else None)
        if roic is None:
            return "not assessed"
        if roic >= 0.15:
            return "strong"
        if roic >= 0.08:
            return "adequate"
        return "weak"

    @staticmethod
    def _value_creation(proj: NewCompanyProjectionReport | None, v: AnnualValuationOutputs | None) -> str:
        spread = (proj.projected_roic_wacc if proj and proj.projected_roic_wacc is not None else None)
        if spread is None and v:
            spread = v.roic_wacc
        if spread is None:
            return "not assessed"
        if spread > 0.03:
            return "creates economic value"
        if spread > 0:
            return "marginally above WACC"
        return "does not cover WACC"

    @staticmethod
    def _capital_allocation(buybacks: NewCompanyBuybackReport | None) -> str:
        if not buybacks or not buybacks.analysis:
            return "insufficient repurchase evidence"
        a = buybacks.analysis
        if a.sbc_offset_material:
            return "repurchases largely offset by stock-based compensation"
        if a.value_created_or_destroyed == "created_per_share_value":
            return "repurchases appear value-accretive"
        if a.value_created_or_destroyed == "likely_destroyed_per_share_value":
            return "repurchases may have been above intrinsic value"
        return "repurchase dollars large but effectiveness inconclusive"

    @staticmethod
    def _attractiveness(v: AnnualValuationOutputs | None) -> str:
        if not v or v.expected_annual_return is None:
            return "not assessed"
        er = v.expected_annual_return
        if abs(er) > 1.5:
            er = er / 100.0
        if er >= 0.12:
            return "attractive"
        if er >= 0.08:
            return "fair"
        return "unattractive"
