"""Retention: keep the latest run per (company, type); protect referenced and running runs; plan before delete."""

import json
from pathlib import Path

from retention.service import RetentionService


def make(root: Path, aid, ticker, kind, status, created):
    (root / "analyses").mkdir(parents=True, exist_ok=True)
    (root / "analyses" / f"{aid}.json").write_text(json.dumps({
        "analysis_id": aid, "ticker": ticker, "analysis_type": kind, "status": status, "created_at": created, "updated_at": created}))
    for folder in ("outputs", "uploads"):
        d = root / folder / aid
        d.mkdir(parents=True)
        (d / "data.bin").write_bytes(b"x" * 1000)


def ids(items):
    return sorted(i["id"] for i in items)


def test_keeps_latest_complete_run_per_company_and_type(tmp_path):
    make(tmp_path, "aaaaaaaa-0000-0000-0000-000000000001", "IDCC", "new_company", "complete", "2026-09-01")
    make(tmp_path, "aaaaaaaa-0000-0000-0000-000000000002", "IDCC", "new_company", "complete", "2026-09-10")
    make(tmp_path, "aaaaaaaa-0000-0000-0000-000000000003", "IDCC", "new_company", "failed", "2026-09-20")   # newer but failed
    make(tmp_path, "bbbbbbbb-0000-0000-0000-000000000001", "IDCC", "quarterly_update", "complete", "2026-09-05")  # other type
    plan = RetentionService(tmp_path).plan()
    assert ids(plan.keep) == ["aaaaaaaa-0000-0000-0000-000000000002", "bbbbbbbb-0000-0000-0000-000000000001"]
    assert ids(plan.delete) == ["aaaaaaaa-0000-0000-0000-000000000001", "aaaaaaaa-0000-0000-0000-000000000003"]
    assert plan.bytes_freed == 4000  # outputs + uploads of two runs


def test_without_a_complete_run_the_latest_run_is_kept(tmp_path):
    make(tmp_path, "cccccccc-0000-0000-0000-000000000001", "AAA", "annual_update", "failed", "2026-09-01")
    make(tmp_path, "cccccccc-0000-0000-0000-000000000002", "AAA", "annual_update", "needs_review", "2026-09-02")
    plan = RetentionService(tmp_path).plan()
    assert ids(plan.keep) == ["cccccccc-0000-0000-0000-000000000002"] and ids(plan.delete) == ["cccccccc-0000-0000-0000-000000000001"]


def test_running_certified_regression_and_listed_runs_are_protected(tmp_path):
    make(tmp_path, "dddddddd-0000-0000-0000-000000000001", "LNN", "new_company", "processing", "2026-09-01")
    make(tmp_path, "dddddddd-0000-0000-0000-000000000002", "LNN", "new_company", "complete", "2026-09-02")   # certified
    make(tmp_path, "dddddddd-0000-0000-0000-000000000003", "LNN", "new_company", "complete", "2026-09-03")   # regression source
    make(tmp_path, "dddddddd-0000-0000-0000-000000000004", "LNN", "new_company", "complete", "2026-09-04")   # listed in retention_keep.json
    make(tmp_path, "dddddddd-0000-0000-0000-000000000005", "LNN", "new_company", "complete", "2026-09-05")   # latest
    (tmp_path / "certifications" / "new-company-lnn-dddddddd").mkdir(parents=True)   # 8-hex prefix in a certification name
    # regression case pointing at a full id
    cases = tmp_path / "cases" / "lnn"
    cases.mkdir(parents=True)
    (cases / "case.json").write_text(json.dumps({"source_analysis_id": "dddddddd-0000-0000-0000-000000000003"}))
    (tmp_path / "retention_keep.json").write_text(json.dumps(["dddddddd-0000-0000-0000-000000000004"]))
    plan = RetentionService(tmp_path).plan(regression_dir=tmp_path / "cases")
    assert ids(plan.keep) == ["dddddddd-0000-0000-0000-000000000005"]
    assert ids(plan.delete) == []  # all four older runs are protected (the prefix protects every run that shares it)
    reasons = {p["id"][-1]: p["reason"] for p in plan.protected}
    assert reasons["1"] == "still running" and len(plan.protected) == 4


def test_apply_deletes_exactly_the_plan_and_nothing_else(tmp_path):
    make(tmp_path, "eeeeeeee-0000-0000-0000-000000000001", "ZZ", "annual_update", "complete", "2026-09-01")
    make(tmp_path, "eeeeeeee-0000-0000-0000-000000000002", "ZZ", "annual_update", "complete", "2026-09-02")
    service = RetentionService(tmp_path)
    plan = service.plan()
    assert (tmp_path / "outputs" / "eeeeeeee-0000-0000-0000-000000000001").exists()  # planning deletes nothing
    removed = service.apply(plan)
    assert removed == ["eeeeeeee-0000-0000-0000-000000000001"]
    assert not (tmp_path / "outputs" / removed[0]).exists() and not (tmp_path / "uploads" / removed[0]).exists()
    assert not (tmp_path / "analyses" / f"{removed[0]}.json").exists()
    assert (tmp_path / "outputs" / "eeeeeeee-0000-0000-0000-000000000002").exists()
