"""Analyst review actions for New Company lease-rate and R&D useful-life overrides."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from models.new_company import LeaseRateReview, NewCompanyWorkflowState, RdUsefulLifeDecision
from services.new_company_lease_service import NewCompanyLeaseService
from services.new_company_rd_service import NewCompanyRdService
from services.new_company_runner import NewCompanyRunner
from services.output_service import OutputService


class NewCompanyReviewService:
    def __init__(self, output_service: OutputService | None = None) -> None:
        self.output_service = output_service or OutputService()
        self.leases = NewCompanyLeaseService()
        self.rd = NewCompanyRdService()
        self.runner = NewCompanyRunner(output_service=self.output_service)

    def resolve_lease_rate(
        self,
        *,
        analysis_id: str,
        ticker: str,
        company: str,
        workbook_path: Path,
        custom_run_path: Path | None,
        action: str,
        rate: float | None = None,
        reason: str | None = None,
        company_facts: dict[str, Any] | None = None,
        sec_manifest: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        review = self._load_review(analysis_id)
        if review is None:
            raise ValueError("lease_rate_review.json is not available for this analysis.")
        updated = self.leases.apply_review(
            review,
            action=action,
            rate=rate,
            reason=reason,
            workbook_path=workbook_path,
        )
        self.output_service.write_json(analysis_id, "lease_rate_review.json", updated)
        if action == "request_more_evidence":
            return {
                "workflow_state": NewCompanyWorkflowState.AWAITING_ANALYST_REVIEW,
                "lease_review": updated,
            }
        # Recalculate dependent outputs after approve/correct.
        return self.runner.run(
            analysis_id=analysis_id,
            ticker=ticker,
            company=company,
            template_path=workbook_path,
            working_path=workbook_path,
            custom_run_path=custom_run_path,
            company_facts=company_facts,
            sec_manifest=sec_manifest,
            lease_review_override={
                "action": action,
                "rate": updated.approved_rate,
                "reason": reason,
            },
            finalize=True,
            prepare_working=False,
        )

    def override_rd_useful_life(
        self,
        *,
        analysis_id: str,
        ticker: str,
        company: str,
        workbook_path: Path,
        custom_run_path: Path | None,
        life: int,
        reason: str | None = None,
        company_facts: dict[str, Any] | None = None,
        sec_manifest: dict[str, Any] | None = None,
        lease_action: str = "approve",
        lease_rate: float | None = None,
    ) -> dict[str, Any]:
        prior = self._load_rd_decision(analysis_id)
        review = self._load_review(analysis_id)
        override = {"life": life, "reason": reason}
        lease_override = None
        if review and not review.blocking:
            lease_override = {
                "action": review.analyst_action or lease_action,
                "rate": review.approved_rate or lease_rate,
                "reason": review.analyst_reason,
            }
        elif lease_rate is not None:
            lease_override = {"action": lease_action, "rate": lease_rate, "reason": "carry approved rate"}
        result = self.runner.run(
            analysis_id=analysis_id,
            ticker=ticker,
            company=company,
            template_path=workbook_path,
            working_path=workbook_path,
            custom_run_path=custom_run_path,
            company_facts=company_facts,
            sec_manifest=sec_manifest,
            rd_override=override,
            lease_review_override=lease_override,
            finalize=bool(lease_override),
            prepare_working=False,
        )
        # Preserve original agent selection in the rewritten decision.
        decision: RdUsefulLifeDecision = result["rd_decision"]
        if prior and prior.original_agent_selection and not decision.original_agent_selection:
            decision.original_agent_selection = prior.original_agent_selection
            self.output_service.write_json(analysis_id, "rd_useful_life_decision.json", decision)
        return result

    def _load_review(self, analysis_id: str) -> LeaseRateReview | None:
        try:
            raw = self.output_service.read_json(analysis_id, "lease_rate_review.json")
        except FileNotFoundError:
            return None
        return LeaseRateReview.model_validate(raw)

    def _load_rd_decision(self, analysis_id: str) -> RdUsefulLifeDecision | None:
        try:
            raw = self.output_service.read_json(analysis_id, "rd_useful_life_decision.json")
        except FileNotFoundError:
            return None
        return RdUsefulLifeDecision.model_validate(raw)
