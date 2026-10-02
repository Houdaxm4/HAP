"""Checkpointed agent run: state machine, feedback capture, dossier labeling (no network, no AI)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agent.run_workflow import AgentRunService, RunWorkflowError
from models.analysis import CreateAnalysisRequest
from research.evidence import Evidence
from services.analysis_service import AnalysisService
from services.feedback_service import FeedbackService
from services.output_service import OutputService


class FakePipeline:
    def __init__(self, analyses, final_status="complete"):
        self.analyses, self.final_status, self.ran = analyses, final_status, 0

    def assert_ready_for_pipeline(self, analysis):
        pass

    def run(self, analysis_id):
        self.ran += 1
        a = self.analyses.get(analysis_id)
        a.status = self.final_status
        self.analyses.save(a)


class FakeResearch:
    def __init__(self):
        self.collected = []

    def execute(self, name, args):
        if name == "search_news":
            return "news failed", True
        self.collected.append(Evidence(kind="x", source="S", url="https://sec.gov", reliability="regulatory"))
        return "ok", False


class FakeAgent:
    def chat(self, aid, msgs, **kw):
        assert kw["purpose"] == "my_take" and "MY TAKE" in kw["extra_system"]
        return SimpleNamespace(reply="MY TAKE (opinion, not HAP's rules-based result). I lean cautious.", model="m")


@pytest.fixture
def env(tmp_path):
    analyses = AnalysisService(tmp_path / "a")
    outputs = OutputService(tmp_path / "o")
    feedback = FeedbackService(tmp_path / "f")
    a = analyses.create(CreateAnalysisRequest(company="Acme", ticker="acme", analysis_type="annual_update"))
    outputs.write_json(a.analysis_id, "final_recommendation_report.json", {"final_recommendation": "HOLD"})
    outputs.write_json(a.analysis_id, "analysis_engine_result.json", {"recommendation": {"recommendation": "WATCH"}})
    return SimpleNamespace(analyses=analyses, outputs=outputs, feedback=feedback, aid=a.analysis_id)


def service(env, status="complete", agent=None):
    return AgentRunService(
        analysis_service=env.analyses, output_service=env.outputs, pipeline=FakePipeline(env.analyses, status),
        feedback_service=env.feedback, agent=agent, research_factory=lambda a: FakeResearch(),
    )


def test_run_reaches_final_review_with_labeled_dossier(env):
    svc = service(env)
    assert svc.start(env.aid)["phase"] == "pipeline"
    state = svc.run(env.aid)
    assert svc.pipeline.ran == 1 and state["phase"] == "waiting_for_you"
    cp = state["checkpoints"][0]
    assert cp["kind"] == "final_review" and cp["status"] == "open"
    dossier = env.outputs.read_json(env.aid, "agent_dossier.json")
    assert dossier["headline"]["headline"] == "HOLD" and dossier["headline"]["conflict"]
    assert len(dossier["outside_evidence"]["items"]) == 2 and len(dossier["outside_evidence"]["errors"]) == 1
    assert dossier["my_take"] is None and "unchanged" in dossier["note"]


def test_advance_is_idempotent_and_answer_records_feedback(env):
    svc = service(env)
    svc.run(env.aid)
    svc.advance(env.aid)
    state = svc.advance(env.aid)
    assert len(state["checkpoints"]) == 1
    cp = state["checkpoints"][0]
    done = svc.answer(env.aid, cp["id"], "revise", "headline too bullish")
    assert done["phase"] == "revising" and done["checkpoints"][0]["status"] == "answered"
    with pytest.raises(RunWorkflowError) as exc:
        svc.answer(env.aid, cp["id"], "approve")
    assert exc.value.status_code == 409
    rows = env.feedback.list(analysis_id=env.aid)
    assert rows and rows[-1]["target"] == "checkpoint_final_review" and rows[-1]["reason"] == "headline too bullish"


def test_review_gate_and_failure_checkpoints(env):
    svc = service(env, status="awaiting_analyst_review")
    state = svc.run(env.aid)
    assert state["checkpoints"][0]["kind"] == "analyst_review"
    svc2 = service(env, status="failed")
    a = env.analyses.get(env.aid)
    a.status = "failed"
    env.analyses.save(a)
    assert svc2.advance(env.aid)["checkpoints"][-1]["kind"] == "pipeline_failed"


def test_my_take_is_labeled_and_failures_are_not_fatal(env):
    svc = service(env, agent=FakeAgent())
    svc.run(env.aid, with_take=True)
    take = env.outputs.read_json(env.aid, "agent_dossier.json")["my_take"]
    assert take["text"].startswith("MY TAKE") and "not HAP" in take["label"]


def test_invalid_decision_and_unknown_checkpoint(env):
    svc = service(env)
    svc.run(env.aid)
    with pytest.raises(RunWorkflowError):
        svc.answer(env.aid, "x", "maybe")
    with pytest.raises(RunWorkflowError) as exc:
        svc.answer(env.aid, "nope", "approve")
    assert exc.value.status_code == 404
