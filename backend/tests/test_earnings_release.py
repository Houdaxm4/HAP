"""Management commentary taken from the SEC earnings release (no network: the extractor works on text)."""

from services.earnings_release_service import ReleaseCommentary, extract_commentary
from services.email_draft_service import Facts, SheetFields, render_quarter

RELEASE = """
<html><body>
<p>Acme Corp Reports Third Quarter 2026 Results</p>
<p>Revenue for the third quarter increased 12% to $4.1 billion, driven primarily by higher demand for the company's data center products.</p>
<p>Operating margin expanded as a result of lower freight costs and a better product mix across all segments.</p>
<p>We expect to invest approximately $300 million in new manufacturing capacity over the next two years and we plan to launch two products in 2027.</p>
<p>The Company expects full year 2026 revenue of $16.0 billion to $16.5 billion.</p>
<p>This press release contains forward-looking statements that involve risks and uncertainties; investors should not place undue reliance on them.</p>
<p>The conference call will be webcast at www.acme.com.</p>
<table><tr><td>Revenue</td><td>4,100</td><td>3,660</td></tr></table>
</body></html>
"""


def test_results_and_outlook_are_picked_from_prose_without_disclaimers_or_tables():
    out = extract_commentary(RELEASE)
    assert out.status == "FOUND"
    assert any("driven primarily by higher demand" in s for s in out.results)
    assert any("invest approximately $300 million" in s for s in out.outlook) and any("full year 2026" in s for s in out.outlook)
    everything = " ".join(out.results + out.outlook)
    assert "forward-looking" not in everything and "webcast" not in everything and "Reports Third Quarter" not in everything
    assert not set(out.results) & set(out.outlook)                         # a sentence sits under one heading only


def test_a_release_without_prose_gives_no_commentary():
    assert extract_commentary("<p>Revenue 4,100 3,660</p>").status == "NO_COMMENTARY"


def _facts_q3(release):
    f = Facts(ticker="ACME", price=10.0)
    f.quarter_number, f.quarter_year, f.quarter_label, f.ytd_label = 3, 2026, "2026 Q3", "9M"
    f.release = release
    return f


def test_the_highlights_section_shows_results_explanation_and_plans_with_their_source():
    release = ReleaseCommentary(results=["Revenue grew on data center demand."], outlook=["We plan to add capacity in 2027."],
                                filed="2026-10-29", status="FOUND")
    _subject, body = render_quarter(_facts_q3(release), sheet=SheetFields(classified_as="Q", pe10_status="Buy"))
    assert "Management's explanation of the results (SEC 8-K earnings release filed 2026-10-29):\n- Revenue grew on data center demand." in body
    assert "short and medium term" in body and "- We plan to add capacity in 2027." in body and "transcript itself was not available" in body


def test_missing_commentary_leaves_bracketed_lines_for_the_analyst():
    _subject, body = render_quarter(_facts_q3(ReleaseCommentary(status="NO_8K")), sheet=SheetFields())
    assert "[Management's plans for the short and medium term: nothing usable in the earnings release" in body
    _subject, plain = render_quarter(_facts_q3(None), sheet=SheetFields())
    assert "Management's" not in plain                                      # no release attempted: the section is as before
