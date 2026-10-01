"""Checkpointed analysis run: pipeline -> analyst gates -> dossier (with outside evidence) -> your review.

The supervisor never approves a review gate, edits scores or overrides the recommendation. It runs the
deterministic pipeline, stops where a human decision is needed, gathers labeled outside evidence, optionally
adds a clearly labeled "my take", and records your answer at each checkpoint as feedback (which feeds lessons).
State lives in `agent_run.json` inside the analysis output folder.
"""

from __future__ import annotations

import threading
import uuid
from typing import Any

from models.common import utc_now_iso
from services.recommendation_conflict import recommendation_conflict
from services.safe_io import write_json_atomic

STATE_FILE = "agent_run.json"
DOSSIER_FILE = "agent_dossier.json"
DECISIONS = {"approve", "revise", "stop"}
_LOCK = threading.Lock()

MY_TAKE_INSTRUCTIONS = (
    "\n\nTASK: Write the 'my take' section of the analyst dossier for this analysis. Use the tools to check "
    "the recommendation, the main risks, validation flags and anything marked as needing review, plus at most a "
    "few outside-evidence lookups for facts newer than the analysis. Format: 1) What I would conclude (2-3 "
    "sentences, may differ from HAP's rules-based recommendation; say so plainly if it does). 2) The three "
    "points that matter most, each with its source. 3) What would change my mind. 4) Questions for the analyst. "
    "Start with: 'MY TAKE (opinion, not HAP's rules-based result).' Keep it under 350 words."
)


class RunWorkflowError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


