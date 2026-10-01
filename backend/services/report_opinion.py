"""Fundamentals and valuation sections of the report (rules-based facts + a slot for the analyst opinion).

The verdicts here come from HAP's own scores; they are not opinions. Step "opinion from online intelligence" fills
the labeled opinion slot separately and never replaces these.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

OPINION_PENDING = "Analyst opinion: pending (generated on request from online sources and the workbook; needs Claude access)."
OPINION_LABEL = "Analyst opinion (not a HAP rules-based result; based on online sources and the workbook):"
ASSESSMENT_FILE = "report_assessment.json"
STRONG_BQ_SCORE = 70.0  # HIGH_QUALITY_BUSINESS and above (see final_recommendation_service bands)
HOUSE_MOS = 0.25


def _read(directory: Path, name: str) -> dict[str, Any]:
    path = directory / name
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _pct(value: Any) -> str:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return "n/a"
    return f"{value * 100:.1f}%" if abs(value) <= 1.5 else f"{value:.1f}%"


def _num(value: Any, digits: int = 2) -> str:
    return "n/a" if not isinstance(value, (int, float)) or isinstance(value, bool) else f"{value:,.{digits}f}"


def _label(value: Any) -> str:
    return str(value or "n/a").replace("_", " ").lower()


def fundamentals_assessment(output_dir: Path, valuation: Any = None, history: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    final = _read(output_dir, "final_recommendation_report.json")
    score = final.get("business_quality_score")
    facts: list[str] = []
    if score is not None:
        facts.append(f"Business-quality score {_num(score, 0)} ({_label(final.get('business_quality_classification'))}).")
    roic_wacc = getattr(valuation, "roic_wacc", None) if valuation is not None else None
    roce = getattr(valuation, "roce", None) if valuation is not None else None
    if roic_wacc is not None:
        facts.append(f"ROIC minus WACC {_pct(roic_wacc)}; ROCE {_pct(roce)}.")
    if history:
        usable = [h for h in history if h.get("revenue")]
        if len(usable) >= 2:
            first, last = usable[0], usable[-1]
            years = max(len(usable) - 1, 1)
            cagr = (last["revenue"] / first["revenue"]) ** (1 / years) - 1
            facts.append(f"Revenue {first['fiscal_year']}-{last['fiscal_year']}: {_num(first['revenue'], 0)} to {_num(last['revenue'], 0)} ($M), {_pct(cagr)} a year.")
            if last.get("operating_margin") is not None and first.get("operating_margin") is not None:
                facts.append(f"Operating margin {_pct(first['operating_margin'])} to {_pct(last['operating_margin'])}.")
    if not isinstance(score, (int, float)):
        strong = None  # this report type carries no business-quality score: the rules give no verdict
    else:
        strong = score >= STRONG_BQ_SCORE and (roic_wacc is None or roic_wacc > 0)
    return {
        "strong": strong,
        "score": score,
        "facts": facts,
        "against": list(final.get("reasons_against", []))[:4],
        "for": list(final.get("reasons_for", []))[:4],
    }


def valuation_assessment(output_dir: Path, valuation: Any = None) -> dict[str, Any]:
    final = _read(output_dir, "final_recommendation_report.json")
    price = final.get("current_price") or getattr(valuation, "current_price", None)
    intrinsic = final.get("intrinsic_value")
    mos = final.get("margin_of_safety")
    ev_per_share = getattr(valuation, "company_value_per_share", None) if valuation is not None else None
    ev_mos = getattr(valuation, "enterprise_mos", None) if valuation is not None else None
    facts = []
    if price is not None:
        facts.append(f"Current price {_num(price)}.")
    if ev_per_share is not None:
        facts.append(f"Enterprise (owner-earnings) value per share {_num(ev_per_share)}; margin of safety {_pct(ev_mos)}.")
    if intrinsic is not None:
        facts.append(f"Graham intrinsic value {_num(intrinsic)}; margin of safety {_pct(mos)}.")
    pe10 = getattr(valuation, "current_pe10", None) if valuation is not None else None
    expected = getattr(valuation, "expected_annual_return", None) if valuation is not None else None
    if pe10 is not None:
        facts.append(f"PE10 {_num(pe10, 1)}x.")
    if expected is not None:
        facts.append(f"Expected annual return at the current price {_pct(expected)}.")
    margins = [m for m in (mos, ev_mos) if isinstance(m, (int, float))]
    cheap = bool(margins) and min(margins) >= HOUSE_MOS
    verdict = "cheap" if cheap else ("not cheap" if margins else "cannot be judged (valuation inputs unavailable)")
    return {"verdict": verdict, "cheap": cheap, "facts": facts, "status": final.get("valuation_status")}


def write_assessment_sections(doc, output_dir: Path, valuation: Any = None, history: list[dict[str, Any]] | None = None,
                              opinion: dict[str, str] | None = None) -> None:
    """Fundamentals section; the valuation (enterprise value) discussion only when the fundamentals are strong."""
    fundamentals = fundamentals_assessment(output_dir, valuation, history)
    doc.add_heading("Fundamentals: how strong are they?", level=1)
    if fundamentals["strong"] is None:
        doc.add_paragraph(
            "Rules-based assessment: not available (this report type has no business-quality score). "
            "The opinion below is based on this period's results, the workbook and online sources."
        )
    else:
        doc.add_paragraph(
            "Rules-based assessment: " + ("STRONG." if fundamentals["strong"] else "NOT RATED STRONG.")
            + f" (strong means a business-quality score of {STRONG_BQ_SCORE:.0f} or more and ROIC above WACC)"
        )
    for fact in fundamentals["facts"]:
        doc.add_paragraph(fact, style="List Bullet")
    if fundamentals["for"]:
        doc.add_paragraph("In favour: " + " ".join(fundamentals["for"]))
    if fundamentals["against"]:
        doc.add_paragraph("Against: " + " ".join(fundamentals["against"]))
    if opinion and opinion.get("fundamentals"):
        doc.add_paragraph(OPINION_LABEL)
        doc.add_paragraph(opinion["fundamentals"])
    else:
        doc.add_paragraph(OPINION_PENDING)

    valuation_facts = valuation_assessment(output_dir, valuation)
    _save_assessment(output_dir, fundamentals, valuation_facts)

    doc.add_heading("Valuation: is the company cheap?", level=1)
    if fundamentals["strong"] is None:
        for fact in valuation_facts["facts"]:
            doc.add_paragraph(fact, style="List Bullet")
        if opinion and opinion.get("valuation"):
            doc.add_paragraph(OPINION_LABEL)
            doc.add_paragraph(opinion["valuation"])
        else:
            doc.add_paragraph(OPINION_PENDING)
        return
    if not fundamentals["strong"]:
        doc.add_paragraph(
            "The fundamentals are not rated strong, so the price is not treated as an opportunity. "
            "Valuation figures are shown for reference only."
        )
        for fact in valuation_facts["facts"]:
            doc.add_paragraph(fact, style="List Bullet")
        return
    doc.add_paragraph(f"Rules-based assessment: the company looks {valuation_facts['verdict']} (house margin-of-safety threshold {HOUSE_MOS * 100:.0f}%).")
    for fact in valuation_facts["facts"]:
        doc.add_paragraph(fact, style="List Bullet")
    if opinion and opinion.get("valuation"):
        doc.add_paragraph(OPINION_LABEL)
        doc.add_paragraph(opinion["valuation"])
    else:
        doc.add_paragraph(OPINION_PENDING)


def _save_assessment(output_dir: Path, fundamentals: dict[str, Any], valuation_facts: dict[str, Any]) -> None:
    """Keep the rules-based verdicts next to the report so the opinion step reacts to the same numbers."""
    try:
        with (output_dir / ASSESSMENT_FILE).open("w", encoding="utf-8") as handle:
            json.dump({"fundamentals": fundamentals, "valuation": valuation_facts}, handle, indent=2, default=str)
    except OSError:
        pass  # the report must not fail because a side file could not be written


def apply_opinion_to_docx(docx_path: Path, opinion: dict[str, str]) -> int:
    """Put the generated opinions into an existing report. Returns how many sections were written.

    A section has a slot when it holds the 'pending' marker or an earlier opinion (label + body), so the opinion can be
    regenerated. The first slot is the fundamentals section, the second (strong fundamentals only) the valuation
    section. Nothing else in the document is touched.
    """
    from docx import Document

    document = Document(str(docx_path))
    paragraphs = document.paragraphs
    slots = []  # (marker paragraph, existing body paragraph or None)
    for index, paragraph in enumerate(paragraphs):
        text = paragraph.text.strip()
        if text == OPINION_PENDING:
            slots.append((paragraph, None))
        elif text == OPINION_LABEL and index + 1 < len(paragraphs):
            slots.append((paragraph, paragraphs[index + 1]))
    filled = 0
    for position, ((marker, body), text) in enumerate(zip(slots, (opinion.get("fundamentals"), opinion.get("valuation")))):
        if not text:
            if position == 1 and body is None and opinion.get("fundamentals"):
                marker.text = "Valuation opinion not written: the fundamentals were not rated strong."
            continue
        marker.text = OPINION_LABEL
        if body is not None:
            body.text = text
        else:
            _insert_paragraph_after(marker, text)
        filled += 1
    if filled:
        document.save(str(docx_path))
    return filled


def _insert_paragraph_after(paragraph, text: str):
    from copy import deepcopy

    clone = deepcopy(paragraph._p)
    paragraph._p.addnext(clone)
    from docx.text.paragraph import Paragraph

    new = Paragraph(clone, paragraph._parent)
    new.text = text
    return new
