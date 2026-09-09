"""HAP pipeline orchestrator — workbook fill through analytical engine."""

from __future__ import annotations

import time

from models.analysis import Analysis
from models.common import utc_now_iso
from models.pipeline import DecisionLogEntry, PipelineStage, PipelineStatus
from models.quarterly_update import QuarterlyPerformanceReport, StageTiming
from pipeline.stages.fetch_sec_filings import FetchSecFilingsStage
from pipeline.stages.fill_workbook import FillWorkbookStage
from pipeline.stages.generate_write_intents import GenerateWriteIntentsStage
from pipeline.stages.parse_custom_run import ParseCustomRunStage
from pipeline.stages.parse_workbook import ParseWorkbookStage
from pipeline.stages.run_analysis import RunAnalysisStage
from pipeline.stages.validate_workbook import ValidateWorkbookStage
from services.analysis_service import AnalysisService
from services.completion_scope import AnalysisTypeMode, normalize_analysis_type
from services.file_service import FileService
from services.output_service import OutputService
from services.quarterly_carry_forward_service import QuarterlyCarryForwardService
from services.quarterly_deliverables_service import QuarterlyDeliverablesService
from services.quarterly_model_continuity_service import QuarterlyModelContinuityService
from services.quarterly_projection_service import QuarterlyProjectionService
from services.quarterly_research_service import QuarterlyResearchService
from services.quarterly_review_service import QuarterlyReviewService
from services.restatement_check_service import RestatementCheckService
from services.annual_update_runner import AnnualUpdateRunner, sha256_file
from services.annual_continuity_service import AnnualContinuityService
from services.annual_period_service import AnnualPeriodAlignmentError, align_fiscal_periods
from services.annual_workbook_guard_service import assert_base_workbook_guard, build_lineage_report
from services.new_company_runner import NewCompanyRunner
from services.new_company_review_service import NewCompanyReviewService
from models.new_company import NewCompanyWorkflowState


class PipelineError(Exception):
    """Raised when a pipeline stage fails."""


