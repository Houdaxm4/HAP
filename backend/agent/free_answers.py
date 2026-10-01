"""Built-in (free) answers: common analyst questions answered from stored artifacts, no AI call.

Each answer is assembled by fixed code from one analysis's persisted results, so it costs
nothing, is instant, and can only say what the artifacts say. Anything open-ended,
hypothetical or opinion-seeking is deliberately NOT matched, so it falls through to Claude.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable

from services.analysis_service import AnalysisService
from services.lessons_service import LessonsService
from services.output_service import OutputService

# Questions like these need reasoning or judgment: never answer them from a template.
_NEEDS_REASONING = re.compile(
    r"\b(what if|what would|suppose|compare|versus|vs\.?|forecast|predict|should i (buy|sell|invest|hold|trust|worry|approve|override)|do you think|"
    r"your (view|take|opinion)|recommend (me|that i)|better than|explain in detail|walk me through|"
    r"calculate|recompute|how much would|why is it that)\b",
    re.IGNORECASE,
)
_CELL_REF = re.compile(r"([A-Za-z][A-Za-z0-9 &\-\.]{0,40}![A-Z]{1,3}[0-9]{1,5})")
MAX_QUESTION_CHARS = 400


@dataclass
class FreeAnswer:
    reply: str
    intent: str
    sources: list[str] = field(default_factory=list)


def _pct(value: Any, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%" if isinstance(value, (int, float)) else "n/a"


def _num(value: Any, digits: int = 1) -> str:
    return f"{value:.{digits}f}" if isinstance(value, (int, float)) else "n/a"


def _usd(value: Any) -> str:
    return f"${value:,.2f}" if isinstance(value, (int, float)) else "n/a"


def _label(text: Any) -> str:
    return str(text).replace("_", " ").title() if text else "n/a"


class FreeAnswerEngine:
    def __init__(
        self,
        analysis_service: AnalysisService,
        output_service: OutputService,
        lessons: LessonsService | None = None,
    ) -> None:
        self.analysis_service = analysis_service
        self.output_service = output_service
        self.lessons = lessons
        # (intent, keywords, handler); first strong match by keyword count wins.
        self._intents: list[tuple[str, tuple[str, ...], Callable[[str, str, Any], FreeAnswer | None]]] = [
            ("provenance", (), self._provenance),  # matched by cell reference, not keywords
            ("review", ("review", "waiting", "pending", "lease", "r&d", "useful life", "approve", "needs my"), self._review),
            ("validation", ("validation", "discrepan", "flag", "fail", "check", "problem", "issue", "error", "gate", "blocker"), self._validation),
            ("recommendation", ("recommend", "score", "drove", "driver", "intrinsic", "margin of safety", "valuation", "entry price", "buy", "hold", "watch", "confidence"), self._recommendation),
            ("risks", ("risk", "opportunit", "threat", "strength", "weakness"), self._risks),
            ("files", ("file", "artifact", "deliverable", "output", "download", "workbook", "report"), self._files),
            ("log", ("decision log", "what did the agent", "pipeline", "stage", "progress", "how long", "when was"), self._log),
            ("attention", ("summar", "overview", "status", "attention", "brief", "how is", "tell me about", "where do we stand", "what is the state"), self._attention),
        ]

    # ---- public ---------------------------------------------------------------------------

    def answer(self, analysis_id: str, question: str) -> FreeAnswer | None:
        text = (question or "").strip()
        if not text or len(text) > MAX_QUESTION_CHARS or _NEEDS_REASONING.search(text):
            return None
        lowered = text.lower()
        analysis = self.analysis_service.get(analysis_id)

        cell = _CELL_REF.search(text)
        if cell:
            # The pattern may swallow leading words ("Where does Income Statement!B5"); try shorter tails.
            words = cell.group(1).strip().split(" ")
            for start in range(len(words)):
                found = self._provenance(analysis_id, " ".join(words[start:]), analysis)
                if found is not None:
                    return found
            return None

        best: tuple[int, Callable[[str, str, Any], FreeAnswer | None]] | None = None
        for _, keywords, handler in self._intents:
            if not keywords:
                continue
            hits = sum(1 for k in keywords if k in lowered)
            if hits and (best is None or hits > best[0]):
                best = (hits, handler)
        if best is None:
            return None
        return best[1](analysis_id, lowered, analysis)

    # ---- helpers --------------------------------------------------------------------------

    def _json(self, analysis_id: str, name: str) -> dict[str, Any] | None:
        try:
            data = self.output_service.read_json(analysis_id, name)
        except (FileNotFoundError, ValueError, OSError):
            return None
        return data if isinstance(data, dict) else None

    def _header(self, analysis: Any) -> str:
        return f"{analysis.company} ({analysis.ticker}) | {_label(analysis.analysis_type)} | status: {analysis.status}"

    # ---- intents --------------------------------------------------------------------------

    def _provenance(self, analysis_id: str, cell_ref: str, analysis: Any = None) -> FreeAnswer | None:
        report = self._json(analysis_id, "provenance_report.json")
        if not report:
            return None
        for entry in report.get("entries", []):
            if str(entry.get("cell_ref", "")).lower() == cell_ref.lower():
                lines = [f"Provenance for {entry.get('cell_ref')}:"]
                for key, value in entry.items():
                    if key == "cell_ref" or value in (None, "", [], {}):
                        continue
                    shown = str(value)
                    lines.append(f"- {_label(key)}: {shown[:300]}")
                return FreeAnswer("\n".join(lines), "provenance", ["provenance_report.json"])
        return None

    def _recommendation(self, analysis_id: str, q: str, analysis: Any) -> FreeAnswer | None:
        final = self._json(analysis_id, "final_recommendation_report.json")
        engine = self._json(analysis_id, "analysis_engine_result.json")
        if not final and not engine:
            return None
        lines = [self._header(analysis), ""]
        sources: list[str] = []
        if final:
            sources.append("final_recommendation_report.json")
            lines.append(
                f"Final report: {final.get('recommendation_label') or _label(final.get('final_recommendation'))} "
                f"(confidence {_num(final.get('confidence'), 2)})."
            )
            lines.append(
                f"- Business quality: {_num(final.get('business_quality_score'))} "
                f"({_label(final.get('business_quality_classification'))}); investment attractiveness: "
                f"{_num(final.get('investment_attractiveness_score'))} ({_label(final.get('investment_attractiveness_classification'))})."
            )
            lines.append(
                f"- Valuation: price {_usd(final.get('current_price'))}, intrinsic value {_usd(final.get('intrinsic_value'))}, "
                f"margin of safety {_pct(final.get('margin_of_safety'))}, entry price {_usd(final.get('entry_price'))}; "
                f"valuation status {_label(final.get('valuation_status'))}, expected return {_label(final.get('expected_return_status'))}."
            )
            if final.get("recommendation_rationale"):
                lines.append(f"- Rationale: {final['recommendation_rationale']}")
            for title, key in (("For", "reasons_for"), ("Against", "reasons_against"), ("Key risks", "key_risks")):
                items = final.get(key) or []
                if items:
                    lines.append(f"- {title}: " + " | ".join(str(i) for i in items[:4]))
        if engine and isinstance(engine.get("recommendation"), dict):
            sources.append("analysis_engine_result.json")
            rec = engine["recommendation"]
            lines.append("")
            lines.append(
                f"Analysis engine: {rec.get('recommendation_label') or rec.get('recommendation')} "
                f"(confidence {_num(rec.get('confidence'), 2)}); business quality {_num(rec.get('business_quality_score'))}, "
                f"investment attractiveness {_num(rec.get('investment_attractiveness_score'))} "
                f"({_label(rec.get('investment_attractiveness_classification'))})."
            )
            if final and str(final.get("final_recommendation", "")).upper() != str(rec.get("recommendation", "")).upper():
                lines.append(
                    f"WARNING: the final report ({final.get('final_recommendation')}) and the analysis engine "
                    f"({rec.get('recommendation')}) disagree. The final report (workbook-based) is the headline "
                    "recommendation; the engine view is shown for comparison and needs your review."
                )
        lines.append("")
        lines.append("Sources: " + ", ".join(sources))
        return FreeAnswer("\n".join(lines), "recommendation", sources)

    def _validation(self, analysis_id: str, q: str, analysis: Any) -> FreeAnswer | None:
        stmt = self._json(analysis_id, "statement_validation_report.json")
        disc = self._json(analysis_id, "discrepancy_report.json")
        review = self._json(analysis_id, "analyst_review_report.json")
        gate = self._json(analysis_id, "new_company_output_gate_report.json")
        if not any((stmt, disc, review, gate)):
            return None
        lines = [self._header(analysis), ""]
        sources: list[str] = []
        if stmt:
            sources.append("statement_validation_report.json")
            lines.append(
                f"Statement validation: {stmt.get('validated_count', 0)} validated, {stmt.get('discrepancy_count', 0)} discrepancies, "
                f"{stmt.get('review_required_count', 0)} review required, {stmt.get('source_missing_count', 0)} source missing, "
                f"{stmt.get('not_comparable_count', 0)} not comparable."
            )
        if disc:
            sources.append("discrepancy_report.json")
            lines.append(
                f"Cell checks: {disc.get('fail_count', 0)} failed, {disc.get('warn_count', 0)} warnings, {disc.get('pass_count', 0)} passed. "
                "Values are never silently overwritten."
            )
        if review:
            sources.append("analyst_review_report.json")
            lines.append(
                f"Analyst-review findings: {review.get('material_count', 0)} material, {review.get('watch_count', 0)} watch, "
                f"{review.get('info_count', 0)} info."
            )
            material = [f for f in review.get("findings", []) if str(f.get("severity")).upper() == "MATERIAL"][:5]
            for f in material:
                lines.append(
                    f"  - [{f.get('severity')}] {f.get('statement')} / {f.get('metric')} / {f.get('period')}: "
                    f"{str(f.get('observation'))[:200]} (status: {f.get('status')})"
                )
        if gate:
            sources.append("new_company_output_gate_report.json")
            lines.append(
                f"Output gates: {gate.get('status')}; blockers {len(gate.get('blockers') or [])}, warnings {len(gate.get('warnings') or [])}, "
                f"report authorized: {gate.get('report_authorized')}."
            )
            for w in (gate.get("blockers") or [])[:3]:
                lines.append(f"  - BLOCKER: {str(w)[:200]}")
            for w in (gate.get("warnings") or [])[:3]:
                lines.append(f"  - warning: {str(w)[:200]}")
        lines.append("")
        lines.append("Sources: " + ", ".join(sources))
        return FreeAnswer("\n".join(lines), "validation", sources)

    def _review(self, analysis_id: str, q: str, analysis: Any) -> FreeAnswer | None:
        lease = self._json(analysis_id, "lease_rate_review.json")
        rd = self._json(analysis_id, "rd_useful_life_decision.json")
        state = self._json(analysis_id, "new_company_run_state.json")
        review = self._json(analysis_id, "analyst_review_report.json")
        if not any((lease, rd, state, review)):
            return None
        lines = [self._header(analysis), ""]
        sources: list[str] = []
        if lease:
            sources.append("lease_rate_review.json")
            lines.append(
                f"Lease discount rate: status {lease.get('status')}; proposed {_pct(lease.get('proposed_rate'), 2)}, "
                f"selected {_pct(lease.get('selected_rate'), 2)}, approved by analyst: "
                f"{_pct(lease.get('approved_rate'), 2) if lease.get('approved_rate') is not None else 'not yet'}. "
                f"Decision class: {lease.get('decision_class')}; basis: {lease.get('classification')}."
            )
            for e in (lease.get("supporting_evidence") or [])[:2]:
                lines.append(f"  - Evidence: {str(e)[:200]}")
        if rd:
            sources.append("rd_useful_life_decision.json")
            lines.append(
                f"R&D useful life: {rd.get('selected_useful_life')} years (allowed {rd.get('permitted_range')}), "
                f"confidence {_num(rd.get('confidence'), 2)}. {str(rd.get('rationale') or '')[:240]}"
            )
        if state:
            sources.append("new_company_run_state.json")
            lines.append(
                f"Workflow state: {state.get('workflow_state')}; lease rate approved by analyst: {state.get('lease_rate_approved')}; "
                f"R&D life overridden: {state.get('rd_life_overridden')}."
            )
        if review:
            sources.append("analyst_review_report.json")
            open_items = [f for f in review.get("findings", []) if f.get("status") == "open"]
            lines.append(f"Open analyst-review findings: {len(open_items)} ({review.get('material_count', 0)} material in total).")
        if self.lessons:
            relevant = self.lessons.approved(analysis.analysis_type, {"lease_rate", "rd_useful_life"})
            if relevant:
                lines.append("")
                lines.append("Lessons you approved from past corrections:")
                for item in relevant[:4]:
                    lines.append(f"  - {item['text']}")
                sources.append("lessons library")
        lines.append("")
        lines.append("To approve or change these, use the Review tab. This assistant cannot approve anything.")
        lines.append("Sources: " + ", ".join(sources))
        return FreeAnswer("\n".join(lines), "review", sources)

    def _risks(self, analysis_id: str, q: str, analysis: Any) -> FreeAnswer | None:
        engine = self._json(analysis_id, "analysis_engine_result.json")
        final = self._json(analysis_id, "final_recommendation_report.json")
        if not engine and not final:
            return None
        lines = [self._header(analysis), ""]
        sources: list[str] = []
        if engine:
            sources.append("analysis_engine_result.json")
            risks = engine.get("risks") or []
            opps = engine.get("opportunities") or []
            lines.append(f"Engine-detected risks ({len(risks)}):")
            for r in risks[:6]:
                lines.append(f"  - [{r.get('severity')}] {r.get('summary') or r.get('code')}")
            lines.append(f"Engine-detected opportunities ({len(opps)}):")
            for o in opps[:6]:
                lines.append(f"  - {o.get('summary') or o.get('code')}")
        if final and final.get("key_risks"):
            sources.append("final_recommendation_report.json")
            lines.append("Key risks in the final report:")
            for r in final["key_risks"][:5]:
                lines.append(f"  - {r}")
        lines.append("")
        lines.append("Sources: " + ", ".join(sources))
        return FreeAnswer("\n".join(lines), "risks", sources)

    def _files(self, analysis_id: str, q: str, analysis: Any) -> FreeAnswer | None:
        artifacts = self.output_service.list_artifacts(analysis_id)
        if not artifacts:
            return None
        deliverables = [a for a in artifacts if a["name"].lower().endswith((".xlsx", ".docx"))]
        reports = [a for a in artifacts if a["name"].lower().endswith(".md")]
        lines = [self._header(analysis), "", f"{len(artifacts)} stored artifacts."]
        if deliverables:
            lines.append("Deliverables (Excel and Word):")
            for a in deliverables:
                lines.append(f"  - {a['name']} ({a['size_bytes'] // 1024} KB)")
        if reports:
            lines.append("Written reports: " + ", ".join(a["name"] for a in reports))
        lines.append("Download them from the Deliverables tab.")
        return FreeAnswer("\n".join(lines), "files", ["(artifact list)"])

    def _log(self, analysis_id: str, q: str, analysis: Any) -> FreeAnswer | None:
        record = analysis.to_dict()
        pipeline = record.get("pipeline") or {}
        log = record.get("decision_log") or []
        lines = [
            self._header(analysis),
            "",
            f"Pipeline: {pipeline.get('state')} at stage '{pipeline.get('current_stage')}' ({pipeline.get('progress_pct')}%), "
            f"started {pipeline.get('started_at')}, completed {pipeline.get('completed_at')}.",
        ]
        if pipeline.get("error"):
            lines.append(f"ERROR: {pipeline['error']}")
        if pipeline.get("stages_completed"):
            lines.append("Stages completed: " + ", ".join(pipeline["stages_completed"]))
        if log:
            lines.append(f"Decision log ({len(log)} entries; latest 8):")
            for entry in log[-8:]:
                lines.append(f"  - {entry.get('timestamp', '')[:19]} {entry.get('agent')}: {entry.get('action')} - {str(entry.get('detail'))[:180]}")
        return FreeAnswer("\n".join(lines), "log", ["(analysis record)"])

    def _attention(self, analysis_id: str, q: str, analysis: Any) -> FreeAnswer | None:
        lines = [self._header(analysis), ""]
        sources: list[str] = []
        record = analysis.to_dict()
        pipeline = record.get("pipeline") or {}
        if pipeline.get("error"):
            lines.append(f"ATTENTION - pipeline error: {pipeline['error']}")
        final = self._json(analysis_id, "final_recommendation_report.json")
        engine = self._json(analysis_id, "analysis_engine_result.json")
        if final:
            sources.append("final_recommendation_report.json")
            lines.append(
                f"Final recommendation: {final.get('recommendation_label')} "
                f"(confidence {_num(final.get('confidence'), 2)}); margin of safety {_pct(final.get('margin_of_safety'))}."
            )
        if engine and isinstance(engine.get("recommendation"), dict):
            sources.append("analysis_engine_result.json")
            rec = engine["recommendation"]
            lines.append(f"Engine recommendation: {rec.get('recommendation_label')} (confidence {_num(rec.get('confidence'), 2)}).")
            if final and str(final.get("final_recommendation", "")).upper() != str(rec.get("recommendation", "")).upper():
                lines.append("ATTENTION - the final report and the analysis engine disagree on the recommendation and scores.")
        stmt = self._json(analysis_id, "statement_validation_report.json")
        review = self._json(analysis_id, "analyst_review_report.json")
        if stmt:
            sources.append("statement_validation_report.json")
            if stmt.get("discrepancy_count") or stmt.get("review_required_count"):
                lines.append(
                    f"ATTENTION - {stmt.get('discrepancy_count', 0)} statement discrepancies and "
                    f"{stmt.get('review_required_count', 0)} items needing review."
                )
        if review and review.get("material_count"):
            sources.append("analyst_review_report.json")
            lines.append(f"ATTENTION - {review['material_count']} material analyst-review findings.")
        lease = self._json(analysis_id, "lease_rate_review.json")
        if lease and lease.get("approved_rate") is None:
            sources.append("lease_rate_review.json")
            lines.append(f"Waiting on you: lease rate {_pct(lease.get('selected_rate'), 2)} was selected by the agent and is not yet approved.")
        gate = self._json(analysis_id, "new_company_output_gate_report.json")
        if gate and (gate.get("blockers") or gate.get("warnings")):
            sources.append("new_company_output_gate_report.json")
            lines.append(f"Output gates: {len(gate.get('blockers') or [])} blockers, {len(gate.get('warnings') or [])} warnings.")
        if len(lines) <= 2:
            return None
        lines.append("")
        lines.append("Ask for details on any point (recommendation, validation, review) for more. Sources: " + ", ".join(sources))
        return FreeAnswer("\n".join(lines), "attention", sources)
