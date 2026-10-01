"""Feedback store and monthly Claude budget guard."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from agent import AgentError, AnalystAgent
from models.analysis import CreateAnalysisRequest
from services.analysis_service import AnalysisService
from services.budget_service import (
    BudgetExceededError,
    BudgetService,
    estimate_cost_usd,
    price_for,
)
from services.feedback_service import FeedbackError, FeedbackService
from services.output_service import OutputService


# ---------------------------------------------------------------------------- budget


def test_prices_and_unknown_models_are_conservative():
    assert price_for("claude-sonnet-5-5") == (2.0, 10.0)
    assert price_for("claude-opus-5-5-20260401") == (4.0, 20.0)  # prefix match
    assert price_for("some-new-model") == (10.0, 50.0)  # priced high so a typo cannot dodge the cap
    assert estimate_cost_usd("claude-sonnet-5-5", 1_000_000, 100_000) == pytest.approx(3.0)


def test_budget_records_status_and_blocks_at_the_cap(tmp_path):
    budget = BudgetService(tmp_path, cap_usd=1.0)
    assert budget.status()["level"] == "ok"
    budget.record(analysis_id="a1", model="claude-sonnet-5-5", input_tokens=300_000, output_tokens=30_000)  # $0.90
    status = budget.status()
    assert status["level"] == "warning" and status["spent_usd"] == pytest.approx(0.9)
    budget.assert_available()  # warning still allowed
    budget.record(analysis_id="a1", model="claude-sonnet-5-5", input_tokens=100_000, output_tokens=10_000)  # +$0.30
    assert budget.status()["level"] == "exceeded"
    with pytest.raises(BudgetExceededError, match="used up"):
        budget.assert_available()


def test_budget_is_per_month(tmp_path):
    budget = BudgetService(tmp_path, cap_usd=5.0)
    budget.record(analysis_id=None, model="claude-sonnet-5-5", input_tokens=1000, output_tokens=1000)
    assert budget.spent_usd("1999-01") == 0.0
    assert budget.spent_usd() > 0
    assert BudgetService.month_key(datetime(2026, 3, 9, tzinfo=timezone.utc)) == "2026-03"


def test_corrupt_usage_lines_do_not_break_status(tmp_path):
    budget = BudgetService(tmp_path, cap_usd=5.0)
    budget.record(analysis_id=None, model="claude-sonnet-5-5", input_tokens=1000, output_tokens=0)
    path = budget._file(budget.month_key())
    with path.open("a", encoding="utf-8") as handle:
        handle.write("{not json\n")
    assert budget.status()["spent_usd"] >= 0


def test_agent_records_usage_and_refuses_when_over_budget(tmp_path):
    analyses = AnalysisService(tmp_path / "analyses")
    outputs = OutputService(tmp_path / "outputs")
    aid = analyses.create(CreateAnalysisRequest(company="B Co", ticker="b", analysis_type="annual_update")).analysis_id
    budget = BudgetService(tmp_path / "usage", cap_usd=0.0001)

    class Client:
        def __init__(self):
            self.calls = 0
            outer = self

            class M:
                def create(self, **kw):
                    outer.calls += 1
                    return SimpleNamespace(
                        content=[SimpleNamespace(type="text", text="hi")],
                        stop_reason="end_turn",
                        model="claude-sonnet-5-5",
                        usage=SimpleNamespace(input_tokens=50_000, output_tokens=5_000),
                    )

            self.messages = M()
            self.beta = SimpleNamespace(messages=self.messages)

    client = Client()
    agent = AnalystAgent(analyses, outputs, client_factory=lambda: client, budget_service=budget)
    reply = agent.chat(aid, [{"role": "user", "content": "hello"}])
    assert reply.budget["level"] == "exceeded" and client.calls == 1
    with pytest.raises(AgentError) as exc:
        agent.chat(aid, [{"role": "user", "content": "again"}])
    assert exc.value.status_code == 429 and client.calls == 1  # no second paid call


# ---------------------------------------------------------------------------- feedback


def test_feedback_roundtrip_and_validation(tmp_path):
    fb = FeedbackService(tmp_path)
    rec = fb.add(
        analysis_id="a1", target="lease_rate", action="correct", agent_value=0.04, analyst_value=0.06,
        reason="Company disclosed 6% in the lease note", ticker="LNN",
    )
    assert rec["analyst_value"] == 0.06 and rec["id"]
    fb.add(analysis_id="a1", target="lease_rate", action="approve", agent_value=0.04, analyst_value=0.04)
    fb.add(analysis_id="a2", target="chat_answer", action="thumbs_down", reason="wrong year")
    assert len(fb.list(analysis_id="a1")) == 2
    assert fb.list(target="chat_answer")[0]["reason"] == "wrong year"

    summary = fb.summary()
    lease = summary["targets"]["lease_rate"]
    assert lease["decisions"] == 2 and lease["correction_rate"] == 0.5
    assert summary["targets"]["chat_answer"]["thumbs_down"] == 1

    with pytest.raises(FeedbackError):
        fb.add(analysis_id="a1", target="lease_rate", action="correct")  # a correction needs the new value
    with pytest.raises(FeedbackError):
        fb.add(analysis_id="a1", target="Bad Target!", action="approve")
    with pytest.raises(FeedbackError):
        fb.add(analysis_id="a1", target="x", action="nonsense")
    with pytest.raises(FeedbackError):
        fb.add(analysis_id="a1", target="x", action="comment", reason="r" * 5000)
    with pytest.raises(ValueError):
        fb.add(analysis_id="../escape", target="x", action="comment")


def test_torn_feedback_line_is_ignored(tmp_path):
    fb = FeedbackService(tmp_path)
    fb.add(analysis_id="a1", target="t", action="comment", reason="ok")
    with fb.path.open("a", encoding="utf-8") as handle:
        handle.write('{"broken": \n')
    assert len(fb.list()) == 1


# ---------------------------------------------------------------------------- endpoints


@pytest.fixture
def api(tmp_path, monkeypatch):
    analyses = AnalysisService(tmp_path / "analyses")
    outputs = OutputService(tmp_path / "outputs")
    monkeypatch.setattr(main, "analysis_service", analyses)
    monkeypatch.setattr(main, "output_service", outputs)
    monkeypatch.setattr(main, "feedback_service", FeedbackService(tmp_path / "fb"))
    monkeypatch.setattr(main, "budget_service", BudgetService(tmp_path / "usage", cap_usd=20.0))
    aid = analyses.create(CreateAnalysisRequest(company="Api Co", ticker="api", analysis_type="new_company")).analysis_id
    return SimpleNamespace(client=TestClient(main.app), aid=aid, outputs=outputs)


def test_feedback_endpoints(api):
    res = api.client.post(f"/analysis/{api.aid}/feedback", json={"target": "chat_answer", "action": "thumbs_up", "reason": "clear"})
    assert res.status_code == 200 and res.json()["ticker"] == "API"
    bad = api.client.post(f"/analysis/{api.aid}/feedback", json={"target": "lease_rate", "action": "correct"})
    assert bad.status_code == 400
    assert api.client.post("/analysis/nope/feedback", json={"target": "t", "action": "comment"}).status_code == 404
    listing = api.client.get(f"/analysis/{api.aid}/feedback").json()
    assert len(listing["items"]) == 1
    assert api.client.get("/feedback/summary").json()["targets"]["chat_answer"]["thumbs_up"] == 1


def test_budget_endpoint(api):
    status = api.client.get("/budget").json()
    assert status["cap_usd"] == 20.0 and status["level"] == "ok"


def test_review_gate_decisions_are_logged_as_feedback(api, monkeypatch):
    api.outputs.write_json(api.aid, "lease_rate_review.json", {"proposed_rate": 0.04})
    api.outputs.write_json(api.aid, "rd_useful_life_decision.json", {"selected_useful_life": 5})
    monkeypatch.setattr(main.pipeline_orchestrator, "finalize_new_company_review", lambda analysis, **kw: analysis)
    r1 = api.client.post(
        f"/analysis/{api.aid}/analyst-review/lease-rate", json={"action": "correct", "rate": 0.06, "reason": "10-K note"}
    )
    r2 = api.client.post(f"/analysis/{api.aid}/analyst-review/rd-useful-life", json={"useful_life": 5})
    r3 = api.client.post(
        f"/analysis/{api.aid}/analyst-review/rd-useful-life", json={"useful_life": 7, "reason": "long patents"}
    )
    assert (r1.status_code, r2.status_code, r3.status_code) == (200, 200, 200)

    rows = main.feedback_service.list(analysis_id=api.aid)
    by = {(r["target"], r["action"]): r for r in rows}
    lease = by[("lease_rate", "correct")]
    assert lease["agent_value"] == 0.04 and lease["analyst_value"] == 0.06
    assert ("rd_useful_life", "approve") in by and ("rd_useful_life", "correct") in by
    assert by[("rd_useful_life", "correct")]["analyst_value"] == 7


def test_feedback_logging_failure_never_breaks_a_review(api, monkeypatch):
    api.outputs.write_json(api.aid, "lease_rate_review.json", {"proposed_rate": 0.04})
    monkeypatch.setattr(main.pipeline_orchestrator, "finalize_new_company_review", lambda analysis, **kw: analysis)

    def boom(**kw):
        raise RuntimeError("disk full")

    monkeypatch.setattr(main.feedback_service, "add", boom)
    res = api.client.post(f"/analysis/{api.aid}/analyst-review/lease-rate", json={"action": "approve"})
    assert res.status_code == 200