class AgentRunService:
    def __init__(
        self,
        *,
        analysis_service: Any,
        output_service: Any,
        pipeline: Any,
        feedback_service: Any = None,
        agent: Any = None,
        research_factory: Any = None,
    ) -> None:
        self.analysis_service = analysis_service
        self.output_service = output_service
        self.pipeline = pipeline
        self.feedback = feedback_service
        self.agent = agent
        self.research_factory = research_factory

    # ---- state ----------------------------------------------------------------------------

    def state(self, analysis_id: str) -> dict[str, Any]:
        try:
            return self.output_service.read_json(analysis_id, STATE_FILE)
        except (FileNotFoundError, ValueError):
            return {"analysis_id": analysis_id, "phase": "not_started", "checkpoints": [], "history": []}

    def _save(self, analysis_id: str, state: dict[str, Any]) -> dict[str, Any]:
        state["updated_at"] = utc_now_iso()
        write_json_atomic(self.output_service.analysis_output_dir(analysis_id) / STATE_FILE, state)
        return state

    @staticmethod
    def _log(state: dict[str, Any], event: str) -> None:
        state.setdefault("history", []).append({"at": utc_now_iso(), "event": event})

    @staticmethod
    def _open(state: dict[str, Any], kind: str) -> dict[str, Any] | None:
        return next((c for c in state["checkpoints"] if c["kind"] == kind and c["status"] == "open"), None)

    @staticmethod
    def _add_checkpoint(state: dict[str, Any], kind: str, title: str, summary: str, options: list[str], data: dict | None = None) -> dict[str, Any]:
        checkpoint = {
            "id": uuid.uuid4().hex[:12], "kind": kind, "status": "open", "title": title, "summary": summary,
            "options": options, "data": data or {}, "created_at": utc_now_iso(), "answer": None,
        }
        state["checkpoints"].append(checkpoint)
        return checkpoint

    # ---- start / advance ------------------------------------------------------------------

    def start(self, analysis_id: str) -> dict[str, Any]:
        """Validate readiness (raises RunWorkflowError) and mark the run started. Pipeline runs separately."""
        analysis = self.analysis_service.get(analysis_id)
        if analysis.status != "complete":
            try:
                self.pipeline.assert_ready_for_pipeline(analysis)
            except Exception as exc:  # noqa: BLE001 - PipelineError text is user-facing
                raise RunWorkflowError(str(exc)) from exc
        with _LOCK:
            state = self.state(analysis_id)
            state.update({"analysis_id": analysis_id, "phase": "pipeline", "started_at": utc_now_iso()})
            state.setdefault("checkpoints", [])
            self._log(state, "run started")
            return self._save(analysis_id, state)

    def run(self, analysis_id: str, with_take: bool = False) -> dict[str, Any]:
        """Background entry point: run the pipeline when needed, then advance to the next checkpoint."""
        analysis = self.analysis_service.get(analysis_id)
        if analysis.status != "complete":
            self.pipeline.run(analysis_id)
        return self.advance(analysis_id, with_take=with_take)

    def advance(self, analysis_id: str, with_take: bool = False) -> dict[str, Any]:
        """Look at where the analysis is and open the next checkpoint if one is due. Safe to call repeatedly."""
        analysis = self.analysis_service.get(analysis_id)
        with _LOCK:
            state = self.state(analysis_id)
            state.setdefault("checkpoints", [])
            status = analysis.status

            if status in {"processing", "recalculating"}:
                state["phase"] = "pipeline"
            elif status == "failed":
                state["phase"] = "waiting_for_you"
                if not self._open(state, "pipeline_failed"):
                    error = getattr(analysis.pipeline, "error", None) or "The pipeline failed."
                    self._add_checkpoint(
                        state, "pipeline_failed", "The pipeline failed",
                        f"{error} Fix the cause (for example the upload or Excel recalculation) and run again.",
                        ["revise", "stop"],
                    )
            elif status in {"awaiting_analyst_review", "needs_review"}:
                state["phase"] = "waiting_for_you"
                if not self._open(state, "analyst_review"):
                    self._add_checkpoint(
                        state, "analyst_review", "Your judgment is needed",
                        "The pipeline paused for a decision (lease discount rate / R&D useful life). Review the proposed "
                        "values in the Review tab, approve or correct them, then continue.",
                        ["approve", "revise", "stop"], {"status": status},
                    )
            elif status == "complete":
                if not (self._open(state, "final_review") or any(c["kind"] == "final_review" for c in state["checkpoints"])):
                    dossier = self._build_dossier(analysis_id, with_take)
                    state["phase"] = "waiting_for_you"
                    self._add_checkpoint(
                        state, "final_review", "Dossier ready for your review", dossier["headline_text"],
                        ["approve", "revise", "stop"], {"dossier": DOSSIER_FILE},
                    )
                    self._log(state, "dossier built")
                elif self._open(state, "final_review"):
                    state["phase"] = "waiting_for_you"
            return self._save(analysis_id, state)

    # ---- answering ------------------------------------------------------------------------

    def answer(self, analysis_id: str, checkpoint_id: str, decision: str, note: str | None = None) -> dict[str, Any]:
        if decision not in DECISIONS:
            raise RunWorkflowError(f"decision must be one of {sorted(DECISIONS)}.")
        analysis = self.analysis_service.get(analysis_id)
        with _LOCK:
            state = self.state(analysis_id)
            checkpoint = next((c for c in state.get("checkpoints", []) if c["id"] == checkpoint_id), None)
            if checkpoint is None:
                raise RunWorkflowError("No such checkpoint.", 404)
            if checkpoint["status"] != "open":
                raise RunWorkflowError("That checkpoint was already answered.", 409)
            checkpoint["status"] = "answered"
            checkpoint["answer"] = {"decision": decision, "note": (note or "").strip()[:2000], "at": utc_now_iso()}
            if decision == "stop":
                state["phase"] = "stopped"
            elif checkpoint["kind"] == "final_review":
                state["phase"] = "done" if decision == "approve" else "revising"
            self._log(state, f"{checkpoint['kind']}: {decision}")
            saved = self._save(analysis_id, state)
        self._record_feedback(analysis, checkpoint, decision, note)
        return saved

    def _record_feedback(self, analysis: Any, checkpoint: dict[str, Any], decision: str, note: str | None) -> None:
        if self.feedback is None:
            return
        action = {"approve": "approve", "revise": "reject", "stop": "reject"}[decision]
        try:
            self.feedback.add(
                analysis_id=analysis.analysis_id, target=f"checkpoint_{checkpoint['kind']}", action=action,
                reason=note, ticker=analysis.ticker, analysis_type=analysis.analysis_type, source="checkpoint",
                context={"checkpoint_id": checkpoint["id"], "decision": decision},
            )
        except Exception:  # noqa: BLE001 - logging feedback must not break the workflow
            pass

    # ---- dossier --------------------------------------------------------------------------

    def _read(self, analysis_id: str, name: str) -> dict[str, Any] | None:
        try:
            return self.output_service.read_json(analysis_id, name)
        except (FileNotFoundError, ValueError):
            return None

    def _build_dossier(self, analysis_id: str, with_take: bool) -> dict[str, Any]:
        analysis = self.analysis_service.get(analysis_id)
        final = self._read(analysis_id, "final_recommendation_report.json")
        engine = self._read(analysis_id, "analysis_engine_result.json")
        conflict = recommendation_conflict(final, engine)
        validation = self._read(analysis_id, "statement_validation_report.json") or {}
        review = self._read(analysis_id, "analyst_review_report.json") or {}

        flags = []
        if conflict["conflict"]:
            flags.append(conflict["message"])
        for label, report in (("statement validation", validation), ("analyst review", review)):
            fails = report.get("fail_count") or 0
            warns = report.get("warn_count") or 0
            if fails or warns:
                flags.append(f"{label}: {fails} failed, {warns} warnings")

        outside = self._gather_outside_evidence(analysis)
        take = self._my_take(analysis_id) if with_take else None

        headline = conflict["headline"] or "no recommendation"
        text = f"{analysis.company} ({analysis.ticker}): headline recommendation {headline}."
        if flags:
            text += " Needs attention: " + "; ".join(flags) + "."
        text += f" Outside evidence gathered: {len(outside['items'])} item(s)" + (f", {len(outside['errors'])} unavailable" if outside["errors"] else "") + "."
        if take and take.get("text"):
            text += " A labeled 'my take' is included."

        dossier = {
            "analysis_id": analysis_id, "built_at": utc_now_iso(), "company": analysis.company, "ticker": analysis.ticker,
            "headline": conflict, "flags": flags, "outside_evidence": outside, "my_take": take, "headline_text": text,
            "note": "Rules-based scores and the final recommendation are unchanged by outside evidence or 'my take'.",
        }
        write_json_atomic(self.output_service.analysis_output_dir(analysis_id) / DOSSIER_FILE, dossier)
        return dossier

    def _gather_outside_evidence(self, analysis: Any) -> dict[str, Any]:
        from research.policy import research_enabled
        if not research_enabled():
            return {"items": [], "errors": ["Online research is switched off."]}
        toolbox = self.research_factory(analysis) if self.research_factory else self._default_research(analysis)
        items: list[dict[str, Any]] = []
        errors: list[str] = []
        for name, args in (("get_recent_filings", {"forms": ["10-K", "10-Q", "8-K"]}), ("get_delayed_price", {}), ("search_news", {})):
            text, is_error = toolbox.execute(name, args)
            if is_error:
                errors.append(text)
        items = [e.to_dict() for e in toolbox.collected]
        return {"items": items, "errors": errors}

    def _default_research(self, analysis: Any) -> Any:
        from research.toolbox import ResearchToolbox
        record = analysis.to_dict()
        return ResearchToolbox(
            ticker=analysis.ticker, company=analysis.company, cik=record.get("cik"),
            evidence_log=self.output_service.analysis_output_dir(analysis.analysis_id) / "research_evidence.jsonl",
        )

    def _my_take(self, analysis_id: str) -> dict[str, Any]:
        """Optional paid step on the stronger model. Failure (no key, budget) is reported, never fatal."""
        if self.agent is None:
            return {"text": None, "error": "No agent configured."}
        from settings import strong_model
        try:
            reply = self.agent.chat(
                analysis_id,
                [{"role": "user", "content": "Write the 'my take' section for this analysis."}],
                model=strong_model(), purpose="my_take", extra_system=MY_TAKE_INSTRUCTIONS,
            )
        except Exception as exc:  # noqa: BLE001 - AgentError carries a clean message
            return {"text": None, "error": str(exc)}
        return {"text": reply.reply, "model": getattr(reply, "model", None), "label": "opinion, not HAP's rules-based result"}
