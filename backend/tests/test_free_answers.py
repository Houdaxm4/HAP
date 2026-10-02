"""Free built-in answers, remembered answers, and the 'Ask Claude only on request' router."""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from agent import AnalystAgent
from agent.free_answers import FreeAnswerEngine
from agent.service import NEEDS_CLAUDE_TEXT, AnalystService
from models.analysis import CreateAnalysisRequest
from services.analysis_service import AnalysisService
from services.answer_cache import AnswerCache, normalize_question
from services.budget_service import BudgetService
from services.feedback_service import FeedbackService
from services.output_service import OutputService


@pytest.fixture
def env(tmp_path):
    analyses = AnalysisService(tmp_path / "analyses")
    outputs = OutputService(tmp_path / "outputs")
    aid = analyses.create(CreateAnalysisRequest(company="Lindsay Corp", ticker="lnn", analysis_type="new_company")).analysis_id
    outputs.write_json(aid, "final_recommendation_report.json", {
        "final_recommendation": "HOLD", "recommendation_label": "Hold", "confidence": 0.2,
        "business_quality_score": 65.0, "business_quality_classification": "AVERAGE_BUSINESS",
        "investment_attractiveness_score": 88.0, "investment_attractiveness_classification": "ATTRACTIVE_OPPORTUNITY",
        "current_price": 116.59, "intrinsic_value": 268.14, "margin_of_safety": 0.5652, "entry_price": 201.1,
        "valuation_status": "ATTRACTIVE", "expected_return_status": "SOURCE_MISSING",
        "recommendation_rationale": "HOLD synthesizes Business Quality with Investment Attractiveness.",
        "reasons_for": ["Margin of safety 56.5% above the 25% threshold."], "reasons_against": ["ROIC evidence is thin."],
        "key_risks": ["9 unresolved statement discrepancies."],
    })
    outputs.write_json(aid, "analysis_engine_result.json", {
        "recommendation": {"recommendation": "WATCH", "recommendation_label": "Watch", "confidence": 0.4857,
                           "business_quality_score": 61.35, "investment_attractiveness_score": 67.5,
                           "investment_attractiveness_classification": "FAIRLY_VALUED"},
        "risks": [{"severity": "warning", "summary": "Weak Organic Growth"}],
        "opportunities": [{"summary": "Strong Liquidity"}],
    })
    outputs.write_json(aid, "statement_validation_report.json", {
        "validated_count": 124, "discrepancy_count": 9, "review_required_count": 2, "source_missing_count": 15, "not_comparable_count": 0})
    outputs.write_json(aid, "discrepancy_report.json", {"fail_count": 46, "warn_count": 0, "pass_count": 0})
    outputs.write_json(aid, "analyst_review_report.json", {
        "material_count": 19, "watch_count": 18, "info_count": 0,
        "findings": [{"severity": "MATERIAL", "statement": "income_statement", "metric": "Revenue", "period": "FY2019",
                      "observation": "Data discrepancy: workbook 444.072 vs SEC 436.32", "status": "open"}]})
    outputs.write_json(aid, "new_company_output_gate_report.json", {
        "status": "ok", "blockers": [], "warnings": ["PE10_PERIOD_NOTE: fiscal year-end dates not supplied"], "report_authorized": True})
    outputs.write_json(aid, "lease_rate_review.json", {
        "status": "autonomous_selected", "proposed_rate": 0.04, "selected_rate": 0.04, "approved_rate": None,
        "decision_class": "AUTONOMOUS_AGENT_DECISION", "classification": "disclosed", "supporting_evidence": ["FY2025 reported rate 0.0400."]})
    outputs.write_json(aid, "rd_useful_life_decision.json", {
        "selected_useful_life": 5, "permitted_range": [1, 10], "confidence": 0.7, "rationale": "industrial product development cycle"})
    outputs.write_json(aid, "new_company_run_state.json", {"workflow_state": "COMPLETE", "lease_rate_approved": False, "rd_life_overridden": False})
    outputs.write_json(aid, "provenance_report.json", {"entries": [{"cell_ref": "Income Statement!B5", "source": "10-K FY2025", "confidence": 0.93}]})
    (outputs.analysis_output_dir(aid) / "completed_workbook.xlsx").write_bytes(b"PK\x03\x04x")
    return SimpleNamespace(analyses=analyses, outputs=outputs, aid=aid, tmp=tmp_path)


def engine(env) -> FreeAnswerEngine:
    return FreeAnswerEngine(env.analyses, env.outputs)


# ---------------------------------------------------------------------------- free answers


def test_recommendation_answer_shows_both_sources_and_flags_the_conflict(env):
    answer = engine(env).answer(env.aid, "What drove the recommendation and the scores?")
    assert answer.intent == "recommendation"
    assert "Hold" in answer.reply and "Watch" in answer.reply
    assert "disagree" in answer.reply  # never silently pick one
    assert "$268.14" in answer.reply and "56.5%" in answer.reply
    assert set(answer.sources) == {"final_recommendation_report.json", "analysis_engine_result.json"}


