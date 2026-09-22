"""Concise OE-base analyst disclosure. Communication only — never a substituted base."""

from __future__ import annotations

import re
from typing import Any

from models.annual_update import (
    DISCLOSE_DISTORTED_BASE,
    INSUFFICIENT_BASE_EVIDENCE,
    KEEP_REPORTED_BASE,
    MANAGEMENT_STATEMENT,
    NO_DISCLOSURE_REQUIRED,
    NO_EXTERNAL_RESEARCH_REQUIRED,
    AnalyticalResearchReport,
    NormalizedBaseDisclosure,
    NormalizedEarningsPowerAnalysis,
)

_CAPEX_TYPES = {
    "CAPEX_SPIKE",
    "CAPEX_TROUGH",
    "STRUCTURAL_REINVESTMENT_CHANGE",
    "NEAR_ZERO_BASE",
}
_EARNINGS_TYPES = {"ONE_TIME_EARNINGS_COLLAPSE", "ONE_TIME_EARNINGS_WINDFALL"}
_FORBIDDEN = (
    "true oe is",
    "normalized oe is",
    "maintenance capex should",
    "capex will revert",
    "the stock is undervalued",
    "the valuation is wrong",
    "fair value should",
    "temporary capex",
    "not hap facts",
    "those characterizations are management statements",
)

_PROGRAM_RE = re.compile(
    r"(?:plan to invest|will invest|intends to invest) approximately \$\s*([\d,.]+)\s*million",
    re.I,
)
_GUIDE_YEAR_AMT_RE = re.compile(
    r"expect total capital expenditures.{0,220}?fiscal (\d{4}).{0,80}?\$\s*([\d,.]+)\s*million",
    re.I,
)
_GUIDE_AMT_YEAR_RE = re.compile(
    r"expect total capital expenditures.{0,80}?\$\s*([\d,.]+)\s*million.{0,120}?fiscal (\d{4})",
    re.I,
)
_WINDOW_RE = re.compile(r"continuing into (?:early )?fiscal (\d{4})", re.I)


def _pretty_million(token: str) -> str:
    value = _parse_million(token)
    if value is None:
        return token
    if abs(value - round(value)) < 0.05:
        return f"{value:.0f}"
    return f"{value:.1f}"


def _latest_reported_year(decomp: list[dict[str, Any]], research: AnalyticalResearchReport | None) -> int | None:
    years: list[int] = []
    for row in decomp:
        match = re.search(r"(20\d{2})", str(row.get("fy") or ""))
        if match:
            years.append(int(match.group(1)))
    if years:
        return max(years)
    if research and research.fiscal_year:
        return int(research.fiscal_year)
    return None


def format_millions(value: float | None, *, digits: int = 1) -> str:
    if value is None:
        return "n/a"
    mag = abs(value)
    if mag >= 100.0 and abs(value - round(value)) < 0.05:
        return f"{value:,.0f}"
    return f"{value:.{digits}f}"


def _abs_series(decomp: list[dict[str, Any]], key: str) -> list[float]:
    out: list[float] = []
    for row in decomp:
        v = row.get(key)
        if isinstance(v, (int, float)):
            out.append(float(v))
    return out


def _parse_million(token: str) -> float | None:
    try:
        return float(token.replace(",", ""))
    except ValueError:
        return None


