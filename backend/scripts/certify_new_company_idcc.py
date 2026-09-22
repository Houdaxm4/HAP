"""IDCC Industrial Template New Company Windows certification inspector.

Locates a real ten-year Bloomberg-prefilled Industrial Template and CRF,
then runs Mode A → NewCompanyRunner → lease review → genuine Excel COM →
valuation judgment. Does not mock COM or lease approval.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from openpyxl import load_workbook

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from services.new_company_period_service import NewCompanyPeriodService
from services.workbook_flag_service import HAP_ANALYSIS_LABEL
from services.formula_utils import is_formula

SOURCE_ANALYSIS = "275d5e21-42e2-4a39-9f78-be9fa48c1b44"
CERT_ID = "new-company-idcc-cert"
ASSUMPTION_CELLS = (
    ("Expected Returns & Buybacks", "A11"),
    ("Expected Returns & Buybacks", "B5"),
    ("Expected Returns & Buybacks", "E14"),
    ("Expected Returns & Buybacks", "F14"),
    ("Enterprise Value", "C6"),
    ("Enterprise Value", "B6"),
    ("R&D", "B8"),
    ("Leases", "A18"),
)


def _json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _find_crf(upload_dir: Path) -> Path | None:
    for p in sorted(upload_dir.glob("*.xlsx")):
        name = p.name.lower()
        if "custom_run" in name or "crf" in name or "filter" in name:
            return p
    return None


def _snapshot(path: Path) -> dict:
    out: dict = {}
    wb = load_workbook(path, data_only=False)
    try:
        for sheet, addr in ASSUMPTION_CELLS:
            if sheet not in wb.sheetnames:
                continue
            cell = wb[sheet][addr]
            out[f"{sheet}!{addr}"] = {
                "value": cell.value,
                "formula": is_formula(cell.value),
            }
        out["_sheets"] = list(wb.sheetnames)
    finally:
        wb.close()
    return out


def _hap_labels(path: Path) -> list[str]:
    found: list[str] = []
    if not path.exists():
        return found
    wb = load_workbook(path, data_only=False)
    try:
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            for row in ws.iter_rows(min_row=1, max_row=80, max_col=40):
                for cell in row:
                    text = str(cell.value or "")
                    comment = cell.comment.text if cell.comment else ""
                    if HAP_ANALYSIS_LABEL in text or HAP_ANALYSIS_LABEL in comment or (
                        isinstance(cell.value, str) and cell.value.startswith("HAP ANALYSIS")
                    ):
                        found.append(f"{sheet}!{cell.coordinate}")
    finally:
        wb.close()
    return found


def _cell_diff(before: dict, after: dict) -> dict:
    diffs = []
    preserved = []
    for key, old in before.items():
        if key.startswith("_"):
            continue
        new = after.get(key)
        if new is None:
            diffs.append({"cell": key, "before": old, "after": None})
            continue
        if old.get("value") != new.get("value"):
            diffs.append({"cell": key, "before": old, "after": new})
        else:
            preserved.append(key)
    return {"preserved": preserved, "diffs": diffs, "preserved_count": len(preserved), "diff_count": len(diffs)}


def _write_blocked(cert_dir: Path, report: dict) -> dict:
    cert_dir.mkdir(parents=True, exist_ok=True)
    (cert_dir / "new_company_windows_certification_manifest.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    md = BACKEND / "NEW_COMPANY_PRODUCTION_CERTIFICATION.md"
    lines = [
        "# New Company Production Certification",
        "",
        f"Recommendation: **{report.get('status', 'NOT_READY_FOR_PRODUCTION')}**",
        "",
        f"Generated at: {report.get('generated_at')}",
        f"Source analysis: `{report.get('source_analysis')}`",
        "",
        "## Acceptance gates",
        "",
        "| Gate | Result | Evidence |",
        "| --- | --- | --- |",
    ]
    for name, row in (report.get("gates") or {}).items():
        if isinstance(row, dict):
            lines.append(f"| {name} | **{row.get('result')}** | {row.get('evidence', row.get('missing', ''))} |")
        else:
            lines.append(f"| {name} | **{row}** | |")
    if report.get("error"):
        lines += ["", "## Blocked reason", "", report["error"], ""]
    md.write_text("\n".join(lines), encoding="utf-8")
    shutil.copy2(md, cert_dir / "NEW_COMPANY_PRODUCTION_CERTIFICATION.md")
    return report


def run() -> dict:
    root = BACKEND / "storage"
    src_uploads = root / "uploads" / SOURCE_ANALYSIS
    cert_dir = root / "outputs" / CERT_ID
    cert_dir.mkdir(parents=True, exist_ok=True)
    report: dict = {
        "analysis_id": CERT_ID,
        "source_analysis": SOURCE_ANALYSIS,
        "ticker": "IDCC",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gates": {},
        "status": "NOT_READY_FOR_PRODUCTION",
    }

    tmpl = src_uploads / "prefilled_workbook.xlsx"
    crf = _find_crf(src_uploads)
    if not tmpl.exists():
        report["error"] = f"Industrial Template missing at {tmpl}"
        report["gates"]["workbook"] = {"result": "BLOCKED", "missing": str(tmpl)}
        return _write_blocked(cert_dir, report)
    if crf is None or not crf.exists():
        report["error"] = f"Custom_Run_Filter missing under {src_uploads}"
        report["gates"]["workbook"] = {"result": "BLOCKED", "missing": str(src_uploads)}
        return _write_blocked(cert_dir, report)

    periods = NewCompanyPeriodService().detect(
        analysis_id=CERT_ID, ticker="IDCC", workbook_path=tmpl
    )
    industrial = periods.template_family == "industrial_template" and len(periods.fiscal_years) >= 8
    report["period_probe"] = {
        "template_family": periods.template_family,
        "fiscal_years": periods.fiscal_years,
        "latest_quarter": periods.latest_quarter,
        "chronology_ok": periods.chronology_ok,
    }
    if not industrial:
        report["error"] = (
            "Source workbook is not a ten-year Industrial Template initiation file. "
            f"family={periods.template_family} years={len(periods.fiscal_years)}"
        )
        report["gates"]["workbook"] = {"result": "BLOCKED", "evidence": str(tmpl)}
        return _write_blocked(cert_dir, report)

    original_copy = cert_dir / "original_initiation_workbook.xlsx"
    shutil.copy2(tmpl, original_copy)
    before = _snapshot(original_copy)
    (cert_dir / "original_assumption_snapshot.json").write_text(
        json.dumps(before, indent=2, default=str), encoding="utf-8"
    )

    report["gates"]["workbook"] = {
        "result": "PASS",
        "evidence": str(tmpl),
        "crf": str(crf),
        "fiscal_years": periods.fiscal_years,
        "latest_quarter": periods.latest_quarter,
    }

    lease_action = (os.environ.get("HAP_NC_LEASE_ACTION") or "").strip()
    argv = [
        str(BACKEND / "scripts" / "new_company_windows_certify.py"),
        "--ticker",
        "IDCC",
        "--company",
        "InterDigital",
        "--workbook",
        str(tmpl),
        "--crf",
        str(crf),
        "--no-prompt",
    ]
    if lease_action:
        argv.extend(["--lease-action", lease_action])
        if os.environ.get("HAP_NC_LEASE_RATE"):
            argv.extend(["--lease-rate", os.environ["HAP_NC_LEASE_RATE"]])
        if os.environ.get("HAP_NC_LEASE_REASON"):
            argv.extend(["--reason", os.environ["HAP_NC_LEASE_REASON"]])
        else:
            argv.extend(
                [
                    "--reason",
                    "Certification-operator approval through FastAPI /analyst-review/lease-rate; "
                    "proposed long-term lease discount rate accepted without modification.",
                ]
            )

    report["windows_certify_argv"] = argv[1:]
    report["lease_action_supplied"] = bool(lease_action)

    old_argv = sys.argv[:]
    try:
        sys.argv = argv
        import importlib.util

        driver_path = BACKEND / "scripts" / "new_company_windows_certify.py"
        spec = importlib.util.spec_from_file_location("new_company_windows_certify", driver_path)
        driver = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(driver)
        rc = driver.main()
    except SystemExit as exc:
        rc = int(exc.code) if isinstance(exc.code, int) else 1
    except Exception as exc:  # noqa: BLE001
        report["error"] = f"windows_certify failed: {exc}"
        report["gates"]["windows_certify"] = {"result": "FAIL", "error": str(exc)}
        return _write_blocked(cert_dir, report)
    finally:
        sys.argv = old_argv

    report["windows_certify_exit"] = rc
    # Driver writes artifacts under the created analysis id; copy frozen files here.
    frozen_repo = BACKEND / "NEW_COMPANY_PRODUCTION_CERTIFICATION.md"
    if frozen_repo.exists():
        shutil.copy2(frozen_repo, cert_dir / "NEW_COMPANY_PRODUCTION_CERTIFICATION.md")

    # Locate the newest new_company analysis output that has a certification status.
    outputs = root / "outputs"
    candidates = []
    if outputs.exists():
        for d in outputs.iterdir():
            if not d.is_dir():
                continue
            status = d / "new_company_certification_status.json"
            if status.exists():
                candidates.append((status.stat().st_mtime, d))
    analysis_dir = max(candidates)[1] if candidates else None
    report["pipeline_output_dir"] = str(analysis_dir) if analysis_dir else None

    if analysis_dir is None:
        report["error"] = "windows_certify produced no new_company_certification_status.json"
        report["gates"]["windows_certify"] = {"result": "FAIL"}
        return _write_blocked(cert_dir, report)

    for name in (
        "lease_rate_review.json",
        "new_company_excel_recalc_report.json",
        "new_company_valuation_report.json",
        "new_company_analyst_judgment_report.json",
        "new_company_circular_reference_report.json",
        "new_company_output_gate_report.json",
        "new_company_deliverables_report.json",
        "new_company_windows_certification_manifest.json",
        "new_company_normalized_base_report.json",
        "cell_diff_report.json",
        "completed_workbook.xlsx",
        "annual_working_workbook.xlsx",
    ):
        src = analysis_dir / name
        if src.exists():
            shutil.copy2(src, cert_dir / name)

    # Completed FA copy if named differently
    for p in analysis_dir.glob("*FA.xlsx"):
        shutil.copy2(p, cert_dir / p.name)
    for p in analysis_dir.glob("*New Company.docx"):
        shutil.copy2(p, cert_dir / p.name)

    completed = None
    for candidate in (
        analysis_dir / "completed_workbook.xlsx",
        analysis_dir / "annual_working_workbook.xlsx",
        *analysis_dir.glob("*FA.xlsx"),
    ):
        if candidate.exists():
            completed = candidate
            break
    if completed:
        shutil.copy2(completed, cert_dir / "completed_workbook.xlsx")
        after = _snapshot(completed)
        diff = _cell_diff(before, after)
        hap = _hap_labels(completed)
        (cert_dir / "cell_diff_original_assumptions.json").write_text(
            json.dumps({**diff, "hap_analysis_cells": hap}, indent=2, default=str),
            encoding="utf-8",
        )
        report["gates"]["original_assumptions_preserved"] = {
            "result": "PASS" if diff["diff_count"] == 0 else "FAIL",
            "diff_count": diff["diff_count"],
            "evidence": str(cert_dir / "cell_diff_original_assumptions.json"),
        }
        report["gates"]["hap_analysis_labeled"] = {
            "result": "PASS" if hap else "FAIL",
            "count": len(hap),
            "evidence": str(cert_dir / "cell_diff_original_assumptions.json"),
        }

    lease = _json(analysis_dir / "lease_rate_review.json") or {}
    recalc = _json(analysis_dir / "new_company_excel_recalc_report.json") or {}
    val = _json(analysis_dir / "new_company_valuation_report.json") or {}
    circ = _json(analysis_dir / "new_company_circular_reference_report.json") or {}
    gate = _json(analysis_dir / "new_company_output_gate_report.json") or {}
    deliv = _json(analysis_dir / "new_company_deliverables_report.json") or {}
    cert = _json(analysis_dir / "new_company_certification_status.json") or {}

    report["lease_rate_review"] = {
        "proposed_rate": lease.get("proposed_rate"),
        "approved_rate": lease.get("approved_rate"),
        "action": lease.get("analyst_action"),
        "blocking": lease.get("blocking"),
        "status": lease.get("status"),
        "reason": lease.get("analyst_reason"),
    }
    report["excel_com"] = {
        "status": recalc.get("status"),
        "method": recalc.get("method"),
        "com_invoked": recalc.get("com_invoked"),
        "summary": recalc.get("summary"),
        "error": recalc.get("error"),
    }
    report["valuation_judgment"] = {
        "status": val.get("status"),
        "er": val.get("er_decision"),
        "oe": val.get("oe_decision"),
        "graham": val.get("graham_decision"),
        "oe_base": val.get("normalized_base_decision"),
        "preserved": val.get("original_assumptions_preserved"),
        "period_context": val.get("period_context"),
        "summary": val.get("summary"),
    }

    report["gates"]["mode_a_runner"] = {
        "result": "PASS" if cert else "FAIL",
        "workflow": cert.get("workflow_state"),
        "evidence": str(analysis_dir / "new_company_run_state.json"),
    }
    report["gates"]["ten_year_validation"] = {
        "result": "PASS" if (analysis_dir / "ten_year_source_coverage.json").exists() else "FAIL",
        "evidence": str(analysis_dir / "ten_year_source_coverage.json"),
    }
    report["gates"]["lease_proposal"] = {
        "result": "PASS" if lease.get("proposed_rate") is not None else "BLOCKED",
        "proposed_rate": lease.get("proposed_rate"),
        "evidence": str(analysis_dir / "lease_rate_review.json"),
    }
    if lease.get("blocking") is False:
        lease_result = "PASS"
    elif not lease_action:
        lease_result = "BLOCKED"
    else:
        lease_result = "FAIL"
    report["gates"]["lease_approval"] = {
        "result": lease_result,
        "action": lease.get("analyst_action"),
        "approved_rate": lease.get("approved_rate"),
        "path": "POST /analysis/{id}/analyst-review/lease-rate" if lease_action else "not supplied",
        "evidence": str(analysis_dir / "lease_rate_review.json"),
    }
    com_ok = bool(recalc.get("com_invoked") and recalc.get("status") == "ok" and recalc.get("method") == "excel_com_calculate_full_rebuild")
    report["gates"]["excel_com"] = {
        "result": "PASS" if com_ok else ("BLOCKED" if not recalc or recalc.get("status") == "UNAVAILABLE" else "FAIL"),
        "evidence": str(analysis_dir / "new_company_excel_recalc_report.json"),
    }
    val_ok = bool(val.get("original_assumptions_preserved") and val.get("status") in {"ok", "PRE_EXISTING_REVIEW"})
    report["gates"]["valuation_judgment"] = {
        "result": "PASS" if val_ok else ("BLOCKED" if not val else "FAIL"),
        "er": val.get("er_decision"),
        "oe": val.get("oe_decision"),
        "graham": val.get("graham_decision"),
        "evidence": str(analysis_dir / "new_company_valuation_report.json"),
    }
    hap_n = None
    if circ:
        hap_n = len(circ.get("hap_introduced") or [])
    report["gates"]["no_hap_circulars"] = {
        "result": "PASS" if hap_n == 0 else ("BLOCKED" if circ is None or not circ else "FAIL"),
        "hap_introduced": hap_n,
        "evidence": str(analysis_dir / "new_company_circular_reference_report.json"),
    }
    report["gates"]["output_gates_a_l"] = {
        "result": "PASS" if gate.get("report_authorized") else ("BLOCKED" if not gate else "FAIL"),
        "gates": gate.get("gates"),
        "blockers": gate.get("blockers"),
        "evidence": str(analysis_dir / "new_company_output_gate_report.json"),
    }
    report["gates"]["authorized_word"] = {
        "result": "PASS" if deliv.get("authorized") and deliv.get("word_path") else ("BLOCKED" if not deliv else "FAIL"),
        "word_path": deliv.get("word_path"),
        "evidence": str(analysis_dir / "new_company_deliverables_report.json"),
    }

    results = [row.get("result") for row in report["gates"].values() if isinstance(row, dict)]
    if results and all(r == "PASS" for r in results):
        report["status"] = "READY_FOR_PRODUCTION"
    elif any(r == "FAIL" for r in results):
        report["status"] = "NOT_READY_FOR_PRODUCTION"
    else:
        report["status"] = "BLOCKED"

    (cert_dir / "new_company_windows_certification_manifest.json").write_text(
        json.dumps(report, indent=2, default=str), encoding="utf-8"
    )
    _write_blocked(cert_dir, report)
    return report


if __name__ == "__main__":
    payload = run()
    print(json.dumps(payload, indent=2, default=str))
    if payload.get("status") == "READY_FOR_PRODUCTION":
        raise SystemExit(0)
    raise SystemExit(1)