def test_validation_answer(env):
    answer = engine(env).answer(env.aid, "Are there validation failures or discrepancies I should look at?")
    assert answer.intent == "validation"
    assert "124 validated" in answer.reply and "9 discrepancies" in answer.reply
    assert "19 material" in answer.reply and "workbook 444.072 vs SEC 436.32" in answer.reply
    assert "PE10_PERIOD_NOTE" in answer.reply


def test_review_answer_says_the_assistant_cannot_approve(env):
    answer = engine(env).answer(env.aid, "What is waiting for my review?")
    assert answer.intent == "review"
    assert "4.00%" in answer.reply and "not yet" in answer.reply and "5 years" in answer.reply
    assert "cannot approve" in answer.reply


def test_attention_summary_flags_problems(env):
    answer = engine(env).answer(env.aid, "Summarise this analysis and what needs my attention.")
    assert answer.intent == "attention"
    assert "ATTENTION" in answer.reply and "disagree" in answer.reply and "Waiting on you" in answer.reply


def test_other_intents(env):
    eng = engine(env)
    assert "Weak Organic Growth" in eng.answer(env.aid, "What are the main risks and opportunities?").reply
    files = eng.answer(env.aid, "Which deliverable files do you have?")
    assert files.intent == "files" and "completed_workbook.xlsx" in files.reply
    log = eng.answer(env.aid, "Show me the pipeline status and stages")
    assert log.intent == "log" and "Pipeline:" in log.reply


def test_cell_reference_gets_provenance_for_free(env):
    answer = engine(env).answer(env.aid, "Where does Income Statement!B5 come from?")
    assert answer.intent == "provenance" and "10-K FY2025" in answer.reply
    assert engine(env).answer(env.aid, "Where does Income Statement!Z99 come from?") is None


@pytest.mark.parametrize("question", [
    "What if the lease rate were 6%?",
    "Should I buy this stock?",
    "Compare this with Apple",
    "What is your take on management quality?",
    "Forecast revenue for 2027",
    "Tell me a joke",
    "x" * 500,
    "",
])
def test_reasoning_and_unrelated_questions_are_not_answered_for_free(env, question):
    assert engine(env).answer(env.aid, question) is None


def test_missing_artifacts_fall_through_instead_of_inventing(tmp_path):
    analyses = AnalysisService(tmp_path / "a")
    outputs = OutputService(tmp_path / "o")
    aid = analyses.create(CreateAnalysisRequest(company="Empty", ticker="e", analysis_type="annual_update")).analysis_id
    eng = FreeAnswerEngine(analyses, outputs)
    assert eng.answer(aid, "What is the recommendation and score?") is None
    assert eng.answer(aid, "Any validation problems?") is None


# ---------------------------------------------------------------------------- cache


def test_cache_roundtrip_expiry_and_fingerprint(env):
    cache = AnswerCache(env.tmp / "cache")
    fp = AnswerCache.fingerprint(env.analyses, env.outputs, env.aid)
    assert cache.get(env.aid, "Why?", fp) is None
    cache.put(env.aid, "Why?", fp, reply="because", model="m", cost_usd=0.1)
    assert cache.get(env.aid, " why ?? ", fp)["reply"] == "because"  # normalised question
    assert cache.get(env.aid, "Why?", "different-fingerprint") is None
    time.sleep(0.01)
    env.outputs.write_json(env.aid, "new_output.json", {"x": 1})
    assert AnswerCache.fingerprint(env.analyses, env.outputs, env.aid) != fp
    assert cache.invalidate(env.aid, "why") is True and cache.get(env.aid, "Why?", fp) is None
    assert normalize_question("  Hello   World?! ") == "hello world"


# ---------------------------------------------------------------------------- router


class CountingClient:
    def __init__(self):
        self.calls = 0
        outer = self

        class M:
            def create(self, **kw):
                outer.calls += 1
                return SimpleNamespace(
                    content=[SimpleNamespace(type="text", text=f"claude answer {outer.calls}")],
                    stop_reason="end_turn", model="claude-sonnet-5-5",
                    usage=SimpleNamespace(input_tokens=1000, output_tokens=200),
                )

        self.messages = M()
        self.beta = SimpleNamespace(messages=self.messages)


@pytest.fixture
def service(env):
    client = CountingClient()
    budget = BudgetService(env.tmp / "usage", cap_usd=20.0)
    agent = AnalystAgent(env.analyses, env.outputs, client_factory=lambda: client, budget_service=budget)
    svc = AnalystService(env.analyses, env.outputs, agent, budget, AnswerCache(env.tmp / "cache"))
    return SimpleNamespace(svc=svc, client=client, budget=budget, env=env)


def msg(text):
    return [{"role": "user", "content": text}]


