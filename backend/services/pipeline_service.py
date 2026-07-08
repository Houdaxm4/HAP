"""Placeholder orchestration for the HAP analysis pipeline."""

from __future__ import annotations

from models.analysis import Analysis, utc_now_iso
from models.pipeline import (
    PipelineStage,
    PipelineState,
    PipelineStepResponse,
    default_pipeline_state,
    pipeline_message_for_stage,
)


class PipelineService:
    """Manage pipeline state transitions and expose step placeholders."""

    def get_state(self, analysis: Analysis) -> PipelineState:
        """Return the current pipeline state for an analysis."""
        return analysis.pipeline

    def start(self, analysis: Analysis) -> PipelineState:
        """
        Begin the pipeline after uploads are present.

        Real implementation will enqueue filing collection and downstream agents.
        """
        if analysis.files.prefilled_workbook is None:
            raise ValueError("prefilled_workbook must be uploaded before starting the pipeline.")
        if analysis.files.custom_run_filter is None:
            raise ValueError("custom_run_filter must be uploaded before starting the pipeline.")

        analysis.pipeline = PipelineState(
            current_stage=PipelineStage.TEMPLATE_UPLOADED,
            stage_status="in_progress",
            message=pipeline_message_for_stage(PipelineStage.TEMPLATE_UPLOADED),
            outputs=analysis.pipeline.outputs,
            updated_at=utc_now_iso(),
        )
        analysis.status = "pipeline_started"
        analysis.updated_at = utc_now_iso()
        return analysis.pipeline

    def _placeholder_step(
        self,
        analysis: Analysis,
        stage: PipelineStage,
        detail: str,
    ) -> PipelineStepResponse:
        """Return a not-implemented response for a pipeline step."""
        analysis.pipeline.current_stage = stage
        analysis.pipeline.stage_status = "not_implemented"
        analysis.pipeline.message = detail
        analysis.pipeline.updated_at = utc_now_iso()
        analysis.updated_at = utc_now_iso()

        return PipelineStepResponse(
            analysis_id=analysis.analysis_id,
            stage=stage,
            stage_status="not_implemented",
            message=detail,
            outputs=analysis.pipeline.outputs,
            implementation_status="not_implemented",
        )

    def collect_filings(self, analysis: Analysis) -> PipelineStepResponse:
        """Placeholder: collect SEC filings and market materials."""
        return self._placeholder_step(
            analysis,
            PipelineStage.FILING_COLLECTION,
            (
                "SEC filing collection is not implemented yet. This step will gather "
                "10-K (10 years), latest 10-Q, earnings release, investor presentation, "
                "Yahoo Finance data, and curated business sources."
            ),
        )

    def parse_filings(self, analysis: Analysis) -> PipelineStepResponse:
        """Placeholder: parse collected filings into structured facts."""
        return self._placeholder_step(
            analysis,
            PipelineStage.FILING_COLLECTION,
            (
                "Filing parsing is not implemented yet. This step will extract structured "
                "financial and business facts from collected SEC documents."
            ),
        )

    def fill_workbook(self, analysis: Analysis) -> PipelineStepResponse:
        """Placeholder: complete blanks in the uploaded Excel template."""
        return self._placeholder_step(
            analysis,
            PipelineStage.WORKBOOK_COMPLETION,
            (
                "Workbook completion is not implemented yet. This step will fill template "
                "blanks using validated filing data without overwriting formulas."
            ),
        )

    def validate_workbook(self, analysis: Analysis) -> PipelineStepResponse:
        """Placeholder: validate completed workbook against sources."""
        return self._placeholder_step(
            analysis,
            PipelineStage.WORKBOOK_VALIDATION,
            (
                "Workbook validation is not implemented yet. This step will reconcile model "
                "outputs with SEC filings and produce discrepancy and confidence reports."
            ),
        )

    def generate_investment_memo(self, analysis: Analysis) -> PipelineStepResponse:
        """Placeholder: generate memo and final recommendation outputs."""
        return self._placeholder_step(
            analysis,
            PipelineStage.FINAL_RECOMMENDATION,
            (
                "Investment memo generation is not implemented yet. This step will produce "
                "the memo, source citations, thesis, risks, and recommendation."
            ),
        )

    def run_fundamental_analysis(self, analysis: Analysis) -> PipelineStepResponse:
        """Placeholder: fundamental analysis stage."""
        return self._placeholder_step(
            analysis,
            PipelineStage.FUNDAMENTAL_ANALYSIS,
            "Fundamental analysis is not implemented yet.",
        )

    def run_market_valuation_analysis(self, analysis: Analysis) -> PipelineStepResponse:
        """Placeholder: market and valuation analysis stage."""
        return self._placeholder_step(
            analysis,
            PipelineStage.MARKET_VALUATION_ANALYSIS,
            "Market and valuation analysis is not implemented yet.",
        )

    def reset_pipeline(self, analysis: Analysis) -> PipelineState:
        """Reset pipeline state to defaults."""
        analysis.pipeline = default_pipeline_state()
        analysis.updated_at = utc_now_iso()
        return analysis.pipeline
