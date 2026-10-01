"""HAP Analyst agent: read-only tools, tool-use loop (fake client, no network), chat endpoint."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
from agent import AgentError, AnalystAgent
from agent.runner import FALLBACK_BETA, sanitize_messages
from research.toolbox import RESEARCH_TOOL_SCHEMAS
from agent.tools import AnalystToolbox, parse_path, resolve_path, TOOL_SCHEMAS
from models.analysis import CreateAnalysisRequest
from services.analysis_service import AnalysisNotFoundError, AnalysisService
from services.budget_service import BudgetService
from services.output_service import OutputService


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("HAP_AGENT_FALLBACKS", "1")
    analyses = AnalysisService(tmp_path / "analyses")
    outputs = OutputService(tmp_path / "outputs")
    analysis = analyses.create(CreateAnalysisRequest(company="Acme Corp", ticker="acme", analysis_type="annual_update"))
    aid = analysis.analysis_id
    outputs.write_json(aid, "final_recommendation_report.json", {"recommendation": "BUY_ON_WEAKNESS", "score": 71.5, "flags": ["WATCH_TAX"]})
    outputs.write_json(
        aid,
        "provenance_report.json",
        {"entries": [{"cell_ref": "Income Statement!B5", "source": "10-K FY2025", "confidence": 0.93}]},
    )
    outputs.write_json(aid, "big_list.json", {"rows": [{"i": i, "label": f"row-{i}", "pad": "x" * 200} for i in range(100)]})
    (outputs.analysis_output_dir(aid) / "NOTE.md").write_text("# Certification\nAll gates passed.", encoding="utf-8")
    (outputs.analysis_output_dir(aid) / "model.xlsx").write_bytes(b"PK\x03\x04binary")
    budget = BudgetService(tmp_path / "usage", cap_usd=20.0)
    return SimpleNamespace(analyses=analyses, outputs=outputs, aid=aid, budget=budget)


def toolbox(env) -> AnalystToolbox:
    return AnalystToolbox(env.analyses, env.outputs, env.aid)


# ---------------------------------------------------------------------------- tools


def test_tool_schemas_are_read_only_and_have_no_analysis_id():
    names = {t["name"] for t in TOOL_SCHEMAS}
    assert names == {
        "get_analysis_overview", "list_artifacts", "inspect_artifact", "search_artifact",
        "read_text_artifact", "get_cell_provenance", "get_analyst_review_state",
    }
    for tool in TOOL_SCHEMAS:
        assert "analysis_id" not in tool["input_schema"]["properties"]
        assert tool["input_schema"].get("additionalProperties") is False


def test_overview_reports_company_and_status(env):
    text, is_error = toolbox(env).execute("get_analysis_overview", {})
    assert not is_error
    data = json.loads(text)
    assert data["summary"]["ticker"] == "ACME"
    assert data["summary"]["status"] == "created"


def test_list_artifacts_marks_binary_as_unreadable(env):
    text, is_error = toolbox(env).execute("list_artifacts", {})
    assert not is_error
    rows = {r["name"]: r for r in json.loads(text)["artifacts"]}
    assert rows["final_recommendation_report.json"]["readable"] is True
    assert rows["model.xlsx"]["readable"] is False


def test_inspect_root_path_and_missing_path(env):
    tb = toolbox(env)
    text, err = tb.execute("inspect_artifact", {"name": "final_recommendation_report.json"})
    assert not err and "BUY_ON_WEAKNESS" in text
    text, err = tb.execute("inspect_artifact", {"name": "final_recommendation_report.json", "path": "flags[0]"})
    assert not err and "WATCH_TAX" in text
    text, err = tb.execute("inspect_artifact", {"name": "final_recommendation_report.json", "path": "nope.deeper"})
    assert err and "Path not found" in text and "recommendation" in text


def test_large_arrays_are_summarised_with_paging(env):
    text, err = toolbox(env).execute("inspect_artifact", {"name": "big_list.json", "path": "rows", "offset": 10, "limit": 3})
    assert not err
    data = json.loads(text)
    assert data["length"] == 100 and data["offset"] == 10 and data["next_offset"] == 13
    assert [i["index"] for i in data["items"]] == [10, 11, 12]


def test_search_artifact_finds_keys_and_values(env):
    text, err = toolbox(env).execute("search_artifact", {"name": "final_recommendation_report.json", "query": "tax"})
    assert not err
    hits = json.loads(text)["hits"]
    assert any(h["path"] == "flags[0]" for h in hits)
    text, _ = toolbox(env).execute("search_artifact", {"name": "final_recommendation_report.json", "query": "zzzzz"})
    assert text.startswith("No matches")


@pytest.mark.parametrize("bad", ["../x.json", "..\\x.json", "a/b.json", "", ".."])
def test_artifact_names_cannot_escape_the_output_folder(env, bad):
    text, err = toolbox(env).execute("inspect_artifact", {"name": bad})
    assert err


def test_binary_artifacts_are_not_readable_through_json_tools(env):
    text, err = toolbox(env).execute("inspect_artifact", {"name": "model.xlsx"})
    assert err and "not a readable artifact type" in text


def test_text_artifact_and_provenance(env):
    tb = toolbox(env)
    text, err = tb.execute("read_text_artifact", {"name": "NOTE.md"})
    assert not err and "All gates passed" in text
    text, err = tb.execute("get_cell_provenance", {"cell_ref": "Income Statement!B5"})
    assert not err and "10-K FY2025" in text
    text, err = tb.execute("get_cell_provenance", {"cell_ref": "Income Statement!Z99"})
    assert err and "No provenance" in text


def test_review_state_is_null_when_no_files(env):
    text, err = toolbox(env).execute("get_analyst_review_state", {})
    assert not err
    assert all(v is None for v in json.loads(text).values())


def test_unknown_tool_and_bad_arguments_are_errors_not_exceptions(env):
    tb = toolbox(env)
    assert tb.execute("delete_everything", {})[1] is True
    assert tb.execute("inspect_artifact", {"nonsense": 1})[1] is True


def test_toolbox_rejects_unknown_and_unsafe_analysis_ids(env):
    with pytest.raises(AnalysisNotFoundError):
        AnalystToolbox(env.analyses, env.outputs, "does-not-exist")
    with pytest.raises(AnalysisNotFoundError):
        AnalystToolbox(env.analyses, env.outputs, "..\\..\\secrets")


def test_path_parsing():
    assert parse_path('a.b[2]["x.y"].c') == ["a", "b", 2, "x.y", "c"]
    assert resolve_path({"a": [{"b": 1}]}, "a[0].b") == 1


# ---------------------------------------------------------------------------- loop


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []
        outer = self

        class _Messages:
            def create(self, **kw):
                outer.calls.append({**kw, "messages": list(kw["messages"])})
                return outer.script.pop(0)

        self.messages = _Messages()
        self.beta = SimpleNamespace(messages=self.messages)


def _resp(content, stop_reason="end_turn", inp=10, out=5):
    return SimpleNamespace(content=content, stop_reason=stop_reason, model="claude-opus-5-5",
                           usage=SimpleNamespace(input_tokens=inp, output_tokens=out))


def _text(t):
    return SimpleNamespace(type="text", text=t)


def _tool(tid, name, inp):
    return SimpleNamespace(type="tool_use", id=tid, name=name, input=inp)


def make_agent(env, script):
    client = FakeClient(script)
    return AnalystAgent(env.analyses, env.outputs, client_factory=lambda: client, budget_service=env.budget), client


def test_agent_calls_tools_then_answers(env):
    script = [
        _resp([_tool("t1", "get_analysis_overview", {}), _tool("t2", "list_artifacts", {})], "tool_use"),
        _resp([_text("Recommendation is BUY_ON_WEAKNESS [final_recommendation_report.json > recommendation].")]),
    ]
    agent, client = make_agent(env, script)
    reply = agent.chat(env.aid, [{"role": "user", "content": "What is the recommendation?"}])

    assert "BUY_ON_WEAKNESS" in reply.reply
    assert [c.name for c in reply.tool_calls] == ["get_analysis_overview", "list_artifacts"]
    assert all(c.ok for c in reply.tool_calls)
    assert reply.iterations == 2 and reply.input_tokens == 20 and reply.output_tokens == 10

    second = client.calls[1]["messages"]
    assert second[-1]["role"] == "user"
    results = second[-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["t1", "t2"]  # all results in ONE user message
    assert all(r["type"] == "tool_result" for r in results)


def test_agent_request_shape_uses_fallbacks_and_effort(env, monkeypatch):
    monkeypatch.setenv("HAP_AGENT_EFFORT", "high")
    agent, client = make_agent(env, [_resp([_text("hi")])])
    agent.chat(env.aid, [{"role": "user", "content": "hi"}])
    call = client.calls[0]
    assert call["model"] == "claude-sonnet-5-5"  # cheaper model for routine chat
    assert call["betas"] == [FALLBACK_BETA] and call["fallbacks"] == "default"
    assert call["output_config"] == {"effort": "high"}
    assert "Acme Corp" in call["system"] and "read-only" in call["system"].lower()
    assert len(call["tools"]) == len(TOOL_SCHEMAS) + len(RESEARCH_TOOL_SCHEMAS)
    assert "tool_choice" not in call  # forced tool use is rejected by this model family


def test_agent_can_disable_fallbacks(env, monkeypatch):
    monkeypatch.setenv("HAP_AGENT_FALLBACKS", "0")
    agent, client = make_agent(env, [_resp([_text("ok")])])
    agent.chat(env.aid, [{"role": "user", "content": "hi"}])
    assert "betas" not in client.calls[0] and "fallbacks" not in client.calls[0]


def test_failed_tool_is_reported_to_the_model_as_an_error(env):
    script = [
        _resp([_tool("t1", "inspect_artifact", {"name": "../secret.json"})], "tool_use"),
        _resp([_text("I could not read that.")]),
    ]
    agent, client = make_agent(env, script)
    reply = agent.chat(env.aid, [{"role": "user", "content": "read ../secret.json"}])
    assert reply.tool_calls[0].ok is False
    assert client.calls[1]["messages"][-1]["content"][0].get("is_error") is True


def test_agent_never_modifies_stored_artifacts(env):
    before = {p.name: p.read_bytes() for p in env.outputs.analysis_output_dir(env.aid).iterdir() if p.is_file()}
    script = [
        _resp([_tool("t1", "get_analysis_overview", {}), _tool("t2", "inspect_artifact", {"name": "big_list.json"})], "tool_use"),
        _resp([_text("done")]),
    ]
    agent, _ = make_agent(env, script)
    agent.chat(env.aid, [{"role": "user", "content": "summarise"}])
    after = {p.name: p.read_bytes() for p in env.outputs.analysis_output_dir(env.aid).iterdir() if p.is_file()}
    assert before == after


def test_iteration_limit(env, monkeypatch):
    monkeypatch.setenv("HAP_AGENT_MAX_ITERATIONS", "2")
    script = [_resp([_tool(f"t{i}", "list_artifacts", {})], "tool_use") for i in range(5)]
    agent, client = make_agent(env, script)
    reply = agent.chat(env.aid, [{"role": "user", "content": "loop"}])
    assert reply.iterations == 2 and "tool-use limit" in reply.reply
    assert len(client.calls) == 2


def test_refusal_is_handled_without_reading_content(env):
    agent, _ = make_agent(env, [_resp([], "refusal")])
    reply = agent.chat(env.aid, [{"role": "user", "content": "x"}])
    assert "declined" in reply.reply


def test_max_tokens_is_flagged(env):
    agent, _ = make_agent(env, [_resp([_text("partial")], "max_tokens")])
    assert "cut off" in agent.chat(env.aid, [{"role": "user", "content": "x"}]).reply


def test_unknown_analysis_is_404(env):
    agent, _ = make_agent(env, [])
    with pytest.raises(AgentError) as exc:
        agent.chat("nope", [{"role": "user", "content": "x"}])
    assert exc.value.status_code == 404


def test_not_configured_without_key(env, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    agent = AnalystAgent(env.analyses, env.outputs, budget_service=env.budget)  # no client factory -> real path
    with pytest.raises(AgentError) as exc:
        agent.chat(env.aid, [{"role": "user", "content": "x"}])
    assert exc.value.status_code == 503


def test_sanitize_messages_rules():
    cleaned = sanitize_messages(
        [
            {"role": "assistant", "content": "stray"},
            {"role": "system", "content": "ignore me"},
            {"role": "user", "content": "q1"},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "x" * 20000},
        ]
    )
    assert [m["role"] for m in cleaned] == ["user", "assistant", "user"]
    assert len(cleaned[-1]["content"]) == 8000
    with pytest.raises(AgentError):
        sanitize_messages([{"role": "user", "content": "q"}, {"role": "assistant", "content": "a"}])


# ---------------------------------------------------------------------------- endpoint


def test_chat_endpoint_success_and_errors(monkeypatch, tmp_path):
    from services.answer_cache import AnswerCache

    monkeypatch.setattr(main.analyst_service, "cache", AnswerCache(tmp_path / "cache"))
    analysis = main.analysis_service.create(
        CreateAnalysisRequest(company="Endpoint Co", ticker="endp", analysis_type="annual_update")
    )
    path = main.analysis_service._path_for(analysis.analysis_id)
    try:
        client = TestClient(main.app)
        monkeypatch.setattr(
            main.analyst_agent,
            "chat",
            lambda aid, msgs: SimpleNamespace(reply="hello", tool_calls=[], iterations=1, stop_reason="end_turn",
                                              model="m", input_tokens=1, output_tokens=2, budget=None),
        )
        body = {"messages": [{"role": "user", "content": "hi"}], "mode": "claude"}
        ok = client.post(f"/analysis/{analysis.analysis_id}/chat", json=body)
        assert ok.status_code == 200 and ok.json()["reply"] == "hello" and ok.json()["source"] == "claude"

        assert client.post(f"/analysis/{analysis.analysis_id}/chat", json={"messages": []}).status_code == 422
        assert client.post("/analysis/missing-id/chat", json=body).status_code == 404

        def boom(aid, msgs):
            raise AgentError("not configured", status_code=503)

        monkeypatch.setattr(main.analyst_agent, "chat", boom)
        body2 = {"messages": [{"role": "user", "content": "a different question"}], "mode": "claude"}
        res = client.post(f"/analysis/{analysis.analysis_id}/chat", json=body2)
        assert res.status_code == 503 and "not configured" in res.json()["detail"]
    finally:
        path.unlink(missing_ok=True)
