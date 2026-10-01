"""Lessons library: propose from repeated feedback, approve/reject, apply (advisory only)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from agent import AnalystAgent
from agent.free_answers import FreeAnswerEngine
from agent.service import AnalystService
from models.analysis import CreateAnalysisRequest
from services.analysis_service import AnalysisService
from services.answer_cache import AnswerCache
from services.budget_service import BudgetService
from services.feedback_service import FeedbackService
from services.lessons_service import LessonError, LessonsService
from services.output_service import OutputService


@pytest.fixture
def lib(tmp_path):
    fb = FeedbackService(tmp_path / "fb")
    return SimpleNamespace(fb=fb, svc=LessonsService(tmp_path / "lessons", feedback=fb), tmp=tmp_path)


def add_lease_feedback(fb, n_correct=3, analysis_type="new_company"):
    for i, new in enumerate([0.06, 0.05, 0.07][:n_correct]):
        fb.add(analysis_id=f"a{i}", target="lease_rate", action="correct", agent_value=0.04, analyst_value=new,
               reason="Company disclosed a higher rate in the lease note", analysis_type=analysis_type)
    fb.add(analysis_id="a9", target="lease_rate", action="approve", agent_value=0.04, analyst_value=0.04, analysis_type=analysis_type)


# ---------------------------------------------------------------------------- proposing


def test_repeated_corrections_become_a_proposed_lesson(lib):
    add_lease_feedback(lib.fb)
    created = lib.svc.propose_from_feedback()
    assert len(created) == 1
    lesson = created[0]
    assert lesson["status"] == "proposed" and lesson["target"] == "lease_rate" and lesson["analysis_type"] == "new_company"
    assert "3 of 4" in lesson["text"] and "higher" in lesson["text"] and "disclosed a higher rate" in lesson["text"]
    assert lesson["support_count"] == 3 and len(lesson["evidence"]) == 3


def test_proposing_is_idempotent_and_needs_enough_evidence(lib, monkeypatch):
    add_lease_feedback(lib.fb, n_correct=2)
    assert lib.svc.propose_from_feedback() == []  # only 2 corrections, threshold is 3
    monkeypatch.setenv("HAP_LESSON_MIN_SUPPORT", "2")
    assert len(lib.svc.propose_from_feedback()) == 1
    assert lib.svc.propose_from_feedback() == []  # same pattern is not proposed twice


def test_chat_thumbs_down_with_reasons_becomes_a_lesson(lib):
    for i in range(3):
        lib.fb.add(analysis_id=f"c{i}", target="chat_answer", action="thumbs_down", reason=f"wrong fiscal year {i}", analysis_type="annual_update")
    lib.fb.add(analysis_id="c9", target="chat_answer", action="thumbs_down", analysis_type="annual_update")  # no reason: not counted
    lesson = lib.svc.propose_from_feedback()[0]
    assert lesson["kind"] == "chat_quality" and "wrong fiscal year" in lesson["text"] and lesson["support_count"] == 3


def test_patterns_are_kept_separate_per_analysis_type(lib):
    add_lease_feedback(lib.fb, analysis_type="new_company")
    add_lease_feedback(lib.fb, analysis_type="annual_update")
    assert {item["analysis_type"] for item in lib.svc.propose_from_feedback()} == {"new_company", "annual_update"}


# ---------------------------------------------------------------------------- decisions


def test_approve_edit_reject_retire_flow(lib):
    add_lease_feedback(lib.fb)
    lesson = lib.svc.propose_from_feedback()[0]
    approved = lib.svc.approve(lesson["id"], text="  Always check the lease note first.  ", note="agreed")
    assert approved["status"] == "approved" and approved["text"] == "Always check the lease note first." and approved["decided_at"]
    with pytest.raises(LessonError):
        lib.svc.approve(lesson["id"])  # already approved
    assert lib.svc.retire(lesson["id"])["status"] == "retired"
    with pytest.raises(LessonError):
        lib.svc.retire(lesson["id"])
    with pytest.raises(LessonError):
        lib.svc.reject(lesson["id"])  # only proposed lessons can be rejected
    with pytest.raises(LessonError, match="not found"):
        lib.svc.approve("nope")
    with pytest.raises(LessonError):
        lib.svc.approve(lesson["id"], text="   ")  # empty wording


def test_rejected_lessons_are_not_proposed_again(lib):
    add_lease_feedback(lib.fb)
    lesson = lib.svc.propose_from_feedback()[0]
    lib.svc.reject(lesson["id"], note="not a real pattern")
    assert lib.svc.propose_from_feedback() == []
    assert [x["status"] for x in lib.svc.list()] == ["rejected"]


def test_list_filters(lib):
    add_lease_feedback(lib.fb)
    lesson = lib.svc.propose_from_feedback()[0]
    assert lib.svc.list(status="approved") == []
    lib.svc.approve(lesson["id"])
    assert len(lib.svc.list(status="approved", analysis_type="new_company")) == 1
    assert lib.svc.list(status="approved", analysis_type="annual_update") == []
    with pytest.raises(LessonError):
        lib.svc.list(status="bogus")


# ---------------------------------------------------------------------------- applying (advisory)


def test_only_approved_lessons_are_applied_and_the_version_changes(lib):
    add_lease_feedback(lib.fb)
    lesson = lib.svc.propose_from_feedback()[0]
    assert lib.svc.prompt_lines("new_company") == []
    v0 = lib.svc.version("new_company")
    lib.svc.approve(lesson["id"])
    assert len(lib.svc.prompt_lines("new_company")) == 1 and lib.svc.prompt_lines("annual_update") == []
    v1 = lib.svc.version("new_company")
    assert v1 != v0
    lib.svc.retire(lesson["id"])
    assert lib.svc.prompt_lines("new_company") == [] and lib.svc.version("new_company") == v0


def env_for_agent(tmp_path, lessons):
    analyses = AnalysisService(tmp_path / "analyses")
    outputs = OutputService(tmp_path / "outputs")
    aid = analyses.create(CreateAnalysisRequest(company="L Co", ticker="l", analysis_type="new_company")).analysis_id
    outputs.write_json(aid, "lease_rate_review.json", {"status": "autonomous_selected", "proposed_rate": 0.04, "selected_rate": 0.04,
                                                       "approved_rate": None, "decision_class": "AUTONOMOUS_AGENT_DECISION"})
    return analyses, outputs, aid


class CapturingClient:
    def __init__(self):
        self.systems: list[str] = []
        outer = self

        class M:
            def create(self, **kw):
                outer.systems.append(kw["system"])
                return SimpleNamespace(content=[SimpleNamespace(type="text", text="ok")], stop_reason="end_turn",
                                       model="claude-sonnet-5-5", usage=SimpleNamespace(input_tokens=10, output_tokens=5))

        self.messages = M()
        self.beta = SimpleNamespace(messages=self.messages)


def test_approved_lessons_reach_the_agent_instructions_and_free_review_answers(lib):
    add_lease_feedback(lib.fb)
    lesson = lib.svc.propose_from_feedback()[0]
    lib.svc.approve(lesson["id"], text="Check the lease note before trusting the agent's rate.")
    analyses, outputs, aid = env_for_agent(lib.tmp, lib.svc)

    client = CapturingClient()
    agent = AnalystAgent(analyses, outputs, client_factory=lambda: client,
                         budget_service=BudgetService(lib.tmp / "usage", cap_usd=20), lessons_service=lib.svc)
    agent.chat(aid, [{"role": "user", "content": "hi"}])
    assert "Check the lease note before trusting the agent's rate." in client.systems[0]
    assert "never override evidence" in client.systems[0]

    free = FreeAnswerEngine(analyses, outputs, lessons=lib.svc).answer(aid, "What is waiting for my review?")
    assert "Lessons you approved" in free.reply and "Check the lease note" in free.reply


def test_new_lessons_retire_remembered_answers(lib):
    add_lease_feedback(lib.fb)
    lesson = lib.svc.propose_from_feedback()[0]
    analyses, outputs, aid = env_for_agent(lib.tmp, lib.svc)
    client = CapturingClient()
    budget = BudgetService(lib.tmp / "usage", cap_usd=20)
    agent = AnalystAgent(analyses, outputs, client_factory=lambda: client, budget_service=budget, lessons_service=lib.svc)
    svc = AnalystService(analyses, outputs, agent, budget, AnswerCache(lib.tmp / "cache"), lessons=lib.svc)

    q = [{"role": "user", "content": "What if the lease rate were 6%?"}]
    assert svc.answer(aid, q, mode="claude").source == "claude"
    assert svc.answer(aid, q, mode="claude").source == "cache"
    lib.svc.approve(lesson["id"])  # the analyst's guidance changed, so the old answer is stale
    assert svc.answer(aid, q, mode="claude").source == "claude"
    assert len(client.systems) == 2


# ---------------------------------------------------------------------------- endpoints


def test_lessons_endpoints(lib, monkeypatch):
    monkeypatch.setattr(main, "lessons_service", lib.svc)
    add_lease_feedback(lib.fb)
    api = TestClient(main.app)

    assert api.get("/lessons").json() == {"items": []}
    created = api.post("/lessons/propose").json()
    assert created["count"] == 1
    lesson_id = created["created"][0]["id"]
    assert api.post("/lessons/propose").json()["count"] == 0

    assert api.get("/lessons", params={"status": "proposed"}).json()["items"][0]["id"] == lesson_id
    assert api.get("/lessons", params={"status": "bogus"}).status_code == 400

    ok = api.post(f"/lessons/{lesson_id}/approve", json={"text": "Edited wording.", "note": "yes"})
    assert ok.status_code == 200 and ok.json()["status"] == "approved" and ok.json()["text"] == "Edited wording."
    assert api.post(f"/lessons/{lesson_id}/approve").status_code == 400
    assert api.post("/lessons/doesnotexist/approve").status_code == 404
    assert api.post(f"/lessons/{lesson_id}/retire").json()["status"] == "retired"
    assert api.post(f"/lessons/{lesson_id}/reject").status_code == 400
