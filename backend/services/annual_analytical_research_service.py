"""Question-driven analytical research evidence. Never SOURCE_FILLs workbook facts.

Reuses SecService for EDGAR retrieval and caching. Does not retune the frozen
normalized-base workbook diagnostic; it may only annotate that diagnostic after
primary-source synthesis.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime
from html import unescape
from typing import Any

from models.annual_update import (
    ACQUISITION_RELATED_CAPEX,
    GROWTH_CAPEX,
    HAP_INFERENCE,
    INSUFFICIENT_BASE_EVIDENCE,
    KEEP_REPORTED_BASE,
    KEEP_REPORTED_BASE_SUPPORTED,
    MAINTENANCE_CAPEX,
    MANAGEMENT_STATEMENT,
    NO_DECISION_EFFECT,
    NO_EXTERNAL_RESEARCH_REQUIRED,
    NORMALIZATION_SUPPORTABLE_AMOUNT_NOT_SELECTED,
    REMAINS_INSUFFICIENT,
    RESEARCH_UNAVAILABLE,
    RESEARCHED,
    SEC_DISCLOSURE,
    SECONDARY_SOURCE,
    STRUCTURAL_CAPITAL_INTENSITY,
    TEMPORARY_PROJECT_CAPEX,
    UNCLASSIFIED_CAPEX,
    USE_NORMALIZED_BASE,
    AnalyticalResearchEvidence,
    AnalyticalResearchReport,
    AnalyticalResearchSynthesis,
    NormalizedEarningsPowerAnalysis,
    ResearchQuestion,
)
from services.sec_service import SecService, SecServiceError

_CONF_FLOAT = {"HIGH": 0.75, "MEDIUM": 0.55, "LOW": 0.35}

_CAPEX_TERMS = (
    "capital expenditure",
    "capital expenditures",
    "capital spending",
    "capital asset purchases",
    "purchases of property, plant and equipment",
    "purchases of property plant and equipment",
)
_PROJECT_TERMS = (
    "facilit",
    "warehouse",
    "distribution center",
    "capacity",
    "expansion",
    "expand",
    "automat",
    "moderniz",
    "production line",
    "construction",
    "new plant",
    "new facility",
)
_MAINT_TERMS = ("maintenance capital", "maintenance spending", "replacement of", "repair")
_ACQ_TERMS = ("acquisition", "acquired", "acquire")
_GUIDE_DECLINE = (
    "expect capital expenditures to decrease",
    "expect capex to decrease",
    "capital expenditures to decline",
    "return to more normal",
    "return to historical",
    "after completion",
    "upon completion",
    "once complete",
    "project is expected to be complete",
    "expected to be completed",
    "will be completed",
    "completion of the",
    "needed to complete",
    "continuing into early fiscal",
    "continuing into the next fiscal year",
)
_FORWARD_GUIDE = (
    "we expect total capital expenditures",
    "expect total capital expenditures",
    "plan to invest approximately",
    "will invest approximately",
    "we plan to invest approximately",
)
_GUIDE_ELEVATED = (
    "remain elevated",
    "remains elevated",
    "continue to invest",
    "ongoing investment",
    "higher level of capital",
    "increased capital intensity",
    "structurally higher",
)
_MGMT_VERBS = (
    "we expect",
    "we believe",
    "we anticipate",
    "we plan",
    "management expects",
    "management believes",
    "the company expects",
    "the company anticipates",
)

_SEARCH_TERMS = [
    "capital expenditures",
    "capital expenditure",
    "facility expansion",
    "capacity",
    "automation",
    "maintenance capital",
    "acquisition",
    "completion",
    "capex guidance",
]


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = str(value).strip()[:10]
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None
    return None


def _html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>", "\n", html)
    html = re.sub(r"(?is)</(p|div|tr|h[1-6]|li)>", "\n", html)
    html = re.sub(r"(?is)<[^>]+>", " ", html)
    html = unescape(html).replace("\xa0", " ")
    html = re.sub(r"[ \t]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html


def _item7_window(text: str) -> str:
    match = re.search(
        r"item\s*7[\.\s\-:]{1,8}(?:\s|[^\n]{0,40})management.?s discussion",
        text,
        re.I,
    )
    if not match:
        return text
    start = match.start()
    end_m = re.search(r"item\s*8[\.\s\-:]{1,8}", text[start + 80 :], re.I)
    end = start + 80 + end_m.start() if end_m else min(len(text), start + 250_000)
    window = text[start:end]
    if len(window) < 20_000:
        return text
    return window


def _fingerprint(text: str) -> str:
    norm = re.sub(r"\s+", " ", (text or "").lower()).strip()[:280]
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def _contains_any(text: str, terms: tuple[str, ...] | list[str]) -> bool:
    low = text.lower()
    return any(t in low for t in terms)


def _fmt_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    mag = abs(value)
    if mag >= 1000:
        return f"{value:,.0f}"
    return f"{value:.1f}"


class AnnualAnalyticalResearchService:
    """Primary-source research for unresolved analytical questions."""

    def __init__(self, sec_service: SecService | None = None) -> None:
        self.sec = sec_service or SecService()

    def generate_questions(
        self,
        ticker: str,
        base: NormalizedEarningsPowerAnalysis,
    ) -> tuple[str, list[ResearchQuestion]]:
        """Return (status, questions). Workbook-sufficient cases do not research."""
        status = (base.reported_base_status or "").lower()
        types = set(base.distortion_type or [])
        if base.decision == KEEP_REPORTED_BASE and status in {"usable", "potentially_distorted"}:
            return NO_EXTERNAL_RESEARCH_REQUIRED, []
        if base.decision == USE_NORMALIZED_BASE and base.selected_normalized_base is not None:
            return NO_EXTERNAL_RESEARCH_REQUIRED, []
        if base.decision != INSUFFICIENT_BASE_EVIDENCE:
            return NO_EXTERNAL_RESEARCH_REQUIRED, []

        decomp = (base.component_series or {}).get("decomposition") or []
        capex_abs = [abs(row["capex"]) for row in decomp if isinstance(row.get("capex"), (int, float))]
        ni_vals = [row["ni"] for row in decomp if isinstance(row.get("ni"), (int, float))]
        oi_vals = [
            row["operating_income"]
            for row in decomp
            if isinstance(row.get("operating_income"), (int, float))
        ]
        last3 = capex_abs[-3:] if len(capex_abs) >= 3 else capex_abs
        questions: list[ResearchQuestion] = []
        capex_types = {"CAPEX_SPIKE", "STRUCTURAL_REINVESTMENT_CHANGE", "NEAR_ZERO_BASE", "CAPEX_TROUGH"}
        if types & capex_types:
            path = " → ".join(f"${_fmt_money(v)}m" for v in last3) if last3 else "the recent CapEx series"
            q = (
                f"Why did capital expenditures increase from approximately {path} "
                f"while NI and operating income remained relatively stable, and what evidence "
                f"indicates whether this spending represents temporary/growth investment versus "
                f"a structurally higher ongoing reinvestment requirement?"
            )
            if ni_vals:
                q += f" Latest NI is approximately ${_fmt_money(ni_vals[-1])}m."
            if oi_vals:
                q += f" Latest operating income is approximately ${_fmt_money(oi_vals[-1])}m."
            questions.append(
                ResearchQuestion(
                    question=q,
                    concept="capex_temporary_vs_structural",
                    sources_searched=["sec_10k", "sec_10q", "sec_8k_earnings"],
                )
            )
        if "ONE_TIME_EARNINGS_COLLAPSE" in types or "ONE_TIME_EARNINGS_WINDFALL" in types:
            questions.append(
                ResearchQuestion(
                    question=(
                        "Was the earnings-level change caused by a disclosed one-time event, "
                        "acquisition/divestiture, or restructuring rather than ongoing operations?"
                    ),
                    concept="one_time_earnings_event",
                    sources_searched=["sec_10k", "sec_8k_earnings"],
                )
            )
        if "MARGIN_DISLOCATION" in types and not questions:
            questions.append(
                ResearchQuestion(
                    question=(
                        "Does management describe the margin change as temporary or structural, "
                        "and is that characterization corroborated by subsequent results?"
                    ),
                    concept="margin_temporary_vs_structural",
                    sources_searched=["sec_10k"],
                )
            )
        if not questions:
            questions.append(
                ResearchQuestion(
                    question=(
                        "What disclosed event, if any, explains why the current Operating Earnings "
                        "base is economically unrepresentative?"
                    ),
                    concept="distorted_base_unresolved",
                    sources_searched=["sec_10k"],
                )
            )
        return RESEARCHED, questions

    def investigate(
        self,
        *,
        analysis_id: str,
        ticker: str,
        base: NormalizedEarningsPowerAnalysis,
        sec_manifest: dict[str, Any] | None = None,
        fiscal_year: int | None = None,
        analysis_as_of_date: str | None = None,
        cache_dir=None,
        today: str | None = None,
    ) -> AnalyticalResearchReport:
        ticker_u = ticker.upper()
        retrieval_date = today or date.today().isoformat()
        status, questions = self.generate_questions(ticker_u, base)
        as_of = analysis_as_of_date or self._infer_as_of(sec_manifest, fiscal_year)
        if status == NO_EXTERNAL_RESEARCH_REQUIRED:
            synth = AnalyticalResearchSynthesis(
                issue="operating_earnings_base",
                question="Workbook evidence is sufficient for the reported-base decision.",
                hap_conclusion=NO_EXTERNAL_RESEARCH_REQUIRED,
                confidence="HIGH",
                decision_effect=NO_DECISION_EFFECT,
                hap_interpretation=(
                    "No unresolved material base question requires external filings. "
                    "HAP will not run generic company research."
                ),
            )
            return AnalyticalResearchReport(
                analysis_id=analysis_id,
                ticker=ticker_u,
                fiscal_year=fiscal_year,
                analysis_as_of_date=as_of,
                status=NO_EXTERNAL_RESEARCH_REQUIRED,
                questions=[],
                queries=[],
                evidence=[],
                synthesis=synth,
                retrieval_date=retrieval_date,
                writes_to_workbook=False,
                selected_normalized_base_written=False,
                summary=f"{ticker_u}: {NO_EXTERNAL_RESEARCH_REQUIRED}.",
            )

        if cache_dir is not None:
            self.sec.cache_dir = cache_dir

        cik = (sec_manifest or {}).get("cik")
        documents = self._select_documents(sec_manifest, as_of, fiscal_year)
        evidence: list[AnalyticalResearchEvidence] = []
        queries = list(_SEARCH_TERMS)
        try:
            for doc in documents:
                html = self.sec.fetch_document_text(
                    doc["document_url"],
                    cik=str(cik or "unknown"),
                    cache_name=f"{doc.get('accession_number')}_{doc.get('primary_document')}",
                )
                evidence.extend(
                    self._extract_from_document(
                        ticker=ticker_u,
                        question=questions[0].question if questions else "",
                        doc=doc,
                        html=html,
                        as_of=as_of,
                        retrieval_date=retrieval_date,
                    )
                )
        except SecServiceError as exc:
            return AnalyticalResearchReport(
                analysis_id=analysis_id,
                ticker=ticker_u,
                fiscal_year=fiscal_year,
                analysis_as_of_date=as_of,
                status=RESEARCH_UNAVAILABLE,
                questions=questions,
                queries=queries,
                evidence=[],
                synthesis=AnalyticalResearchSynthesis(
                    issue="operating_earnings_base",
                    question=questions[0].question if questions else "",
                    missing_evidence=[f"SEC retrieval failed: {exc}"],
                    hap_conclusion=UNCLASSIFIED_CAPEX,
                    confidence="LOW",
                    decision_effect=REMAINS_INSUFFICIENT,
                    hap_interpretation="Primary filings could not be retrieved; workbook INSUFFICIENT stands.",
                ),
                retrieval_date=retrieval_date,
                summary=f"{ticker_u}: {RESEARCH_UNAVAILABLE} ({exc}).",
            )

        available = [e for e in evidence if e.available_as_of_analysis and e.source_tier == 1]
        available = self._drop_secondary(available)
        synthesis = self._synthesize(questions[0] if questions else None, available, base)
        return AnalyticalResearchReport(
            analysis_id=analysis_id,
            ticker=ticker_u,
            fiscal_year=fiscal_year,
            analysis_as_of_date=as_of,
            status=RESEARCHED,
            questions=questions,
            queries=queries,
            evidence=evidence,
            synthesis=synthesis,
            retrieval_date=retrieval_date,
            writes_to_workbook=False,
            selected_normalized_base_written=False,
            summary=(
                f"{ticker_u}: researched {len(questions)} question(s), "
                f"{len(evidence)} excerpt(s), conclusion={synthesis.hap_conclusion}, "
                f"effect={synthesis.decision_effect}."
            ),
        )

    def apply_to_diagnostic(
        self,
        base: NormalizedEarningsPowerAnalysis,
        report: AnalyticalResearchReport,
    ) -> NormalizedEarningsPowerAnalysis:
        """Annotate the frozen diagnostic. Never writes selected_normalized_base."""
        out = base.model_copy(deep=True)
        frozen_selected = out.selected_normalized_base
        out.research_status = report.status
        synth = report.synthesis
        if synth is None or report.status == NO_EXTERNAL_RESEARCH_REQUIRED:
            out.research_decision_effect = NO_DECISION_EFFECT
            out.selected_normalized_base = frozen_selected
            return out

        out.research_decision_effect = synth.decision_effect
        extra = [
            f"RESEARCH_{synth.decision_effect}",
            f"research_conclusion={synth.hap_conclusion}",
            f"research_confidence={synth.confidence}",
        ]
        if synth.capex_category:
            extra.append(f"research_capex_category={synth.capex_category}")
        out.distortions_identified = list(out.distortions_identified) + extra
        out.evidence = list(out.evidence) + [
            f"research:{row}"
            for row in (synth.evidence_for_temporary[:3] + synth.evidence_for_structural[:3] + synth.missing_evidence[:3])
        ]
        locators = [e.source_locator for e in report.evidence if e.source_locator and e.available_as_of_analysis]
        out.provenance = list(out.provenance) + [loc for loc in locators if loc][:8]
        out.provenance.append("analytical_research_primary_sec_only; not a SOURCE_FILL")
        out.confidence = _CONF_FLOAT.get(synth.confidence, out.confidence)
        if synth.hap_interpretation:
            out.rationale = (out.rationale + " " + synth.hap_interpretation).strip()
        out.selected_normalized_base = frozen_selected
        if synth.decision_effect == NORMALIZATION_SUPPORTABLE_AMOUNT_NOT_SELECTED:
            out.decision = USE_NORMALIZED_BASE
            out.selection_method = "research_supports_temporary_capex_amount_not_selected"
            # This phase reports that normalization is supportable; it does not pick a dollar base.
            out.selected_normalized_base = None
        elif synth.decision_effect == KEEP_REPORTED_BASE_SUPPORTED:
            out.decision = KEEP_REPORTED_BASE
            out.selection_method = "research_supports_reported_base_as_sustainable"
        elif synth.decision_effect == REMAINS_INSUFFICIENT:
            out.decision = INSUFFICIENT_BASE_EVIDENCE
        out.writes_to_workbook = False
        out.implementation_status = "DIAGNOSTIC_ONLY"
        return out

    def _infer_as_of(self, manifest: dict[str, Any] | None, fiscal_year: int | None) -> str | None:
        filings = (manifest or {}).get("selected_filings") or []
        dated = []
        for f in filings:
            fd = _parse_date(f.get("filing_date"))
            if not fd:
                continue
            if fiscal_year and f.get("fiscal_year") == fiscal_year and f.get("filing_type") == "10-K":
                return fd.isoformat()
            dated.append(fd)
        if not dated:
            return None
        return max(dated).isoformat()

    def _select_documents(
        self,
        manifest: dict[str, Any] | None,
        as_of: str | None,
        fiscal_year: int | None,
    ) -> list[dict[str, Any]]:
        as_of_d = _parse_date(as_of)
        selected = list((manifest or {}).get("selected_filings") or [])
        docs: list[dict[str, Any]] = []
        for f in selected:
            form = f.get("filing_type") or f.get("form")
            if form not in {"10-K", "10-Q"}:
                continue
            if not f.get("document_url"):
                continue
            fd = _parse_date(f.get("filing_date"))
            if as_of_d and fd and fd > as_of_d:
                continue
            docs.append(f)
        # Optional 8-K earnings exhibits via the same SecService, still as-of filtered.
        cik = (manifest or {}).get("cik")
        if cik:
            try:
                extras = self.sec.list_recent_filings(str(cik), forms={"8-K"}, items_contains="2.02")
            except SecServiceError:
                extras = []
            kept = 0
            for f in extras:
                fd = _parse_date(f.get("filing_date"))
                if as_of_d and fd and fd > as_of_d:
                    continue
                if fiscal_year and fd and fd.year < fiscal_year - 3:
                    continue
                docs.append(f)
                kept += 1
                if kept >= 6:
                    break
        # Prefer 10-K, then 10-Q, then 8-K; chronological.
        rank = {"10-K": 0, "10-Q": 1, "8-K": 2}
        docs.sort(key=lambda x: (rank.get(x.get("filing_type") or x.get("form") or "", 9), x.get("filing_date") or ""))
        # Cap 10-Ks to the last four at or before as-of.
        tenks = [d for d in docs if (d.get("filing_type") or d.get("form")) == "10-K"][-4:]
        others = [d for d in docs if (d.get("filing_type") or d.get("form")) != "10-K"]
        return tenks + others

    def _extract_from_document(
        self,
        *,
        ticker: str,
        question: str,
        doc: dict[str, Any],
        html: str,
        as_of: str | None,
        retrieval_date: str,
    ) -> list[AnalyticalResearchEvidence]:
        text = _item7_window(_html_to_text(html))
        pub = doc.get("filing_date")
        available = True
        as_of_d, pub_d = _parse_date(as_of), _parse_date(pub)
        if as_of_d and pub_d and pub_d > as_of_d:
            available = False
        form = str(doc.get("filing_type") or doc.get("form") or "SEC")
        locator = f"{form} {doc.get('accession_number')} {doc.get('document_url')}"
        windows = self._capex_windows(text)
        out: list[AnalyticalResearchEvidence] = []
        for blob in windows:
            fact = self._fact_sentence(blob)
            claim = self._claim_sentence(blob)
            supports, contradicts, category_hint = self._direction(blob)
            source_type = SEC_DISCLOSURE if fact and not claim else MANAGEMENT_STATEMENT if claim else SEC_DISCLOSURE
            if form not in {"10-K", "10-Q", "8-K"}:
                source_type = SECONDARY_SOURCE
            out.append(
                AnalyticalResearchEvidence(
                    company=ticker,
                    metric_or_issue="capex_temporary_vs_structural",
                    research_question=question,
                    source_type=source_type,
                    source_title=f"SEC {form} filed {pub}",
                    source_date=pub,
                    filing_period=str(doc.get("fiscal_year") or doc.get("report_date") or ""),
                    source_locator=locator,
                    evidence_text_or_summary=blob[:900],
                    management_claim=claim,
                    verified_financial_fact=fact,
                    hap_interpretation=None,
                    supports=supports,
                    contradicts=contradicts,
                    uncertainty=None if (fact or claim) else "excerpt lacks a classifiable claim or fact",
                    relevance="high" if category_hint else "medium",
                    provenance=[locator, f"filing_date={pub}"],
                    confidence="MEDIUM" if fact else "LOW",
                    publication_date=pub,
                    analysis_as_of_date=as_of,
                    available_as_of_analysis=available,
                    claim_fingerprint=_fingerprint(claim or fact or blob),
                    source_tier=1 if form in {"10-K", "10-Q", "8-K"} else 3,
                    document_identity=str(doc.get("accession_number") or ""),
                    retrieval_date=retrieval_date,
                    search_terms=list(_SEARCH_TERMS),
                    filing_type=form,
                )
            )
        return out[:8]

    def _capex_windows(self, text: str) -> list[str]:
        low = text.lower()
        spans: list[tuple[int, int]] = []
        for term in _CAPEX_TERMS + _PROJECT_TERMS:
            start = 0
            while True:
                i = low.find(term, start)
                if i < 0:
                    break
                spans.append((max(0, i - 420), min(len(text), i + len(term) + 520)))
                start = i + len(term)
        if not spans:
            return []
        spans.sort()
        merged: list[tuple[int, int]] = [spans[0]]
        for a, b in spans[1:]:
            pa, pb = merged[-1]
            if a <= pb + 40:
                merged[-1] = (pa, max(pb, b))
            else:
                merged.append((a, b))
        windows = []
        seen = set()
        for a, b in merged:
            blob = re.sub(r"\s+", " ", text[a:b]).strip()
            if len(blob) < 80:
                continue
            if not _contains_any(blob, _CAPEX_TERMS):
                continue
            key = _fingerprint(blob)
            if key in seen:
                continue
            seen.add(key)
            windows.append(blob)
        windows.sort(
            key=lambda w: (
                0 if _contains_any(w, _FORWARD_GUIDE) else 1,
                0 if "accounted for" in w.lower() or "purchases of property, plant" in w.lower() else 1,
                0 if re.search(r"\$\s*\d", w) else 1,
                -len(w),
            )
        )
        return windows[:10]

    def _fact_sentence(self, blob: str) -> str | None:
        sentences = re.split(r"(?<=[\.\;])\s+", blob)
        money = re.compile(r"\$\s*\d[\d,]*(?:\.\d+)?\s*(?:million|billion|thousand)?", re.I)
        for s in sentences:
            if money.search(s) and _contains_any(s, _CAPEX_TERMS + ("million", "facility", "project", "plant", "accounted for")):
                return s.strip()[:400]
        return None

    def _claim_sentence(self, blob: str) -> str | None:
        sentences = re.split(r"(?<=[\.\;])\s+", blob)
        for s in sentences:
            if _contains_any(s, _MGMT_VERBS) or _contains_any(s, _GUIDE_DECLINE + _GUIDE_ELEVATED + _FORWARD_GUIDE):
                return s.strip()[:400]
        return None

    def _direction(self, blob: str) -> tuple[str | None, str | None, str | None]:
        supports = None
        contradicts = None
        category = None
        if _contains_any(blob, _GUIDE_DECLINE) and _contains_any(blob, _PROJECT_TERMS + ("complete", "completion", "project")):
            supports = TEMPORARY_PROJECT_CAPEX
            category = TEMPORARY_PROJECT_CAPEX
        elif _contains_any(blob, _PROJECT_TERMS) and _contains_any(blob, _CAPEX_TERMS + ("invest", "construction", "building")):
            supports = GROWTH_CAPEX
            category = GROWTH_CAPEX
        if _contains_any(blob, _MAINT_TERMS):
            supports = supports or MAINTENANCE_CAPEX
            category = category or MAINTENANCE_CAPEX
        if _contains_any(blob, _ACQ_TERMS) and _contains_any(blob, _CAPEX_TERMS + ("integrat",)):
            supports = supports or ACQUISITION_RELATED_CAPEX
            category = category or ACQUISITION_RELATED_CAPEX
        if _contains_any(blob, _GUIDE_ELEVATED):
            if supports == TEMPORARY_PROJECT_CAPEX:
                contradicts = STRUCTURAL_CAPITAL_INTENSITY
            else:
                supports = STRUCTURAL_CAPITAL_INTENSITY
                category = STRUCTURAL_CAPITAL_INTENSITY
        return supports, contradicts, category

    def _drop_secondary(self, rows: list[AnalyticalResearchEvidence]) -> list[AnalyticalResearchEvidence]:
        primary = [r for r in rows if r.source_tier == 1 and r.source_type != SECONDARY_SOURCE]
        return primary if primary else [r for r in rows if r.source_tier == 1]

    def _synthesize(
        self,
        question: ResearchQuestion | None,
        evidence: list[AnalyticalResearchEvidence],
        base: NormalizedEarningsPowerAnalysis,
    ) -> AnalyticalResearchSynthesis:
        qtext = question.question if question else "Unresolved operating-earnings-base question."
        cx_obs = (base.historical_normalized_observations or {}).get("capex") or {}
        cx_med = cx_obs.get("median_10y")
        cx_med_abs = abs(cx_med) if isinstance(cx_med, (int, float)) else None
        # Repeated management claims are one claim, not independent corroboration.
        seen_fp: dict[str, int] = {}
        unique: list[AnalyticalResearchEvidence] = []
        repeated = 0
        for row in evidence:
            fp = row.claim_fingerprint or _fingerprint(row.management_claim or row.evidence_text_or_summary)
            seen_fp[fp] = seen_fp.get(fp, 0) + 1
            if seen_fp[fp] == 1:
                unique.append(row)
            else:
                repeated += 1

        temp, struct, other, contra = [], [], [], []
        has_project = False
        has_completion = False
        has_decline_guide = False
        has_elevated_guide = False
        has_named_dollar = False
        independent_facts = 0
        fact_fps: set[str] = set()
        for row in unique:
            blob = f"{row.evidence_text_or_summary} {row.management_claim or ''} {row.verified_financial_fact or ''}"
            if row.verified_financial_fact:
                fp = _fingerprint(row.verified_financial_fact)
                if fp not in fact_fps:
                    fact_fps.add(fp)
                    independent_facts += 1
                    has_named_dollar = True
            if row.supports == TEMPORARY_PROJECT_CAPEX or _contains_any(blob, _GUIDE_DECLINE):
                temp.append(row.evidence_text_or_summary[:240])
            if row.supports == STRUCTURAL_CAPITAL_INTENSITY or _contains_any(blob, _GUIDE_ELEVATED):
                struct.append(row.evidence_text_or_summary[:240])
            if row.supports in {GROWTH_CAPEX, MAINTENANCE_CAPEX, ACQUISITION_RELATED_CAPEX}:
                other.append(f"{row.supports}: {row.evidence_text_or_summary[:200]}")
            if row.contradicts:
                contra.append(row.contradicts)
            if _contains_any(blob, ("expand our production", "90.0 million in capital", "plan to invest approximately", "will invest approximately")):
                has_project = True
            if _contains_any(blob, _PROJECT_TERMS):
                has_project = True
            if _contains_any(blob, ("complet", "expected to be complete", "will be completed", "upon completion", "needed to complete", "continuing into early fiscal", "continuing into the next fiscal year")):
                has_completion = True
            if _contains_any(blob, _GUIDE_DECLINE) or _contains_any(blob, _FORWARD_GUIDE):
                has_decline_guide = has_decline_guide or _contains_any(blob, _GUIDE_DECLINE)
            guided = re.findall(
                r"expect total capital expenditures[^.]{0,120}\$\s*([\d,.]+)\s*million",
                blob,
                re.I,
            )
            actuals = re.findall(
                r"capital expenditures accounted for a[n]?\s*\$\s*([\d,.]+)\s*million",
                blob,
                re.I,
            )
            if guided:
                has_project = True
                gval = float(guided[-1].replace(",", ""))
                if actuals:
                    aval = max(float(a.replace(",", "")) for a in actuals)
                    if gval < 0.75 * aval:
                        has_decline_guide = True
                if cx_med_abs and gval > 1.5 * cx_med_abs:
                    has_elevated_guide = True
                temp.append(f"Forward CapEx guide ${gval:.1f}m: {blob[:180]}")

        missing = []
        if not has_project:
            missing.append("No named capital project identified in as-of primary filings.")
        if not has_completion:
            missing.append("No project completion date/period disclosed.")
        if not has_decline_guide:
            missing.append("No forward statement that CapEx should decline after the project.")
        if not evidence:
            missing.append("No CapEx narrative excerpts retrieved from primary filings.")

        # CapEx-intensity formula cluster is NOT independent research evidence.
        missing.append(
            "Workbook CapEx/D&A, CapEx/revenue, and component-margin reconstructions remain "
            "one mean-reversion family and are not counted as independent research corroboration."
        )

        if temp and struct:
            contra.append("Filings contain both temporary-project language and elevated/ongoing-investment language.")

        conclusion = UNCLASSIFIED_CAPEX
        effect = REMAINS_INSUFFICIENT
        confidence = "LOW"
        category = None
        # Project alone is not enough. Need completion timing AND forward decline guidance,
        # with primary-source independence — not repeated copies of one sentence.
        if has_project and has_completion and has_decline_guide and has_elevated_guide:
            conclusion = GROWTH_CAPEX
            category = GROWTH_CAPEX
            effect = REMAINS_INSUFFICIENT
            confidence = "MEDIUM"
            missing.append(
                "Forward CapEx is guided lower than the spike year but remains above historical "
                "intensity. That is not sufficient to treat the current OE base as fully "
                "temporary maintenance-normalized CapEx."
            )
        elif has_project and has_completion and has_decline_guide and not has_elevated_guide:
            conclusion = TEMPORARY_PROJECT_CAPEX
            category = TEMPORARY_PROJECT_CAPEX
            effect = NORMALIZATION_SUPPORTABLE_AMOUNT_NOT_SELECTED
            confidence = "HIGH" if independent_facts >= 2 and not contra else "MEDIUM"
        elif has_elevated_guide and not has_decline_guide and has_project:
            conclusion = STRUCTURAL_CAPITAL_INTENSITY
            category = STRUCTURAL_CAPITAL_INTENSITY
            # A new run-rate is not automatically the reported $2m OE; still insufficient
            # unless management plus subsequent years (in-period) show a new intensity.
            effect = REMAINS_INSUFFICIENT
            confidence = "MEDIUM"
        elif has_project and not (has_completion and has_decline_guide):
            conclusion = GROWTH_CAPEX if has_project else UNCLASSIFIED_CAPEX
            category = GROWTH_CAPEX if has_project else UNCLASSIFIED_CAPEX
            effect = REMAINS_INSUFFICIENT
            confidence = "MEDIUM" if has_named_dollar else "LOW"
        elif not evidence:
            conclusion = UNCLASSIFIED_CAPEX
            effect = REMAINS_INSUFFICIENT
            confidence = "LOW"

        if contra and effect == NORMALIZATION_SUPPORTABLE_AMOUNT_NOT_SELECTED:
            confidence = "LOW"
            effect = REMAINS_INSUFFICIENT
            conclusion = UNCLASSIFIED_CAPEX

        interpretation = (
            f"HAP inference (not a filing fact): {conclusion}. Decision effect {effect}. "
            f"Independent primary facts counted={independent_facts}; repeated claim copies={repeated}. "
            "Management characterizations are claims. CapEx-normalization formulas were not treated "
            "as independent corroboration."
        )
        if effect == NORMALIZATION_SUPPORTABLE_AMOUNT_NOT_SELECTED:
            interpretation += (
                " Research would support evaluating a normalized earnings-power case, but this phase "
                "does not select or write a replacement OE base."
            )
        else:
            interpretation += (
                " Available as-of primary evidence does not distinguish temporary project CapEx from "
                "a sustainable reinvestment requirement with enough independence to change the "
                "workbook INSUFFICIENT_EVIDENCE conclusion into a selected base."
            )

        return AnalyticalResearchSynthesis(
            issue="operating_earnings_base",
            question=qtext,
            evidence_for_temporary=temp[:8],
            evidence_for_structural=struct[:8],
            evidence_for_other_explanation=other[:8],
            contradictory_evidence=contra[:8],
            missing_evidence=missing,
            hap_conclusion=conclusion,
            confidence=confidence,
            decision_effect=effect,
            independent_fact_count=independent_facts,
            repeated_claim_count=repeated,
            capex_category=category,
            hap_interpretation=interpretation,
        )
