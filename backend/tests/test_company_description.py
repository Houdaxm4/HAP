from services.company_description_service import CompanyDescription, predicate_from_business_text

TOC = "Item 1. Business 1 Item 1A. Risk Factors 9 Item 1B. Unresolved Staff Comments 19 "


def _doc(body: str) -> str:
    return TOC + "x " * 40 + "Item 1. Business " + body + " " + "More text about the company. " * 40


def test_subject_with_a_parenthetical_definition_is_dropped_and_the_predicate_kept():
    text = _doc('Standex International Corporation and subsidiaries ("we," "us," "our," the "Company" and "Standex") is a diversified industrial '
                "manufacturer with leading positions in a variety of products and services that are used in diverse markets.")
    assert predicate_from_business_text(text) == "is a diversified industrial manufacturer with leading positions in a variety of products and services that are used in diverse markets"


def test_third_person_verbs_and_we_are_are_converted():
    assert predicate_from_business_text(_doc("General: We are an independent designer, manufacturer, and services provider of control solutions.")) \
        == "is an independent designer, manufacturer, and services provider of control solutions"
    assert predicate_from_business_text(_doc("Timken designs and manages a portfolio of engineered bearings and related services.")).startswith("designs and manages a portfolio")
    assert predicate_from_business_text(_doc("We design and manufacture precision products for aerospace customers.")) == "designs and manufactures precision products for aerospace customers"


def test_boilerplate_sentences_are_skipped_and_long_ones_are_clipped():
    text = _doc("As used herein, the term Company refers to Acme Inc. and its subsidiaries. This report contains forward-looking statements. "
                "Acme is a global provider of " + "widgets, " * 40 + "and gadgets.")
    out = predicate_from_business_text(text)
    assert out.startswith("is a global provider of widgets") and len(out) <= 232


def test_the_table_of_contents_is_not_mistaken_for_the_business_section():
    assert predicate_from_business_text("Item 1. Business 1 Item 1A. Risk Factors 9 Item 2. Properties 12") == ""


def test_the_sentences_for_each_email_type():
    d = CompanyDescription(predicate="is a maker of valves", headquarters="Billerica, Massachusetts")
    assert d.annual("Acme Inc.") == "Acme Inc. is a maker of valves"
    assert d.new_company("Acme Inc.") == "Acme Inc., headquartered in Billerica, Massachusetts, is a maker of valves."
    assert CompanyDescription().annual("Acme") is None


def test_business_content_drops_run_together_headings_and_tables():
    from services.business_content import extract

    body = ("Item 1. Business General Acme is a maker of valves for industrial customers around the world. Acme was founded long ago by a family of engineers. Acme has plants in many countries on four continents. Acme sells through distributors and direct channels worldwide. "
            "DESCRIPTION OF OUR REPORTING SEGMENTS INFORMATION ABOUT SEGMENTS We are organized into three reporting segments. "
            "Backlog: 2025 2024 Segment: Engineered Bearings $ 1,421.8 $ 1,341.8 Process Industries $ 400.1 $ 380.2 "
            "Our customers include large distributors and original equipment manufacturers in many end markets. "
            "Operations that sell valves to utilities form our Flow segment. " + "More text about the company and its products. " * 40)
    c = extract("Item 1. Business 1 Item 1A. Risk Factors 9 " + "x " * 40 + body + " Item 1A. Risk Factors " + "y " * 10)
    assert c.segments[0] == "We are organized into three reporting segments."
    assert all("Backlog" not in s and "$ 1,421" not in s for s in c.segments + c.customers + c.overview)