def test_auto_mode_answers_free_questions_without_any_paid_call(service):
    result = service.svc.answer(service.env.aid, msg("What is waiting for my review?"), mode="auto")
    assert result.source == "built_in" and result.estimated_cost_usd == 0.0
    assert service.client.calls == 0 and service.budget.spent_usd() == 0.0


def test_auto_mode_never_pays_it_offers_the_button(service):
    result = service.svc.answer(service.env.aid, msg("What if the lease rate were 6%?"), mode="auto")
    assert result.source == "none" and result.needs_claude is True and result.reply == NEEDS_CLAUDE_TEXT
    assert result.estimated_cost_usd > 0
    assert service.client.calls == 0
    free_only = service.svc.answer(service.env.aid, msg("What if the lease rate were 6%?"), mode="free")
    assert free_only.needs_claude is False and service.client.calls == 0


def test_claude_mode_pays_once_then_remembers(service):
    q = "What if the lease rate were 6%?"
    first = service.svc.answer(service.env.aid, msg(q), mode="claude")
    assert first.source == "claude" and service.client.calls == 1 and service.budget.spent_usd() > 0
    spent = service.budget.spent_usd()

    again = service.svc.answer(service.env.aid, msg(q), mode="claude")
    assert again.source == "cache" and again.reply == first.reply and service.client.calls == 1
    assert service.budget.spent_usd() == spent  # remembered answers are free
    auto = service.svc.answer(service.env.aid, msg(q), mode="auto")
    assert auto.source == "cache" and auto.needs_claude is False


def test_cache_is_retired_when_the_analysis_changes(service):
    q = "What if the lease rate were 6%?"
    service.svc.answer(service.env.aid, msg(q), mode="claude")
    service.env.outputs.write_json(service.env.aid, "lease_rate_review.json", {"proposed_rate": 0.04, "approved_rate": 0.05})
    result = service.svc.answer(service.env.aid, msg(q), mode="claude")
    assert result.source == "claude" and service.client.calls == 2


def test_multi_turn_conversations_are_not_cached(service):
    convo = [{"role": "user", "content": "What if the lease rate were 6%?"}, {"role": "assistant", "content": "ok"},
             {"role": "user", "content": "And 8%?"}]
    service.svc.answer(service.env.aid, convo, mode="claude")
    service.svc.answer(service.env.aid, convo, mode="claude")
    assert service.client.calls == 2


def test_remembered_answers_still_work_after_the_budget_is_used_up(service):
    q = "What if the lease rate were 6%?"
    service.svc.answer(service.env.aid, msg(q), mode="claude")
    service.budget._cap_override = 0.0
    assert service.svc.answer(service.env.aid, msg(q), mode="claude").source == "cache"


def test_bad_mode_is_rejected(service):
    from agent import AgentError

    with pytest.raises(AgentError):
        service.svc.answer(service.env.aid, msg("hi"), mode="turbo")


# ---------------------------------------------------------------------------- endpoint


def test_chat_endpoint_modes_and_thumbs_down_forgets_the_answer(env, monkeypatch):
    client_stub = CountingClient()
    budget = BudgetService(env.tmp / "usage", cap_usd=20.0)
    agent = AnalystAgent(env.analyses, env.outputs, client_factory=lambda: client_stub, budget_service=budget)
    cache = AnswerCache(env.tmp / "cache")
    svc = AnalystService(env.analyses, env.outputs, agent, budget, cache)
    for name, value in (("analysis_service", env.analyses), ("output_service", env.outputs), ("analyst_service", svc),
                        ("answer_cache", cache), ("budget_service", budget),
                        ("feedback_service", FeedbackService(env.tmp / "fb"))):
        monkeypatch.setattr(main, name, value)
    api = TestClient(main.app)
    url = f"/analysis/{env.aid}/chat"

    free = api.post(url, json={"messages": msg("What is waiting for my review?")}).json()
    assert free["source"] == "built_in" and free["needs_claude"] is False and client_stub.calls == 0

    q = "What if the lease rate were 6%?"
    ask = api.post(url, json={"messages": msg(q)}).json()
    assert ask["needs_claude"] is True and ask["source"] == "none" and client_stub.calls == 0

    paid = api.post(url, json={"messages": msg(q), "mode": "claude"}).json()
    assert paid["source"] == "claude" and client_stub.calls == 1
    assert api.post(url, json={"messages": msg(q), "mode": "claude"}).json()["source"] == "cache"

    fb = api.post(f"/analysis/{env.aid}/feedback", json={"target": "chat_answer", "action": "thumbs_down",
                                                         "reason": "wrong", "context": {"question": q}})
    assert fb.status_code == 200
    assert api.post(url, json={"messages": msg(q), "mode": "claude"}).json()["source"] == "claude"
    assert client_stub.calls == 2

    assert api.post(url, json={"messages": msg(q), "mode": "turbo"}).status_code == 422