class AnnualNormalizedBaseDisclosureService:
    """Build HAP_ANALYSIS disclosure from the diagnostic + optional research synthesis."""

    def build(
        self,
        base: NormalizedEarningsPowerAnalysis,
        research: AnalyticalResearchReport | None = None,
    ) -> NormalizedBaseDisclosure:
        decision = self._decision(base)
        if decision == NO_DISCLOSURE_REQUIRED:
            return NormalizedBaseDisclosure(
                metric="operating_earnings_base",
                severity=base.reported_base_status or "",
                reported_base=base.reported_current_base,
                decision=NO_DISCLOSURE_REQUIRED,
                confidence="HIGH",
                display_text="",
                word_text="",
            )

        decomp = (base.component_series or {}).get("decomposition") or []
        types = list(base.distortion_type or [])
        reported = base.reported_current_base
        driver, issue = self._driver_and_issue(types, decomp, reported)
        research_summary, research_prov, has_mgmt = self._research_summary(research, types, decomp)
        interpretation = self._interpretation(base, types, research_summary)
        unresolved = self._unresolved(base, types, research)
        implication = self._implication(reported, driver)
        display = self._compose(
            issue=issue,
            research_summary=research_summary,
            interpretation=interpretation,
            implication=implication,
        )
        self._assert_language(display)
        conf = "MEDIUM"
        if research and research.synthesis and research.synthesis.confidence:
            conf = research.synthesis.confidence
        provenance = [p for p in (base.provenance or []) if p][:3]
        provenance.extend(research_prov)
        if research is not None and research.status != NO_EXTERNAL_RESEARCH_REQUIRED:
            provenance.append("annual_analytical_research_report.json")
        provenance.append("HAP_ANALYSIS disclosure only; not SOURCE_FILL")
        if has_mgmt:
            provenance.append(
                "management characterizations treated as evidence, not as independent conclusions"
            )
        return NormalizedBaseDisclosure(
            metric="operating_earnings_base",
            severity=base.reported_base_status or "materially_distorted",
            reported_base=reported,
            issue=issue,
            primary_driver=driver,
            research_summary=research_summary,
            hap_interpretation=interpretation,
            unresolved_question=unresolved,
            valuation_implication=implication,
            decision=DISCLOSE_DISTORTED_BASE,
            confidence=conf,
            provenance=provenance[:10],
            display_text=display,
            word_text=display,
        )

    def _decision(self, base: NormalizedEarningsPowerAnalysis) -> str:
        status = (base.reported_base_status or "").lower()
        if status == "materially_distorted":
            # Substitution is not implemented; never emit DISCLOSE_NORMALIZED_BASE.
            return DISCLOSE_DISTORTED_BASE
        return NO_DISCLOSURE_REQUIRED

    def _driver_and_issue(
        self,
        types: list[str],
        decomp: list[dict[str, Any]],
        reported: float | None,
    ) -> tuple[str, str]:
        type_set = set(types)
        ni = _abs_series(decomp, "ni")
        oi = _abs_series(decomp, "operating_income")
        cx = [abs(v) for v in _abs_series(decomp, "capex")]
        if type_set & _CAPEX_TYPES:
            path = ""
            if len(cx) >= 3:
                path = " -> ".join(f"${format_millions(v)}m" for v in cx[-3:])
            ni_note = ""
            if ni:
                ni_note = f" Latest net income is about ${format_millions(ni[-1])}m"
                if oi:
                    ni_note += f" and operating income about ${format_millions(oi[-1])}m"
                ni_note += ", so the decline is not a collapse in earnings."
            driver = "elevated_capex"
            issue = (
                f"Reported owner earnings of ${format_millions(reported)}m are materially affected "
                f"by elevated capital spending"
                + (f" ({path})" if path else "")
                + "."
                + ni_note
            )
            return driver, issue
        if type_set & _EARNINGS_TYPES:
            driver = "one_time_earnings_level"
            which = "collapse" if "ONE_TIME_EARNINGS_COLLAPSE" in type_set else "windfall"
            issue = (
                f"Reported owner earnings of ${format_millions(reported)}m reflect a one-period "
                f"earnings-level {which} rather than a representative earnings-power starting point."
            )
            return driver, issue
        if "MARGIN_DISLOCATION" in type_set:
            return (
                "margin_dislocation",
                f"Reported owner earnings of ${format_millions(reported)}m sit with a margin "
                f"dislocation versus the company's own history.",
            )
        if "NEGATIVE_BASE" in type_set:
            return (
                "negative_base",
                f"Reported owner earnings of ${format_millions(reported)}m are negative and are "
                f"not a usable earnings-power starting point.",
            )
        return (
            "unrepresentative_base",
            f"Reported owner earnings of ${format_millions(reported)}m appear economically "
            f"unrepresentative of earnings power ({', '.join(types) or 'unspecified distortion'}).",
        )

    def _research_summary(
        self,
        research: AnalyticalResearchReport | None,
        types: list[str],
        decomp: list[dict[str, Any]],
    ) -> tuple[str, list[str], bool]:
        if research is None or research.status == NO_EXTERNAL_RESEARCH_REQUIRED:
            return "", [], False
        rows = [r for r in (research.evidence or []) if r.available_as_of_analysis]
        rows.sort(
            key=lambda r: (
                r.source_date or "",
                1 if (r.filing_type or "").upper() == "10-K" else 0,
            ),
            reverse=True,
        )
        locators: list[str] = []
        has_mgmt = False
        blobs: list[str] = []
        for row in rows:
            if row.source_locator and row.source_locator not in locators:
                locators.append(row.source_locator)
            if row.management_claim or row.source_type == MANAGEMENT_STATEMENT:
                has_mgmt = True
            piece = " ".join(
                x
                for x in (row.management_claim, row.verified_financial_fact, row.evidence_text_or_summary)
                if x
            )
            if piece:
                blobs.append(piece)
        blob = " ".join(blobs)
        latest_year = _latest_reported_year(decomp, research)
        parts: list[str] = []
        prog = _PROGRAM_RE.search(blob)
        prog_amt = _pretty_million(prog.group(1)) if prog else None
        window = _WINDOW_RE.search(blob)
        guide_amt = None
        for text in blobs:
            year_amt = _GUIDE_YEAR_AMT_RE.search(text)
            amt_year = _GUIDE_AMT_YEAR_RE.search(text)
            year = amt = None
            if year_amt:
                year, amt = int(year_amt.group(1)), year_amt.group(2)
            elif amt_year:
                amt, year = amt_year.group(1), int(amt_year.group(2))
            if year is None or amt is None:
                continue
            if latest_year is not None and year <= latest_year:
                continue
            guide_amt = _pretty_million(str(amt))
            break
        if prog_amt:
            span = f" extending through early FY{window.group(1)}" if window else ""
            parts.append(
                f"Company filings identify an approximately ${prog_amt} million "
                f"equipment/infrastructure expansion program{span}."
            )
        if guide_amt:
            guide_note = (
                f"Management has indicated subsequent capital spending of approximately "
                f"${guide_amt} million."
            )
            latest_cx = [abs(v) for v in _abs_series(decomp, "capex")]
            hist = latest_cx[:-2] if len(latest_cx) >= 4 else latest_cx[: max(0, len(latest_cx) - 1)]
            gval = _parse_million(str(guide_amt))
            latest = latest_cx[-1] if latest_cx else None
            hist_med = sorted(hist)[len(hist) // 2] if hist else None
            if gval is not None and latest is not None and gval < latest:
                guide_note += " That figure is below the latest year"
                if hist_med is not None and gval > hist_med * 1.1:
                    guide_note += (
                        " but remains above earlier historical levels and is not established "
                        "as a sustainable post-project reinvestment rate."
                    )
                else:
                    guide_note += (
                        ", but the available evidence does not establish a sustainable "
                        "post-project reinvestment level."
                    )
            else:
                guide_note += (
                    " The available evidence does not establish a sustainable post-project "
                    "reinvestment level."
                )
            low = blob.lower()
            if "complet" in low and ("ongoing" in low or "maintenance" in low):
                guide_note += " The figure includes remaining project work and ongoing spending."
            parts.append(guide_note)
        if has_mgmt and parts:
            if prog_amt:
                parts.append(
                    "HAP treats management's characterization of the program as evidence, not as "
                    "an independently established conclusion about sustainable capital spending."
                )
            else:
                parts.append(
                    "HAP treats management's characterization in company filings as evidence, not as "
                    "an independently established conclusion about a sustainable replacement base."
                )
        if not parts and research.synthesis and research.synthesis.hap_interpretation:
            parts.append(
                "Primary filings were reviewed for the unresolved base question; they do not "
                "establish a defensible replacement for the reported owner-earnings figure."
            )
        return " ".join(parts), locators[:4], has_mgmt

    def _interpretation(
        self,
        base: NormalizedEarningsPowerAnalysis,
        types: list[str],
        research_summary: str,
    ) -> str:
        if base.decision == INSUFFICIENT_BASE_EVIDENCE:
            capex = bool(set(types) & _CAPEX_TYPES)
            if capex and research_summary:
                return (
                    "HAP can infer that spending is elevated in connection with a disclosed "
                    "investment program. HAP cannot determine sustainable post-project capital "
                    "spending with sufficient confidence. HAP therefore retains the reported "
                    "base and flags the resulting valuation for interpretation. HAP does not "
                    "substitute a normalized owner-earnings figure."
                )
            if capex:
                return (
                    "HAP can infer that the reported base is depressed by elevated capital "
                    "spending. HAP cannot determine a sustainable reinvestment level with "
                    "sufficient confidence. HAP therefore retains the reported base and "
                    "flags the resulting valuation for interpretation. HAP does not "
                    "substitute a normalized owner-earnings figure."
                )
            return (
                "HAP can infer that the reported starting base is economically unusual. "
                "HAP cannot determine a defensible replacement owner-earnings figure with "
                "sufficient confidence. HAP therefore retains the reported base and flags "
                "the resulting valuation for interpretation. HAP does not substitute a "
                "normalized amount."
            )
        if base.decision == KEEP_REPORTED_BASE:
            return "HAP retains the reported owner-earnings base and has not replaced it."
        return (
            "HAP flags the reported owner-earnings base for interpretation and does not "
            "treat candidate reconstructions as a written replacement."
        )

    def _unresolved(
        self,
        base: NormalizedEarningsPowerAnalysis,
        types: list[str],
        research: AnalyticalResearchReport | None,
    ) -> str:
        if research and research.questions:
            return research.questions[0].question
        if set(types) & _CAPEX_TYPES:
            return (
                "What sustainable capital reinvestment level, if any, should be used to "
                "evaluate earnings power after the current investment period?"
            )
        if set(types) & _EARNINGS_TYPES:
            return (
                "Was the earnings-level change a disclosed one-time event, and if so what "
                "earnings-power figure is defensible going forward?"
            )
        return "What, if any, replacement owner-earnings base is supported by available evidence?"

    def _implication(self, reported: float | None, driver: str) -> str:
        if driver == "elevated_capex":
            reason = "materially affected by elevated investment spending"
        elif driver == "one_time_earnings_level":
            reason = "materially affected by a one-period earnings-level event"
        else:
            reason = "materially unrepresentative of earnings power"
        return (
            f"The current enterprise-value calculation begins from reported owner earnings of "
            f"${format_millions(reported)}m. Because that base is {reason}, valuation outputs "
            f"that extrapolate it should be interpreted cautiously. HAP has not changed the "
            f"original valuation."
        )

    def _compose(
        self,
        *,
        issue: str,
        research_summary: str,
        interpretation: str,
        implication: str,
    ) -> str:
        bits = [issue]
        if research_summary:
            bits.append(research_summary)
        bits.append(interpretation)
        bits.append(implication)
        text = " ".join(b.strip() for b in bits if b and b.strip())
        return re.sub(r"\s+", " ", text).strip()

    def _assert_language(self, text: str) -> None:
        low = text.lower()
        for phrase in _FORBIDDEN:
            if phrase in low:
                raise ValueError(f"Disclosure language is too precise: {phrase!r}")
        if re.search(r"normalized oe is \$?\d", low):
            raise ValueError("Disclosure must not present a candidate as the normalized base.")
