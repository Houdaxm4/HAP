"""Annual Update runner — previous completed workbook is historical authority; template is the base."""

from __future__ import annotations

import hashlib
import shutil
import time
from pathlib import Path
from typing import Any

from models.annual_update import AnnualPerformanceTimingReport, StageTiming
from services.annual_continuity_service import AnnualContinuityService
from services.annual_deliverables_service import AnnualDeliverablesService
from services.annual_formula_guard_service import AnnualFormulaGuardService
from services.annual_inputs_service import AnnualInputsService
from services.annual_judgment_service import AnnualJudgmentService
from services.annual_leases_service import AnnualLeasesService
from services.annual_output_gate_service import AnnualOutputGateService
from services.annual_rd_service import AnnualRdService
from services.annual_research_service import AnnualResearchService
from services.annual_restatement_service import AnnualRestatementService
from services.annual_statement_validation_service import AnnualStatementValidationService
from services.annual_tax_service import AnnualTaxService
from services.annual_analyst_intelligence_service import AnnualAnalystIntelligenceService
from services.annual_valuation_extract_service import AnnualValuationExtractService
from services.excel_recalc_service import ExcelRecalcService
from services.output_service import OutputService


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class AnnualUpdateRunner:
    def __init__(self, output_service: OutputService | None = None) -> None:
        self.output_service = output_service or OutputService()
        self.continuity = AnnualContinuityService()
        self.restatement = AnnualRestatementService()
        self.statements = AnnualStatementValidationService()
        self.inputs = AnnualInputsService()
        self.tax = AnnualTaxService()
        self.rd = AnnualRdService()
        self.leases = AnnualLeasesService()
        self.guard = AnnualFormulaGuardService()
        self.judgment = AnnualJudgmentService()
        self.research = AnnualResearchService()
        self.intelligence = AnnualAnalystIntelligenceService()
        self.deliverables = AnnualDeliverablesService()
        self.valuation_extract = AnnualValuationExtractService()
        self.output_gates = AnnualOutputGateService()
        self.excel_recalc = ExcelRecalcService()

    def run_workbook_phases(
        self,
        *,
        analysis_id: str,
        ticker: str,
        template_path: Path,
        previous_path: Path,
        working_path: Path,
        custom_run_path: Path | None,
        company_facts: dict[str, Any] | None = None,
        sec_manifest: dict[str, Any] | None = None,
        tax_inputs: dict[str, Any] | None = None,
        restatement_explicit: list[dict[str, Any]] | None = None,
        restatement_narrative: list[dict[str, Any]] | None = None,
        lease_event: bool = False,
        lease_event_note: str | None = None,
        judgment_context: dict[str, Any] | None = None,
        filing_rd: float | None = None,
        live_price: float | None = None,
        prepare_working: bool = True,
        skip_continuity_apply: bool = False,
        new_fiscal_year: str | None = None,
    ) -> dict[str, Any]:
        timings: list[StageTiming] = []
        t0 = time.perf_counter()

        def timed(name: str, fn):
            start = time.perf_counter()
            result = fn()
            timings.append(StageTiming(stage=name, elapsed_ms=(time.perf_counter() - start) * 1000.0))
            return result

        start_hashes = {
            "template": sha256_file(template_path),
            "previous": sha256_file(previous_path),
        }
        if custom_run_path and Path(custom_run_path).exists():
            start_hashes["custom_run_filter"] = sha256_file(custom_run_path)

        if prepare_working:
            working_path.parent.mkdir(parents=True, exist_ok=True)
            if working_path.resolve() != template_path.resolve():
                shutil.copy2(template_path, working_path)

        if skip_continuity_apply:
            from openpyxl import load_workbook as _lw

            tmp = _lw(working_path, data_only=False)
            new_fy = new_fiscal_year
            try:
                if new_fy is None:
                    from services.annual_continuity_service import detect_year_columns

                    for sheet in tmp.sheetnames:
                        cols = detect_year_columns(tmp[sheet])
                        fys = [k for k in cols if k.startswith("FY")]
                        if fys:
                            new_fy = max(fys)
                            break
            finally:
                tmp.close()
            cont_apply = None
        else:
            cont_apply = timed(
                "model_continuity_apply",
                lambda: self.continuity.apply(
                    analysis_id=analysis_id,
                    ticker=ticker,
                    template_path=template_path,
                    previous_workbook_path=previous_path,
                    workbook_path=working_path,
                ),
            )
            new_fy = cont_apply.new_fiscal_year

        rest = timed(
            "historical_restatement",
            lambda: self.restatement.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                explicit_revisions=restatement_explicit,
                narrative_disclosures=restatement_narrative,
            ),
        )
        stmt = timed(
            "new_fy_statement_validation",
            lambda: self.statements.validate(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_year=new_fy or "",
                company_facts=company_facts,
            ),
        )
        completeness = timed(
            "required_data_completeness",
            lambda: self.intelligence.assess_completeness(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                new_fiscal_year=new_fy,
            ),
        )
        tax_research_q: list = []
        tax_kw = dict(tax_inputs or {})
        if not tax_kw.get("reported_effective_rate") and new_fy:
            researched, tax_research_q = self.intelligence.research_tax(
                company_facts=company_facts,
                fiscal_year=new_fy or "",
                ticker=ticker,
                completeness=completeness,
            )
            tax_kw.update({k: v for k, v in researched.items() if v is not None})
        inputs = timed(
            "inputs_pe10_current",
            lambda: self.inputs.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                custom_run_path=custom_run_path,
                new_fiscal_year=new_fy,
                live_price=live_price,
            ),
        )
        tax = timed(
            "tax_update",
            lambda: self.tax.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_year=new_fy or "",
                reported_effective_rate=tax_kw.get("reported_effective_rate"),
                filing_components=tax_kw.get("components"),
                source=tax_kw.get("source"),
                source_locations=tax_kw.get("locations"),
                pretax_income=tax_kw.get("pretax_income"),
                income_tax_expense=tax_kw.get("income_tax_expense"),
            ),
        )
        # Tax research is only "resolved" when schedule cells were written.
        if tax_research_q and (not tax.schedule_populated or not tax.cells_written):
            for q in tax_research_q:
                if q.concept == "tax_effective_rate":
                    q.unsuccessful = True
                    q.rationale = (
                        (q.rationale or "")
                        + " Workbook tax schedule was not populated; treating as unresolved."
                    ).strip()

        if filing_rd is None:
            filing_rd = self._extract_filing_rd(working_path, new_fy, company_facts)

        rd = timed(
            "rd_rollforward",
            lambda: self.rd.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                previous_workbook_path=previous_path,
                fiscal_year=new_fy or "",
                filing_rd=filing_rd,
            ),
        )
        leases = timed(
            "leases_rate_judgment",
            lambda: self.leases.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_year=new_fy or "",
                extraordinary_event=lease_event,
                event_note=lease_event_note,
            ),
        )
        roic, formulas = timed(
            "roic_ratios_final_metrics_guard",
            lambda: self.guard.inspect(
                analysis_id=analysis_id, ticker=ticker, workbook_path=working_path
            ),
        )
        ctx = dict(judgment_context or {})
        ctx["lease_judgment"] = self.leases.judgment_record(leases)
        fy_int = None
        if new_fy:
            digits = "".join(ch for ch in str(new_fy) if ch.isdigit())
            fy_int = int(digits) if digits else None
        research = timed(
            "annual_research",
            lambda: self.research.gather(
                analysis_id=analysis_id,
                ticker=ticker,
                fiscal_year=fy_int,
                sec_manifest=sec_manifest,
                research_questions=tax_research_q,
            ),
        )
        intel_ctx = self.intelligence.build_judgment_context(
            analysis_id=analysis_id,
            ticker=ticker,
            workbook_path=working_path,
            company_facts=company_facts,
            research_evidence=research.hap_interpretations + research.reported_facts[:3],
        )
        ctx.update({k: v for k, v in intel_ctx.items() if k not in ("er_validation", "valuation_validation")})
        er_rep, judge = timed(
            "expected_return_ev_graham_judgment",
            lambda: self.judgment.apply(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                context=ctx,
            ),
        )
        out_dir = self.output_service.analysis_output_dir(analysis_id)
        recalc = timed(
            "excel_recalculation",
            lambda: self.excel_recalc.recalculate(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_year=new_fy,
            ),
        )
        # Refresh Tax/R&D calculated outputs from cached values after recalc.
        if recalc.status == "ok":
            rd = self.rd.refresh_calculated_values(rd, working_path, new_fy or "")

        er_val = None
        val_val = None
        try:
            er_val = self.output_service.read_json(analysis_id, "expected_return_validation_report.json")
        except Exception:  # noqa: BLE001
            er_val = None
        try:
            val_val = self.output_service.read_json(analysis_id, "valuation_validation_report.json")
        except Exception:  # noqa: BLE001
            val_val = None
        valuation = timed(
            "valuation_extract",
            lambda: self.valuation_extract.extract(
                working_path,
                expected_return_validation=er_val if isinstance(er_val, dict) else None,
                valuation_validation=val_val if isinstance(val_val, dict) else None,
                recalculation_complete=(recalc.status == "ok"),
                pe10_fiscal=inputs.pe10.source_value if inputs.pe10 else None,
                pe10_fiscal_label=inputs.pe10.fiscal_year if inputs.pe10 else new_fy,
                pe10_fiscal_as_of=inputs.pe10.as_of_date if inputs.pe10 else None,
                pe10_current=inputs.pe10_current.source_value if inputs.pe10_current else None,
                pe10_current_as_of=inputs.pe10_current.as_of_date if inputs.pe10_current else None,
            ),
        )
        gate = timed(
            "annual_output_gates",
            lambda: self.output_gates.evaluate(
                analysis_id=analysis_id,
                ticker=ticker,
                workbook_path=working_path,
                fiscal_year=new_fy,
                tax=tax,
                inputs=inputs,
                rd=rd,
                valuation=valuation,
                recalc=recalc,
            ),
        )
        # Final investment Word only when gates authorize; otherwise diagnostic Word.
        perf_snap = self.deliverables.build_performance(
            analysis_id=analysis_id,
            ticker=ticker,
            fiscal_year=fy_int or 0,
            workbook_path=working_path,
            research=research,
            valuation=valuation,
            gate=gate,
        )
        deliv = timed(
            "annual_deliverables",
            lambda: self.deliverables.produce(
                analysis_id=analysis_id,
                ticker=ticker,
                fiscal_year=fy_int or 0,
                completed_workbook_path=working_path,
                output_dir=out_dir,
                performance=perf_snap,
                research=research,
                judgment=judge,
                expected_return=er_rep,
                gate=gate,
            ),
        )
        final = timed(
            "model_continuity_final",
            lambda: self.continuity.verify_final(
                analysis_id=analysis_id,
                ticker=ticker,
                previous_workbook_path=previous_path,
                workbook_path=working_path,
                new_fiscal_year=new_fy,
            ),
        )

        end_hashes = {
            "template": sha256_file(template_path),
            "previous": sha256_file(previous_path),
        }
        if custom_run_path and Path(custom_run_path).exists():
            end_hashes["custom_run_filter"] = sha256_file(custom_run_path)

        artifacts = {
            "annual_completeness_report.json": completeness,
            "annual_model_continuity_report.json": final,
            "annual_restatement_report.json": rest,
            "annual_statement_validation_report.json": stmt,
            "annual_inputs_report.json": inputs,
            "annual_tax_update_report.json": tax,
            "annual_rd_report.json": rd,
            "annual_leases_report.json": leases,
            "annual_roic_report.json": roic,
            "annual_formula_guard_report.json": formulas,
            "annual_expected_return_judgment_report.json": er_rep,
            "annual_analyst_judgment_report.json": judge,
            "annual_research_report.json": research,
            "annual_performance_report.json": perf_snap,
            "annual_deliverables_report.json": deliv,
            "annual_valuation_extract_report.json": valuation,
            "annual_output_gate_report.json": gate,
            "annual_excel_recalc_report.json": {
                "analysis_id": recalc.analysis_id,
                "ticker": recalc.ticker,
                "status": recalc.status,
                "method": recalc.method,
                "workbook_path": recalc.workbook_path,
                "elapsed_ms": recalc.elapsed_ms,
                "cells_checked": recalc.cells_checked,
                "missing_cached_values": recalc.missing_cached_values,
                "formula_errors": recalc.formula_errors,
                "error": recalc.error,
                "summary": recalc.summary,
            },
        }
        if cont_apply is not None:
            artifacts["annual_model_continuity_apply_report.json"] = cont_apply
        for name, obj in artifacts.items():
            self.output_service.write_json(analysis_id, name, obj)

        total_ms = (time.perf_counter() - t0) * 1000.0
        timing = AnnualPerformanceTimingReport(
            analysis_id=analysis_id,
            ticker=ticker,
            total_elapsed_ms=round(total_ms, 1),
            stages=timings,
            summary=f"Annual Update workbook phases finished in {total_ms/1000:.1f}s.",
        )
        self.output_service.write_json(analysis_id, "annual_performance_timing_report.json", timing)
        self.output_service.write_json(
            analysis_id,
            "annual_source_immutability.json",
            {"start": start_hashes, "end": end_hashes, "immutable": start_hashes == end_hashes},
        )
        return {
            "new_fiscal_year": new_fy,
            "continuity": final,
            "restatement": rest,
            "statements": stmt,
            "inputs": inputs,
            "tax": tax,
            "rd": rd,
            "leases": leases,
            "roic": roic,
            "formulas": formulas,
            "completeness": completeness,
            "expected_return": er_rep,
            "judgment": judge,
            "research": research,
            "performance": perf_snap,
            "deliverables": deliv,
            "valuation": valuation,
            "output_gate": gate,
            "excel_recalc": recalc,
            "timing": timing,
            "immutable": start_hashes == end_hashes,
        }

    @staticmethod
    def _extract_filing_rd(
        workbook_path: Path,
        fiscal_year: str | None,
        company_facts: dict[str, Any] | None,
    ) -> float | None:
        """Prefer Income-statement R&D already in the workbook; else SEC ResearchAndDevelopmentExpense."""
        from openpyxl import load_workbook
        from services.annual_period_service import detect_year_columns

        if fiscal_year:
            wb = load_workbook(workbook_path, data_only=False)
            try:
                if "Income - GAAP" in wb.sheetnames:
                    ws = wb["Income - GAAP"]
                    cols = detect_year_columns(ws, wb)
                    token = fiscal_year if str(fiscal_year).startswith("FY") else f"FY{fiscal_year}"
                    col = cols.get(token)
                    if col:
                        for row in range(1, min(ws.max_row or 1, 80) + 1):
                            lab = str(ws.cell(row, 1).value or "").lower()
                            if "research" in lab and "development" in lab:
                                val = ws.cell(row, col).value
                                if isinstance(val, (int, float)):
                                    return float(val)
            finally:
                wb.close()
        if not company_facts or not fiscal_year:
            return None
        try:
            from services.sec_service import SecService

            period = fiscal_year if str(fiscal_year).startswith("FY") else f"FY{fiscal_year}"
            fact = SecService().find_fact(
                company_facts,
                "ResearchAndDevelopmentExpense",
                period,
                xbrl_tag_hint="ResearchAndDevelopmentExpense",
            )
            if fact is not None and fact.value is not None:
                # Workbook is in millions.
                return float(fact.value) / 1_000_000.0
        except Exception:  # noqa: BLE001
            return None
        return None
