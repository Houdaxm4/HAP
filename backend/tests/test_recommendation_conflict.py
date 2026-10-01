from services.recommendation_conflict import recommendation_conflict


def test_conflict_flagged_with_final_as_headline():
    r = recommendation_conflict({"final_recommendation": "HOLD"}, {"recommendation": {"recommendation": "WATCH"}})
    assert r["conflict"] and r["headline"] == "HOLD" and r["headline_source"] == "final_recommendation_report"


def test_agreement_and_missing():
    assert not recommendation_conflict({"final_recommendation": "buy"}, {"recommendation": {"recommendation": "BUY"}})["conflict"]
    r = recommendation_conflict(None, {"recommendation": {"recommendation": "WATCH"}})
    assert not r["conflict"] and r["headline"] == "WATCH"
