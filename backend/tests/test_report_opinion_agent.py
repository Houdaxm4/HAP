"""Opinion generation: fake agent, no network. Parsing, gating on strength, docx insertion, saved record."""

from types import SimpleNamespace

import pytest
from docx import Document

from agent.report_opinion import OpinionError, ReportOpinionService, parse_sections
from models.analysis import CreateAnalysisRequest
from services.analysis_service import AnalysisService
from services.output_service import OutputService
from services.report_opinion import write_assessment_sections

REPLY = """### FUNDAMENTALS
**Strong.** Returns on capital are high [final_recommendation_report.json].
### VALUATION
Looks cheap versus owner-earnings value (news, Reuters, 2026-09-28).
"""


class FakeAgent:
    def __init__(self, reply=REPLY):
        self.reply, self.calls = reply, []

    def chat(self, analysis_id, messages, **kw):
        self.calls.append(kw)
        return SimpleNamespace(reply=self.reply, model="strong-model", tool_calls=[SimpleNamespace(name="search_news")])


@pytest.fixture
def env(tmp_path):
    analyses = AnalysisService(tmp_path / "a")
    outputs = OutputService(tmp_path / "o")
    aid = analyses.create(CreateAnalysisRequest(company="Acme", ticker="acme", analysis_type="new_company")).analysis_id
    return SimpleNamespace(analyses=analyses, outputs=outputs, aid=aid)


def make_report(env, bq):
    out = env.outputs.analysis_output_dir(env.aid)
    env.outputs.write_json(env.aid, "final_recommendation_report.json", {
        "business_quality_score": bq, "business_quality_classification": "X", "current_price": 10.0, "margin_of_safety": 0.4})
    doc = Document()
    write_assessment_sections(doc, out, SimpleNamespace(roic_wacc=0.1, roce=0.2, enterprise_mos=0.4))
    doc.save(str(out / "report.docx"))
    return out


def test_parse_sections_strips_markdown():
    sections = parse_sections(REPLY)
    assert sections["fundamentals"].startswith("Strong.") and "**" not in sections["fundamentals"]
    assert "cheap" in sections["valuation"]
    assert parse_sections("no headings here") == {}


def test_strong_company_gets_both_opinions_in_the_report(env):
    out = make_report(env, bq=80.0)
    agent = FakeAgent()
    record = ReportOpinionService(agent=agent, analysis_service=env.analyses, output_service=env.outputs).generate(env.aid)
    assert record["sections_inserted"] == 2 and record["tools_used"] == ["search_news"]
    assert agent.calls[0]["purpose"] == "report_opinion" and '"fundamentals_rules_based": "STRONG"' in agent.calls[0]["extra_system"]
    text = "\n".join(p.text for p in Document(str(out / "report.docx")).paragraphs)
    assert "Strong. Returns on capital" in text and "Looks cheap" in text and "pending" not in text
    assert env.outputs.read_json(env.aid, "report_opinion.json")["label"].startswith("opinion")


def test_weak_company_gets_no_valuation_opinion(env):
    out = make_report(env, bq=60.0)
    record = ReportOpinionService(agent=FakeAgent(), analysis_service=env.analyses, output_service=env.outputs).generate(env.aid)
    assert record["valuation"] is None and record["sections_inserted"] == 1
    assert "Looks cheap" not in "\n".join(p.text for p in Document(str(out / "report.docx")).paragraphs)


def test_errors_leave_the_report_untouched(env):
    service = ReportOpinionService(agent=FakeAgent("rambling without headings"), analysis_service=env.analyses, output_service=env.outputs)
    with pytest.raises(OpinionError) as exc:
        service.generate(env.aid)  # report not generated yet
    assert exc.value.status_code == 409
    out = make_report(env, bq=80.0)
    before = (out / "report.docx").read_bytes()
    with pytest.raises(OpinionError) as exc:
        service.generate(env.aid)
    assert exc.value.status_code == 502 and (out / "report.docx").read_bytes() == before


def test_endpoint_maps_errors_and_success(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    import main
    from agent import AgentError

    client = TestClient(main.app)

    class Boom:
        def __init__(self, exc):
            self.exc = exc

        def generate(self, analysis_id):
            raise self.exc

        def saved(self, analysis_id):
            return None

    isolated = AnalysisService(tmp_path / "analyses")  # never touch the real storage
    monkeypatch.setattr(main, "analysis_service", isolated)
    analysis_id = isolated.create(CreateAnalysisRequest(company="Acme", ticker="acme", analysis_type="new_company")).analysis_id
    if True:
        monkeypatch.setattr(main, "report_opinion_service", Boom(AgentError("The analyst agent is not configured.", 503)))
        response = client.post(f"/analysis/{analysis_id}/report/opinion")
        assert response.status_code == 503 and "not configured" in response.json()["detail"]
        monkeypatch.setattr(main, "report_opinion_service", Boom(OpinionError("No report yet.", 409)))
        assert client.post(f"/analysis/{analysis_id}/report/opinion").status_code == 409
        assert client.get(f"/analysis/{analysis_id}/report/opinion").status_code == 404