class PipelineOrchestrator:
    """
    Run the HAP workflow.

    Standard (new_company / annual_update):
      Upload → Parse → CRF → SEC → M3 intents → Fill → Validate (incl. annual deep) → Analysis

    Quarterly update (lean):
      Upload → Parse → CRF → Require previous workbook → Carry-forward →
      SEC (light) → Current-data intents/fill + quarterly presentation →
      Restatement check → Lean validate → Quarter review → (skip annual analysis engine)
    """

    def __init__(
        self,
        analysis_service: AnalysisService | None = None,
        file_service: FileService | None = None,
        output_service: OutputService | None = None,
    ) -> None:
        self.analysis_service = analysis_service or AnalysisService()
        self.file_service = file_service or FileService()
        self.output_service = output_service or OutputService()
        self.parse_workbook_stage = ParseWorkbookStage(output_service=self.output_service)
        self.parse_custom_run_stage = ParseCustomRunStage(output_service=self.output_service)
        self.fetch_sec_stage = FetchSecFilingsStage(output_service=self.output_service)
        self.generate_write_intents_stage = GenerateWriteIntentsStage(
            output_service=self.output_service
        )
        self.fill_workbook_stage = FillWorkbookStage(output_service=self.output_service)
        self.validate_workbook_stage = ValidateWorkbookStage(output_service=self.output_service)
        self.run_analysis_stage = RunAnalysisStage(output_service=self.output_service)
        self.carry_forward = QuarterlyCarryForwardService()
        self.model_continuity = QuarterlyModelContinuityService()
        self.restatement_check = RestatementCheckService()
        self.quarterly_review = QuarterlyReviewService()
        self.quarterly_projection = QuarterlyProjectionService()
        self.quarterly_research = QuarterlyResearchService()
        self.quarterly_deliverables = QuarterlyDeliverablesService()
        self.annual_continuity = AnnualContinuityService()
        self.annual_runner = AnnualUpdateRunner(output_service=self.output_service)
        self.new_company_runner = NewCompanyRunner(output_service=self.output_service)
        self.new_company_review = NewCompanyReviewService(output_service=self.output_service)

    def run(self, analysis_id: str) -> Analysis:
        """Execute pipeline stages for the analysis type."""
        analysis = self.analysis_service.get(analysis_id)
        self._assert_ready_for_pipeline(analysis)

        analysis.pipeline = PipelineStatus(
            state="processing",
            current_stage=PipelineStage.PARSE_WORKBOOK,
            progress_pct=5,
            started_at=utc_now_iso(),
        )
        analysis.status = "processing"
        analysis.decision_log = []
        self.analysis_service.save(analysis)

        try:
            mode = normalize_analysis_type(analysis.analysis_type)
            if mode == AnalysisTypeMode.QUARTERLY_UPDATE:
                return self._run_quarterly(analysis)
            if mode == AnalysisTypeMode.ANNUAL_UPDATE:
                return self._run_annual(analysis)
            if mode == AnalysisTypeMode.NEW_COMPANY:
                return self._run_new_company(analysis)
            return self._run_standard(analysis)
        except Exception as exc:  # noqa: BLE001 - never leave analyses stuck processing
            return self._fail(analysis, str(exc))

    def _run_standard(self, analysis: Analysis) -> Analysis:
        analysis_id = analysis.analysis_id
        workbook_path = self.file_service.get_prefilled_workbook_path(analysis)
        custom_run_path = self.file_service.get_custom_run_filter_path(analysis)

        structure, structure_path, log = self.parse_workbook_stage.run(analysis, workbook_path)
        self._complete_stage(
            analysis, PipelineStage.PARSE_WORKBOOK, 20, log, workbook_structure=structure_path
        )

        custom_run, custom_run_path_rel, log = self.parse_custom_run_stage.run(
            analysis, custom_run_path
        )
        self._complete_stage(
            analysis, PipelineStage.PARSE_CUSTOM_RUN, 35, log, custom_run_data=custom_run_path_rel
        )

        cache_dir = self.output_service.analysis_output_dir(analysis_id) / "sec_cache"
        manifest, company_facts, manifest_path, _, log = self.fetch_sec_stage.run(
            analysis, cache_dir=cache_dir
        )
        analysis.cik = manifest.get("cik")
        self._complete_stage(
            analysis, PipelineStage.FETCH_SEC_FILINGS, 55, log, sec_filings_manifest=manifest_path
        )

        _intent_report, intents_path, log = self.generate_write_intents_stage.run(
            analysis, custom_run, company_facts
        )
        analysis.pipeline.outputs.write_intents = intents_path
        analysis.decision_log.append(log)
        analysis.pipeline.progress_pct = 60
        analysis.updated_at = utc_now_iso()
        self.analysis_service.save(analysis)

        provenance_report, completion_report, workbook_path_rel, provenance_path, cell_diff_path, completion_path, log = (
            self.fill_workbook_stage.run(
                analysis,
                workbook_path,
                custom_run,
                structure,
                company_facts,
                manifest,
                write_intents_path=intents_path,
            )
        )
        self._complete_stage(
            analysis,
            PipelineStage.FILL_WORKBOOK,
            80,
            log,
            completed_workbook=workbook_path_rel,
            provenance_report=provenance_path,
            cell_diff_report=cell_diff_path,
            completion_report=completion_path,
        )

        completed_workbook_path = self.output_service.artifact_path(
            analysis_id, "completed_workbook.xlsx"
        )
        discrepancy_report, validation_path, discrepancy_path, log = (
            self.validate_workbook_stage.run(
                analysis,
                custom_run,
                provenance_report,
                completed_workbook_path,
                completion_report=completion_report,
                company_facts=company_facts,
            )
        )
        self._complete_stage(
            analysis,
            PipelineStage.VALIDATE_WORKBOOK,
            90,
            log,
            validation_report=validation_path,
            discrepancy_report=discrepancy_path,
        )

        _, _, model_path, result_path, hap_workbook_path, log = self.run_analysis_stage.run(
            analysis, provenance_report, discrepancy_report, custom_run, company_facts
        )
        self._complete_stage(
            analysis,
            PipelineStage.RUN_ANALYSIS,
            98,
            log,
            company_financial_model=model_path,
            analysis_engine_result=result_path,
            hap_workbook=hap_workbook_path,
        )

        return self._mark_complete(analysis)

    def _run_new_company(self, analysis: Analysis) -> Analysis:
        """New Company initiation: Mode A spine, then ten-year Industrial Template phases."""
        analysis_id = analysis.analysis_id
        workbook_path = self.file_service.get_prefilled_workbook_path(analysis)
        custom_run_path = self.file_service.get_custom_run_filter_path(analysis)

        structure, structure_path, log = self.parse_workbook_stage.run(analysis, workbook_path)
        self._complete_stage(
            analysis, PipelineStage.PARSE_WORKBOOK, 12, log, workbook_structure=structure_path
        )

        custom_run, custom_run_path_rel, log = self.parse_custom_run_stage.run(
            analysis, custom_run_path
        )
        self._complete_stage(
            analysis, PipelineStage.PARSE_CUSTOM_RUN, 22, log, custom_run_data=custom_run_path_rel
        )
        try:
            mapping = {
                "ticker": custom_run.ticker,
                "inputs_annual_pe10": (custom_run.metadata or {}).get("inputs_annual_pe10"),
                "inputs_annual_e10": (custom_run.metadata or {}).get("inputs_annual_e10"),
                "scalars": custom_run.scalars,
            }
            self.output_service.write_json(analysis_id, "custom_run_mapping.json", mapping)
        except Exception:  # noqa: BLE001
            pass

        cache_dir = self.output_service.analysis_output_dir(analysis_id) / "sec_cache"
        manifest, company_facts, manifest_path, _, log = self.fetch_sec_stage.run(
            analysis, cache_dir=cache_dir
        )
        analysis.cik = manifest.get("cik")
        self._complete_stage(
            analysis, PipelineStage.FETCH_SEC_FILINGS, 35, log, sec_filings_manifest=manifest_path
        )

        _intent_report, intents_path, log = self.generate_write_intents_stage.run(
            analysis, custom_run, company_facts
        )
        analysis.pipeline.outputs.write_intents = intents_path
        analysis.decision_log.append(log)
        analysis.pipeline.progress_pct = 42
        analysis.updated_at = utc_now_iso()
        self.analysis_service.save(analysis)

        provenance_report, completion_report, workbook_path_rel, provenance_path, cell_diff_path, completion_path, log = (
            self.fill_workbook_stage.run(
                analysis,
                workbook_path,
                custom_run,
                structure,
                company_facts,
                manifest,
                write_intents_path=intents_path,
            )
        )
        self._complete_stage(
            analysis,
            PipelineStage.FILL_WORKBOOK,
            55,
            log,
            completed_workbook=workbook_path_rel,
            provenance_report=provenance_path,
            cell_diff_report=cell_diff_path,
            completion_report=completion_path,
        )

        completed_workbook_path = self.output_service.artifact_path(
            analysis_id, "completed_workbook.xlsx"
        )
        discrepancy_report, validation_path, discrepancy_path, log = (
            self.validate_workbook_stage.run(
                analysis,
                custom_run,
                provenance_report,
                completed_workbook_path,
                completion_report=completion_report,
                company_facts=company_facts,
            )
        )
        self._complete_stage(
            analysis,
            PipelineStage.VALIDATE_WORKBOOK,
            65,
            log,
            validation_report=validation_path,
            discrepancy_report=discrepancy_path,
        )

        from services.new_company_period_service import NewCompanyPeriodService

        period_probe = NewCompanyPeriodService().detect(
            analysis_id=analysis_id, ticker=analysis.ticker, workbook_path=completed_workbook_path
        )
        industrial = (
            period_probe.template_family == "industrial_template"
            and len(period_probe.fiscal_years) >= 8
        )
        if not industrial:
            # Generic/non-template workbooks keep the Mode A analysis-engine spine.
            _, _, model_path, result_path, hap_workbook_path, log = self.run_analysis_stage.run(
                analysis, provenance_report, discrepancy_report, custom_run, company_facts
            )
            self._complete_stage(
                analysis,
                PipelineStage.RUN_ANALYSIS,
                98,
                log,
                company_financial_model=model_path,
                analysis_engine_result=result_path,
                hap_workbook=hap_workbook_path,
            )
            return self._mark_complete(analysis)

        result = self.new_company_runner.run(
            analysis_id=analysis_id,
            ticker=analysis.ticker,
            company=analysis.company,
            template_path=completed_workbook_path,
            working_path=completed_workbook_path,
            custom_run_path=custom_run_path,
            company_facts=company_facts,
            sec_manifest=manifest,
            prepare_working=False,
            wacc=custom_run.assumptions.get("wacc") if custom_run.assumptions else None,
        )
        workflow = result["workflow_state"]
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="New Company",
                action="new_company_phases",
                detail=result["state"].summary,
                confidence=0.8,
            )
        )
        return self._apply_new_company_workflow(
            analysis,
            workflow,
            provenance_report=provenance_report,
            discrepancy_report=discrepancy_report,
            custom_run=custom_run,
            company_facts=company_facts,
        )

    def finalize_new_company_review(
        self,
        analysis: Analysis,
        *,
        action: str,
        rate: float | None = None,
        reason: str | None = None,
        rd_life: int | None = None,
    ) -> Analysis:
        """Resume after lease-rate review or R&D override."""
        analysis_id = analysis.analysis_id
        workbook_path = self.output_service.artifact_path(analysis_id, "completed_workbook.xlsx")
        custom_run_path = self.file_service.get_custom_run_filter_path(analysis)
        company_facts = {}
        manifest = {}
        try:
            company_facts = self.output_service.read_json(analysis_id, "company_facts.json")
        except Exception:  # noqa: BLE001
            company_facts = {}
        try:
            manifest = self.output_service.read_json(analysis_id, "sec_filings_manifest.json")
        except Exception:  # noqa: BLE001
            manifest = {}
        analysis.status = "recalculating"
        analysis.pipeline.state = "processing"
        self.analysis_service.save(analysis)
        if rd_life is not None:
            result = self.new_company_review.override_rd_useful_life(
                analysis_id=analysis_id,
                ticker=analysis.ticker,
                company=analysis.company,
                workbook_path=workbook_path,
                custom_run_path=custom_run_path,
                life=rd_life,
                reason=reason,
                company_facts=company_facts,
                sec_manifest=manifest,
            )
        else:
            result = self.new_company_review.resolve_lease_rate(
                analysis_id=analysis_id,
                ticker=analysis.ticker,
                company=analysis.company,
                workbook_path=workbook_path,
                custom_run_path=custom_run_path,
                action=action,
                rate=rate,
                reason=reason,
                company_facts=company_facts,
                sec_manifest=manifest,
            )
        workflow = result.get("workflow_state") or result["state"].workflow_state
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="New Company Analyst Review",
                action=f"review_{action if rd_life is None else 'rd_override'}",
                detail=str(result.get("state").summary if result.get("state") else workflow),
                confidence=0.9,
            )
        )
        custom_run = None
        try:
            from models.custom_run import CustomRunData

            raw = self.output_service.read_json(analysis_id, "custom_run_data.json")
            custom_run = CustomRunData.model_validate(raw)
        except Exception:  # noqa: BLE001
            custom_run = None
        from models.provenance import ProvenanceReport
        from models.validation import DiscrepancyReport

        provenance_report = ProvenanceReport(analysis_id=analysis_id, ticker=analysis.ticker)
        discrepancy_report = DiscrepancyReport(analysis_id=analysis_id, ticker=analysis.ticker)
        try:
            provenance_report = ProvenanceReport.model_validate(
                self.output_service.read_json(analysis_id, "provenance_report.json")
            )
        except Exception:  # noqa: BLE001
            pass
        try:
            discrepancy_report = DiscrepancyReport.model_validate(
                self.output_service.read_json(analysis_id, "discrepancy_report.json")
            )
        except Exception:  # noqa: BLE001
            pass
        return self._apply_new_company_workflow(
            analysis,
            workflow,
            provenance_report=provenance_report,
            discrepancy_report=discrepancy_report,
            custom_run=custom_run,
            company_facts=company_facts,
        )

    def _apply_new_company_workflow(
        self,
        analysis: Analysis,
        workflow: NewCompanyWorkflowState,
        *,
        provenance_report,
        discrepancy_report,
        custom_run,
        company_facts,
    ) -> Analysis:
        if workflow == NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW:
            analysis.status = "awaiting_analyst_review"
            analysis.pipeline.state = "processing"
            analysis.pipeline.progress_pct = 85
            analysis.updated_at = utc_now_iso()
            self.analysis_service.save(analysis)
            return analysis
        if workflow == NewCompanyWorkflowState.COMPLETE:
            if custom_run is not None:
                _, _, model_path, result_path, hap_workbook_path, log = self.run_analysis_stage.run(
                    analysis, provenance_report, discrepancy_report, custom_run, company_facts
                )
                self._complete_stage(
                    analysis,
                    PipelineStage.RUN_ANALYSIS,
                    98,
                    log,
                    company_financial_model=model_path,
                    analysis_engine_result=result_path,
                    hap_workbook=hap_workbook_path,
                )
            return self._mark_complete(analysis)
        analysis.status = "needs_review" if workflow == NewCompanyWorkflowState.NEEDS_REVIEW else "failed"
        if workflow == NewCompanyWorkflowState.FAILED:
            analysis.pipeline.state = "failed"
            analysis.pipeline.current_stage = PipelineStage.FAILED
        else:
            # Stages finished, but the report is not authorized (e.g. Excel COM missing).
            analysis.pipeline.state = "complete"
            analysis.pipeline.current_stage = PipelineStage.COMPLETE
            analysis.pipeline.progress_pct = 95
            analysis.pipeline.completed_at = utc_now_iso()
        analysis.updated_at = utc_now_iso()
        self.analysis_service.save(analysis)
        return analysis

    def _run_annual(self, analysis: Analysis) -> Analysis:
        """Annual Update: preserve historical analyst work; refresh new FY + current data + Word."""
        analysis_id = analysis.analysis_id
        current_template_path = self.file_service.get_prefilled_workbook_path(analysis)
        custom_run_path = self.file_service.get_custom_run_filter_path(analysis)
        previous_workbook_path = self.file_service.get_previous_workbook_path(analysis)
        if previous_workbook_path is None:
            raise PipelineError(
                "MISSING_PREVIOUS_WORKBOOK: annual_update requires the previous completed workbook."
            )
        if sha256_file(current_template_path) == sha256_file(previous_workbook_path):
            raise PipelineError(
                "ANNUAL_BASE_WORKBOOK_VIOLATION: current template and previous workbook are identical files."
            )

        try:
            period_alignment = align_fiscal_periods(current_template_path, previous_workbook_path)
        except AnnualPeriodAlignmentError as exc:
            raise PipelineError(str(exc)) from exc

        structure, structure_path, log = self.parse_workbook_stage.run(
            analysis, current_template_path
        )
        self._complete_stage(
            analysis, PipelineStage.PARSE_WORKBOOK, 12, log, workbook_structure=structure_path
        )
        custom_run, custom_run_rel, log = self.parse_custom_run_stage.run(analysis, custom_run_path)
        self._complete_stage(
            analysis, PipelineStage.PARSE_CUSTOM_RUN, 18, log, custom_run_data=custom_run_rel
        )

        import shutil as _shutil

        working_workbook_path = self.output_service.artifact_path(
            analysis_id, "annual_working_workbook.xlsx"
        )
        working_workbook_path.parent.mkdir(parents=True, exist_ok=True)
        _shutil.copy2(current_template_path, working_workbook_path)
        working_initial_sha = sha256_file(working_workbook_path)

        apply_report = self.annual_continuity.apply(
            analysis_id=analysis_id,
            ticker=analysis.ticker,
            template_path=current_template_path,
            previous_workbook_path=previous_workbook_path,
            workbook_path=working_workbook_path,
            new_fiscal_year=period_alignment.new_fiscal_year,
            period_alignment=period_alignment,
        )
        self.output_service.write_json(
            analysis_id, "annual_model_continuity_apply_report.json", apply_report
        )
        lineage = build_lineage_report(
            analysis_id=analysis_id,
            ticker=analysis.ticker,
            template_path=current_template_path,
            previous_path=previous_workbook_path,
            working_path=working_workbook_path,
            final_path=working_workbook_path,
            alignment=period_alignment,
            continuity_summary=apply_report.summary,
        )
        lineage.working_workbook_initial_sha256 = working_initial_sha
        self.output_service.write_json(analysis_id, "annual_workbook_lineage_report.json", lineage)

        cache_dir = self.output_service.analysis_output_dir(analysis_id) / "sec_cache"
        manifest, company_facts, manifest_path, _, log = self.fetch_sec_stage.run(
            analysis, cache_dir=cache_dir
        )
        analysis.cik = manifest.get("cik")
        self._complete_stage(
            analysis, PipelineStage.FETCH_SEC_FILINGS, 40, log, sec_filings_manifest=manifest_path
        )
        _intent_report, intents_path, log = self.generate_write_intents_stage.run(
            analysis, custom_run, company_facts, workbook_path=current_template_path
        )
        analysis.pipeline.outputs.write_intents = intents_path
        analysis.decision_log.append(log)

        provenance_report, completion_report, workbook_rel, provenance_path, cell_diff_path, completion_path, log = (
            self.fill_workbook_stage.run(
                analysis,
                working_workbook_path,
                custom_run,
                structure,
                company_facts,
                manifest,
                write_intents_path=intents_path,
            )
        )
        self._complete_stage(
            analysis,
            PipelineStage.FILL_WORKBOOK,
            70,
            log,
            completed_workbook=workbook_rel,
            provenance_report=provenance_path,
            cell_diff_report=cell_diff_path,
            completion_report=completion_path,
        )
        completed_path = self.output_service.artifact_path(analysis_id, "completed_workbook.xlsx")

        discrepancy_report, validation_path, discrepancy_path, log = self.validate_workbook_stage.run(
            analysis,
            custom_run,
            provenance_report,
            completed_path,
            completion_report=completion_report,
            company_facts=company_facts,
            skip_annual_deep_review=False,
        )
        self._complete_stage(
            analysis,
            PipelineStage.VALIDATE_WORKBOOK,
            82,
            log,
            validation_report=validation_path,
            discrepancy_report=discrepancy_path,
        )

        result = self.annual_runner.run_workbook_phases(
            analysis_id=analysis_id,
            ticker=analysis.ticker,
            template_path=current_template_path,
            previous_path=previous_workbook_path,
            working_path=completed_path,
            custom_run_path=custom_run_path,
            company_facts=company_facts,
            sec_manifest=manifest,
            prepare_working=False,
            skip_continuity_apply=True,
            new_fiscal_year=period_alignment.new_fiscal_year,
        )
        guard = assert_base_workbook_guard(
            analysis_id=analysis_id,
            ticker=analysis.ticker,
            template_path=current_template_path,
            previous_path=previous_workbook_path,
            final_path=completed_path,
            alignment=period_alignment,
        )
        self.output_service.write_json(analysis_id, "annual_base_workbook_guard_report.json", guard)
        if guard.status == "ANNUAL_BASE_WORKBOOK_VIOLATION":
            raise PipelineError(guard.summary)
        lineage = lineage.model_copy(update={"final_workbook_sha256": guard.final_sha256})
        self.output_service.write_json(analysis_id, "annual_workbook_lineage_report.json", lineage)
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Annual Update",
                action="annual_update_phases",
                detail=result["timing"].summary if result.get("timing") else "Annual phases complete.",
                confidence=0.85,
            )
        )
        gate = result.get("output_gate")
        if gate is not None and getattr(gate, "status", "ok") != "ok":
            analysis.decision_log.append(
                DecisionLogEntry(
                    agent="Annual Update",
                    action="annual_output_gates",
                    detail=gate.summary,
                    confidence=0.5,
                )
            )
            analysis.pipeline.state = "complete"
            analysis.pipeline.current_stage = PipelineStage.COMPLETE
            analysis.pipeline.progress_pct = 100
            analysis.pipeline.completed_at = utc_now_iso()
            analysis.status = "needs_review"
            analysis.updated_at = utc_now_iso()
            self.analysis_service.save(analysis)
            return analysis
        return self._mark_complete(analysis)

    def _run_quarterly(self, analysis: Analysis) -> Analysis:
        """Lean quarterly_update path — carry forward + refresh current + quarter review."""
        analysis_id = analysis.analysis_id
        timings: list[StageTiming] = []
        skipped_annual = [
            "annual_m3_full_reconstruction",
            "roic_full_review",
            "expected_return_full_review",
            "valuation_full_review",
            "final_recommendation",
            "run_analysis_engine",
        ]
        t0 = time.perf_counter()

        def _time(name: str, fn):
            start = time.perf_counter()
            result = fn()
            timings.append(
                StageTiming(stage=name, elapsed_ms=(time.perf_counter() - start) * 1000.0)
            )
            return result

        workbook_path = self.file_service.get_prefilled_workbook_path(analysis)
        custom_run_path = self.file_service.get_custom_run_filter_path(analysis)
        previous_path = self.file_service.get_previous_workbook_path(analysis)

        structure, structure_path, log = _time(
            "parse_workbook",
            lambda: self.parse_workbook_stage.run(analysis, workbook_path),
        )
        self._complete_stage(
            analysis, PipelineStage.PARSE_WORKBOOK, 15, log, workbook_structure=structure_path
        )

        custom_run, custom_run_path_rel, log = _time(
            "parse_custom_run",
            lambda: self.parse_custom_run_stage.run(analysis, custom_run_path),
        )
        self._complete_stage(
            analysis, PipelineStage.PARSE_CUSTOM_RUN, 25, log, custom_run_data=custom_run_path_rel
        )

        # Previous workbook is REQUIRED
        if previous_path is None:
            raise PipelineError(
                "MISSING_PREVIOUS_WORKBOOK: quarterly_update requires a previous completed "
                "workbook. Upload previous_workbook rather than reconstructing from SEC."
            )

        carried_path = self.output_service.artifact_path(
            analysis_id, "quarterly_carried_workbook.xlsx"
        )

        def _carry():
            return self.carry_forward.apply(
                analysis_id=analysis_id,
                ticker=analysis.ticker,
                new_template_path=workbook_path,
                previous_workbook_path=previous_path,
                destination_path=carried_path,
            )

        carry_report = _time("carry_forward", _carry)
        carry_path_rel = self.output_service.write_json(
            analysis_id, "quarterly_carry_forward_report.json", carry_report
        )
        if carry_report.status == "MISSING_PREVIOUS_WORKBOOK":
            raise PipelineError(carry_report.summary)
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Quarterly Carry-Forward",
                action="carry_forward",
                detail=carry_report.summary,
                confidence=0.9,
                citations=[carry_path_rel],
            )
        )

        apply_report = _time(
            "model_continuity_apply",
            lambda: self.model_continuity.apply_persistent_continuity(
                analysis_id=analysis_id,
                ticker=analysis.ticker,
                new_template_path=workbook_path,
                previous_workbook_path=previous_path,
                workbook_path=carried_path,
            ),
        )
        apply_path = self.output_service.write_json(
            analysis_id, "quarterly_model_continuity_apply_report.json", apply_report
        )
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Model Continuity",
                action="apply_persistent_continuity",
                detail=apply_report.summary,
                confidence=0.85,
                citations=[apply_path],
            )
        )

        cache_dir = self.output_service.analysis_output_dir(analysis_id) / "sec_cache"
        manifest, company_facts, manifest_path, _, log = _time(
            "fetch_sec_filings",
            lambda: self.fetch_sec_stage.run(analysis, cache_dir=cache_dir),
        )
        analysis.cik = manifest.get("cik")
        self._complete_stage(
            analysis, PipelineStage.FETCH_SEC_FILINGS, 45, log, sec_filings_manifest=manifest_path
        )

        # M3 still runs but completion scope limits quarterly writes to current_data + LQ
        _intent_report, intents_path, log = _time(
            "generate_write_intents_scoped",
            lambda: self.generate_write_intents_stage.run(analysis, custom_run, company_facts),
        )
        analysis.pipeline.outputs.write_intents = intents_path
        analysis.decision_log.append(log)

        # Fill from carried workbook (not raw blank template)
        provenance_report, completion_report, workbook_path_rel, provenance_path, cell_diff_path, completion_path, log = _time(
            "fill_workbook_current_and_quarterly",
            lambda: self.fill_workbook_stage.run(
                analysis,
                carried_path,
                custom_run,
                structure,
                company_facts,
                manifest,
                write_intents_path=intents_path,
            ),
        )
        self._complete_stage(
            analysis,
            PipelineStage.FILL_WORKBOOK,
            70,
            log,
            completed_workbook=workbook_path_rel,
            provenance_report=provenance_path,
            cell_diff_report=cell_diff_path,
            completion_report=completion_path,
        )

        completed_workbook_path = self.output_service.artifact_path(
            analysis_id, "completed_workbook.xlsx"
        )

        # Re-lock ignored template sheets after fill (As Reported, DividendHelper)
        self.model_continuity.restore_ignored_sheets(
            new_template_path=workbook_path,
            workbook_path=completed_workbook_path,
        )

        restatement = _time(
            "restatement_check",
            lambda: self.restatement_check.check(
                analysis_id=analysis_id,
                ticker=analysis.ticker,
                previous_workbook_path=previous_path,
                company_facts=company_facts,
            ),
        )
        rest_path = self.output_service.write_json(
            analysis_id, "restatement_check_report.json", restatement
        )
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Restatement Check",
                action="lightweight_restatement_check",
                detail=restatement.summary,
                confidence=0.85,
                citations=[rest_path],
            )
        )

        discrepancy_report, validation_path, discrepancy_path, log = _time(
            "validate_workbook_lean",
            lambda: self.validate_workbook_stage.run(
                analysis,
                custom_run,
                provenance_report,
                completed_workbook_path,
                completion_report=completion_report,
                company_facts=company_facts,
                skip_annual_deep_review=True,
            ),
        )
        self._complete_stage(
            analysis,
            PipelineStage.VALIDATE_WORKBOOK,
            88,
            log,
            validation_report=validation_path,
            discrepancy_report=discrepancy_path,
        )

        q_review = _time(
            "quarterly_analyst_review",
            lambda: self.quarterly_review.review(
                analysis_id=analysis_id,
                ticker=analysis.ticker,
                workbook_path=completed_workbook_path,
            ),
        )
        q_path = self.output_service.write_json(
            analysis_id, "quarterly_analyst_review.json", q_review
        )
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Quarter Analyst Review",
                action="quarter_scoped_review",
                detail=q_review.summary,
                confidence=0.8,
                citations=[q_path],
            )
        )

        projection = _time(
            "quarterly_projection",
            lambda: self.quarterly_projection.apply(
                analysis_id=analysis_id,
                ticker=analysis.ticker,
                workbook_path=completed_workbook_path,
                previous_workbook_path=previous_path,
            ),
        )
        proj_path = self.output_service.write_json(
            analysis_id, "quarterly_projection_report.json", projection
        )
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Quarter Projection",
                action="q2_q3_roic_roce_projection",
                detail=projection.summary,
                confidence=0.85,
                citations=[proj_path],
            )
        )

        # Final: restore ignored sheets after projection, then verify deliverable
        self.model_continuity.restore_ignored_sheets(
            new_template_path=workbook_path,
            workbook_path=completed_workbook_path,
        )
        final_continuity = _time(
            "model_continuity_final",
            lambda: self.model_continuity.verify_final_deliverable(
                analysis_id=analysis_id,
                ticker=analysis.ticker,
                new_template_path=workbook_path,
                workbook_path=completed_workbook_path,
            ),
        )
        cont_path = self.output_service.write_json(
            analysis_id, "quarterly_model_continuity_report.json", final_continuity
        )
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Model Continuity",
                action="verify_final_deliverable",
                detail=final_continuity.summary,
                confidence=0.9,
                citations=[cont_path],
            )
        )

        out_dir = self.output_service.analysis_output_dir(analysis_id)
        research = _time(
            "quarterly_research",
            lambda: self.quarterly_research.gather(
                analysis_id=analysis_id,
                ticker=analysis.ticker,
                fiscal_year=projection.fiscal_year,
                fiscal_quarter=projection.fiscal_quarter,
                sec_manifest=manifest,
            ),
        )
        research_path = self.output_service.write_json(
            analysis_id, "quarterly_research_report.json", research
        )
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Quarter Research",
                action="external_research_for_word",
                detail=research.summary,
                confidence=0.75,
                citations=[research_path],
            )
        )

        deliverables = _time(
            "quarterly_deliverables",
            lambda: self.quarterly_deliverables.produce(
                analysis_id=analysis_id,
                ticker=analysis.ticker,
                completed_workbook_path=completed_workbook_path,
                output_dir=out_dir,
                fiscal_year=projection.fiscal_year,
                fiscal_quarter=projection.fiscal_quarter,
                projection=projection,
                review=q_review,
                research=research,
            ),
        )
        deliv_path = self.output_service.write_json(
            analysis_id, "quarterly_deliverables_report.json", deliverables
        )
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Quarter Deliverables",
                action="excel_fa_and_word_report",
                detail=deliverables.summary,
                confidence=1.0,
                citations=[deliv_path],
            )
        )

        # Explicitly skip run_analysis
        timings.append(
            StageTiming(
                stage="run_analysis_engine",
                elapsed_ms=0.0,
                executed=False,
                skipped_reason="annual-only stage skipped for quarterly_update",
            )
        )
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Pipeline Orchestrator",
                action="skip_annual_analysis_engine",
                detail="Skipped RUN_ANALYSIS for quarterly_update lean path.",
                confidence=1.0,
            )
        )

        total_ms = (time.perf_counter() - t0) * 1000.0
        perf = QuarterlyPerformanceReport(
            analysis_id=analysis_id,
            ticker=analysis.ticker,
            total_elapsed_ms=round(total_ms, 1),
            stages=timings,
            annual_only_stages_skipped=skipped_annual,
            summary=(
                f"Quarterly lean path finished in {total_ms/1000:.1f}s; "
                f"skipped {len(skipped_annual)} annual-only stages."
            ),
        )
        self.output_service.write_json(analysis_id, "quarterly_performance_report.json", perf)

        # Mark RUN_ANALYSIS as intentionally not completed — advance to complete
        analysis.pipeline.progress_pct = 98
        return self._mark_complete(analysis)

    def _mark_complete(self, analysis: Analysis) -> Analysis:
        analysis.pipeline.state = "complete"
        analysis.pipeline.current_stage = PipelineStage.COMPLETE
        analysis.pipeline.progress_pct = 100
        analysis.pipeline.completed_at = utc_now_iso()
        analysis.status = "complete" if analysis.is_pipeline_complete else "processing"
        analysis.updated_at = utc_now_iso()
        self.analysis_service.save(analysis)
        return analysis

    def _complete_stage(
        self,
        analysis: Analysis,
        stage: PipelineStage,
        progress_pct: int,
        log_entry: DecisionLogEntry,
        **output_fields: str,
    ) -> None:
        analysis.pipeline.stages_completed.append(stage)
        next_stage = self._next_stage(stage)
        analysis.pipeline.current_stage = next_stage
        analysis.pipeline.progress_pct = progress_pct
        for field_name, value in output_fields.items():
            setattr(analysis.pipeline.outputs, field_name, value)
        analysis.decision_log.append(log_entry)
        analysis.updated_at = utc_now_iso()
        self.analysis_service.save(analysis)

    def _fail(self, analysis: Analysis, message: str) -> Analysis:
        analysis.pipeline.state = "failed"
        analysis.pipeline.current_stage = PipelineStage.FAILED
        analysis.pipeline.error = message
        analysis.pipeline.completed_at = utc_now_iso()
        analysis.status = "failed"
        analysis.updated_at = utc_now_iso()
        analysis.decision_log.append(
            DecisionLogEntry(
                agent="Pipeline Orchestrator",
                action="pipeline_failed",
                detail=message,
                confidence=0.0,
            )
        )
        self.analysis_service.save(analysis)
        return analysis

    @staticmethod
    def _next_stage(stage: PipelineStage) -> PipelineStage | None:
        order = [
            PipelineStage.PARSE_WORKBOOK,
            PipelineStage.PARSE_CUSTOM_RUN,
            PipelineStage.FETCH_SEC_FILINGS,
            PipelineStage.FILL_WORKBOOK,
            PipelineStage.VALIDATE_WORKBOOK,
            PipelineStage.RUN_ANALYSIS,
            PipelineStage.COMPLETE,
        ]
        try:
            index = order.index(stage)
        except ValueError:
            return None
        return order[index + 1] if index + 1 < len(order) else PipelineStage.COMPLETE

    def assert_ready_for_pipeline(self, analysis: Analysis) -> None:
        """Validate that an analysis has the uploads required to start the pipeline."""
        self._assert_ready_for_pipeline(analysis)

    @staticmethod
    def _assert_ready_for_pipeline(analysis: Analysis) -> None:
        if analysis.files.prefilled_workbook is None:
            raise PipelineError("prefilled_workbook must be uploaded before running the pipeline.")
        if analysis.files.custom_run_filter is None:
            raise PipelineError("custom_run_filter is required before running the pipeline.")
        from services.completion_scope import AnalysisTypeMode, normalize_analysis_type

        mode = normalize_analysis_type(analysis.analysis_type)
        if mode in {AnalysisTypeMode.ANNUAL_UPDATE, AnalysisTypeMode.QUARTERLY_UPDATE}:
            if analysis.files.previous_workbook is None:
                raise PipelineError(
                    "previous_workbook is required for annual_update and quarterly_update."
                )
        if analysis.pipeline.state == "processing":
            raise PipelineError("Pipeline is already running for this analysis.")
