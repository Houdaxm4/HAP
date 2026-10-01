"""Write the analyst opinions of the Word report: fundamentals strength and (if strong) whether the company is cheap.

Runs on request, never inside the pipeline, because it spends money. The model gets the same tools as the chat agent
(the analysis artifacts plus allow-listed online research), reacts to HAP's rules-based verdict, and must label and
date every outside fact. The result is inserted into the existing Word report in place of the 'pending' markers.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from models.common import utc_now_iso
from services.report_opinion import ASSESSMENT_FILE, apply_opinion_to_docx
from services.safe_io import write_json_atomic

OPINION_FILE = "report_opinion.json"
MAX_SECTION_CHARS = 1800

INSTRUCTIONS = """

TASK: write the analyst-opinion paragraphs of the company report. Two sections at most.

Method
1. Read the rules-based verdict below and the analysis artifacts (get_analysis_overview, then final_recommendation_report.json and the key metrics you need).
2. Gather outside intelligence with the research tools: search_news for the company, get_recent_filings (for example 8-Ks since the analysis date), and fetch_ir_page only if the company's IR site is known. Use the free delayed price for the current price. Do not make more than about six research calls.
3. Weigh the outside evidence against the workbook figures. Tier your evidence: SEC filing = authoritative; IR page = the company's own claim; delayed price = indicative; news = unverified lead (say so, give publisher and date).

Write exactly this format and nothing else:
### FUNDAMENTALS
<150 to 220 words: how strong the fundamentals are (business quality, returns on capital, growth and margins, balance sheet, anything in the outside evidence that changes the picture). State your view in the first sentence. If it differs from HAP's rules-based verdict, say so plainly and why.>
### VALUATION
<only if the verdict below says the fundamentals are STRONG: 120 to 180 words on whether the company is cheap or expensive, using enterprise (owner-earnings) value per share, Graham value, margin of safety, PE10, expected return and the current price; state the view in the first sentence. If the fundamentals are not strong, omit this whole section including its heading.>

Rules: cite the artifact or the outside source (with date) for every number; never invent figures; keep outside facts separate from HAP's results and flag any conflict; no instruction to buy or sell; if data you need is missing, say what is missing."""


class OpinionError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def parse_sections(text: str) -> dict[str, str]:
    """Split '### FUNDAMENTALS ... ### VALUATION ...' into {'fundamentals': ..., 'valuation': ...}."""
    sections: dict[str, str] = {}
    parts = re.split(r"^\s*#{2,4}\s*(FUNDAMENTALS|VALUATION)\s*$", text or "", flags=re.IGNORECASE | re.MULTILINE)
    for index in range(1, len(parts) - 1, 2):
        body = re.sub(r"\n{3,}", "\n\n", parts[index + 1].strip())
        body = re.sub(r"[*_`]{1,3}", "", body)  # the Word report is plain text
        if body:
            sections[parts[index].lower()] = body[:MAX_SECTION_CHARS]
    return sections


class ReportOpinionService:
    def __init__(self, *, agent: Any, analysis_service: Any, output_service: Any) -> None:
        self.agent = agent
        self.analysis_service = analysis_service
        self.output_service = output_service

    def saved(self, analysis_id: str) -> dict[str, Any] | None:
        try:
            return self.output_service.read_json(analysis_id, OPINION_FILE)
        except (FileNotFoundError, ValueError):
            return None

    def generate(self, analysis_id: str) -> dict[str, Any]:
        self.analysis_service.get(analysis_id)
        directory: Path = self.output_service.analysis_output_dir(analysis_id)
        try:
            assessment = self.output_service.read_json(analysis_id, ASSESSMENT_FILE)
        except (FileNotFoundError, ValueError) as exc:
            raise OpinionError("The Word report has not been generated yet; run the analysis first.", 409) from exc
        documents = sorted(directory.glob("*.docx"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not documents:
            raise OpinionError("No Word report found for this analysis.", 409)

        from settings import strong_model

        rules = assessment.get("fundamentals", {}).get("strong")  # True, False, or None (no rules-based verdict)
        verdict = {
            "fundamentals_rules_based": "NOT AVAILABLE (judge the fundamentals yourself; write VALUATION only if you rate them strong)"
            if rules is None else ("STRONG" if rules else "NOT RATED STRONG"),
            "fundamentals_facts": assessment.get("fundamentals", {}).get("facts", []),
            "against": assessment.get("fundamentals", {}).get("against", []),
            "valuation_rules_based": assessment.get("valuation", {}).get("verdict"),
            "valuation_facts": assessment.get("valuation", {}).get("facts", []),
        }
        extra = INSTRUCTIONS + "\n\nRules-based verdict (HAP):\n" + json.dumps(verdict, indent=2)
        reply = self.agent.chat(
            analysis_id,
            [{"role": "user", "content": "Write the analyst-opinion sections of the report now."}],
            model=strong_model(), purpose="report_opinion", extra_system=extra,
        )
        sections = parse_sections(getattr(reply, "reply", ""))
        if "fundamentals" not in sections:
            raise OpinionError("The model did not return a usable fundamentals opinion; nothing was changed.", 502)
        if rules is False:
            sections.pop("valuation", None)  # the cheapness discussion only exists for strong fundamentals

        evidence = self._outside_sources(directory)
        record = {
            "analysis_id": analysis_id,
            "generated_at": utc_now_iso(),
            "model": getattr(reply, "model", None),
            "fundamentals": sections["fundamentals"],
            "valuation": sections.get("valuation"),
            "tools_used": [getattr(c, "name", str(c)) for c in getattr(reply, "tool_calls", [])],
            "outside_sources": evidence,
            "label": "opinion, not HAP's rules-based result",
        }
        record["inserted_into"] = documents[0].name
        record["sections_inserted"] = apply_opinion_to_docx(documents[0], record)
        write_json_atomic(directory / OPINION_FILE, record)
        return record

    @staticmethod
    def _outside_sources(directory: Path, limit: int = 12) -> list[dict[str, str]]:
        path = directory / "research_evidence.jsonl"
        if not path.exists():
            return []
        rows: list[dict[str, str]] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
                item = json.loads(line)
                rows.append({k: str(item.get(k, "")) for k in ("source", "title", "url", "as_of", "retrieved_at")})
        except (OSError, ValueError):
            return rows
        return rows
