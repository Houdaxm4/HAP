#!/usr/bin/env python3
"""Windows New Company certification driver.

Creates an analysis, runs Mode A then NewCompanyRunner with autonomous
lease-rate and R&D useful-life selection, then continues through genuine
Excel COM CalculateFullRebuild. Optional FastAPI analyst-review overrides
remain available but are not required to complete the run.

Does not mock Excel COM. Does not overwrite the prior IDCC production
certification at commit da1765b.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from models.analysis import AnalysisFiles, CreateAnalysisRequest, UploadedFileMetadata  # noqa: E402
from models.common import utc_now_iso  # noqa: E402


def _copy_upload(src: Path, dest: Path) -> UploadedFileMetadata:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return UploadedFileMetadata(
        filename=src.name,
        stored_filename=dest.name,
        size_bytes=dest.stat().st_size,
        uploaded_at=utc_now_iso(),
    )


def _resolve_lease_action(args, proposed: float | None) -> tuple[str, float | None, str | None] | None:
    cli = (args.lease_action or os.environ.get("HAP_NC_LEASE_ACTION") or "").strip()
    if cli:
        upper = cli.upper()
        reason = args.reason or os.environ.get("HAP_NC_LEASE_REASON") or (
            "Windows certification operator approval via FastAPI /analyst-review/lease-rate"
        )
        if upper in {"APPROVE", "APPROVED"}:
            return "approve", None, reason
        if upper in {"MORE", "REQUEST_MORE_EVIDENCE"}:
            return "request_more_evidence", None, reason
        if upper in {"CORRECT", "CORRECTION"}:
            raw_rate = args.lease_rate if args.lease_rate is not None else os.environ.get("HAP_NC_LEASE_RATE")
            if raw_rate is None:
                raise SystemExit("--lease-action correct requires --lease-rate")
            rate = float(raw_rate)
            if rate <= 0 or rate >= 1:
                raise SystemExit("Corrected rate must be a decimal such as 0.045")
            return "correct", rate, reason
        raise SystemExit(f"Unrecognized --lease-action {cli!r}")
    if args.no_prompt or not sys.stdin.isatty():
        return None
    return _prompt_lease(proposed)


def _prompt_lease(proposed: float | None) -> tuple[str, float | None, str | None]:
    print()
    print("=== MANUAL LEASE-RATE REVIEW REQUIRED ===")
    print(f"Proposed long-term lease discount rate: {proposed}")
    print("Type APPROVE to accept the proposed rate.")
    print("Type a decimal (example 0.05) to correct the rate.")
    print("Type MORE to request more evidence (run remains blocked).")
    raw = input("Lease-rate action> ").strip()
    if not raw:
        raise SystemExit("No lease-rate action entered.")
    upper = raw.upper()
    if upper == "APPROVE":
        return "approve", None, "Windows certification manual approval"
    if upper == "MORE":
        return "request_more_evidence", None, "Windows certification requested more evidence"
    try:
        rate = float(raw)
    except ValueError as exc:
        raise SystemExit(f"Unrecognized lease-rate action: {raw!r}") from exc
    if rate <= 0 or rate >= 1:
        raise SystemExit("Corrected rate must be a decimal such as 0.045")
    return "correct", rate, "Windows certification manual correction"


def _safe_json(output_service, analysis_id: str, name: str) -> dict:
    try:
        return output_service.read_json(analysis_id, name)
    except FileNotFoundError:
        return {}


def _print_report(analysis_id: str, analysis, output_service, extra: dict) -> dict:
    out_dir = output_service.analysis_output_dir(analysis_id)
    cert = _safe_json(output_service, analysis_id, "new_company_certification_status.json")
    gate = _safe_json(output_service, analysis_id, "new_company_output_gate_report.json")
    val = _safe_json(output_service, analysis_id, "new_company_valuation_report.json")
    lease = _safe_json(output_service, analysis_id, "lease_rate_review.json")
    recalc = _safe_json(output_service, analysis_id, "new_company_excel_recalc_report.json")
    circ = _safe_json(output_service, analysis_id, "new_company_circular_reference_report.json")
    artifacts = sorted(p.name for p in out_dir.iterdir() if p.is_file()) if out_dir.exists() else []
    payload = {
        **extra,
        "analysis_id": analysis_id,
        "status": analysis.status,
        "pipeline_state": analysis.pipeline.state,
        "certification_status": cert.get("certification_status"),
        "workflow_state": cert.get("workflow_state"),
        "selected_lease_rate": lease.get("selected_rate"),
        "lease_classification": lease.get("classification"),
        "lease_decision_class": lease.get("decision_class"),
        "lease_rate_approved": cert.get("lease_rate_approved"),
        "proposed_lease_rate": lease.get("proposed_rate"),
        "approved_lease_rate": lease.get("approved_rate"),
        "lease_action": lease.get("analyst_action"),
        "com_invoked": cert.get("com_invoked") or recalc.get("com_invoked"),
        "recalc_status": cert.get("recalc_status") or recalc.get("status"),
        "recalc_method": cert.get("recalc_method") or recalc.get("method"),
        "gates": gate.get("gates"),
        "blockers": gate.get("blockers"),
        "warnings": gate.get("warnings"),
        "report_authorized": gate.get("report_authorized"),
        "valuation_judgment": {
            "status": val.get("status"),
            "er_decision": val.get("er_decision"),
            "oe_decision": val.get("oe_decision"),
            "graham_decision": val.get("graham_decision"),
            "normalized_base_decision": val.get("normalized_base_decision"),
            "original_assumptions_preserved": val.get("original_assumptions_preserved"),
            "hap_introduced_circular_count": val.get("hap_introduced_circular_count"),
            "period_context": val.get("period_context"),
        },
        "circular_status": circ.get("status"),
        "artifact_dir": str(out_dir),
        "artifact_paths": [str(out_dir / name) for name in artifacts],
    }
    print()
    print("=== NEW COMPANY CERTIFICATION RESULT ===")
    print(json.dumps(payload, indent=2, default=str))
    return payload


def _preflight_excel() -> str:
    try:
        import pythoncom  # type: ignore
        import win32com.client as win32  # type: ignore
    except ImportError as exc:
        raise SystemExit(f"pywin32/win32com is required: {exc}") from exc
    pythoncom.CoInitialize()
    excel = None
    try:
        excel = win32.DispatchEx("Excel.Application")
        excel.Visible = False
        excel.DisplayAlerts = False
        version = str(getattr(excel, "Version", "unknown"))
        excel.Quit()
        excel = None
        return version
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Microsoft Excel COM is not available: {exc}") from exc
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass


def _write_frozen_markdown(path: Path, payload: dict, gates: dict[str, dict]) -> None:
    lines = [
        "# New Company Autonomous-Decision Certification",
        "",
        f"Recommendation: **{payload.get('recommendation', 'NOT_READY_FOR_PRODUCTION')}**",
        "",
        f"Generated at: {payload.get('generated_at')}",
        f"Analysis id: `{payload.get('analysis_id')}`",
        f"Ticker: {payload.get('ticker')}",
        f"Workbook: `{payload.get('workbook')}`",
        f"CRF: `{payload.get('crf')}`",
        "",
        "## Acceptance gates",
        "",
        "| Gate | Result | Evidence |",
        "| --- | --- | --- |",
    ]
    for name, row in gates.items():
        lines.append(f"| {name} | **{row.get('result')}** | {row.get('evidence', '')} |")
    lines += [
        "",
        "## Lease-rate autonomous decision",
        "",
        f"- Selected rate: `{payload.get('selected_lease_rate') or payload.get('proposed_lease_rate')}`",
        f"- Classification: `{payload.get('lease_classification')}`",
        f"- Decision class: `{payload.get('lease_decision_class')}`",
        f"- Analyst action: `{payload.get('lease_action')}`",
        f"- Review path: `{payload.get('lease_approval_path', 'not_required')}`",
        f"- Prior certified baseline: `da1765badfd339dfdc3deb2ffc92968ff0012268`",
        "",
        "## Excel COM recalculation",
        "",
        f"- com_invoked: `{payload.get('com_invoked')}`",
        f"- status: `{payload.get('recalc_status')}`",
        f"- method: `{payload.get('recalc_method')}`",
        f"- Excel version: `{payload.get('excel_version')}`",
        "",
        "## Valuation judgment",
        "",
        json.dumps(payload.get("valuation_judgment") or {}, indent=2, default=str),
        "",
        "## Output-gate blockers / warnings",
        "",
        f"- blockers: `{payload.get('blockers')}`",
        f"- warnings: `{payload.get('warnings')}`",
        f"- authorized: `{payload.get('report_authorized')}`",
        "",
        "## Artifact directory",
        "",
        f"`{payload.get('artifact_dir')}`",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run New Company Windows Excel COM certification.")
    parser.add_argument("--ticker", default="", help="Ticker (or HAP_NC_TICKER)")
    parser.add_argument("--company", default="", help="Company name (or HAP_NC_COMPANY)")
    parser.add_argument("--workbook", default="", help="Prefilled Industrial Template .xlsx")
    parser.add_argument("--crf", default="", help="Bloomberg Custom_Run_Filter .xlsx")
    parser.add_argument("--branch", default="", help="Git branch being certified")
    parser.add_argument("--commit", default="", help="Git commit being certified")
    parser.add_argument(
        "--lease-action",
        default="",
        help="Optional override only: approve | correct | request_more_evidence. Default is autonomous (no prompt).",
    )
    parser.add_argument("--lease-rate", type=float, default=None, help="Required when --lease-action correct")
    parser.add_argument("--reason", default="", help="Analyst reason recorded on an optional override")
    parser.add_argument(
        "--no-prompt",
        action="store_true",
        help="Do not prompt if the run unexpectedly pauses for more evidence.",
    )
    args = parser.parse_args()

    generated_at = datetime.now(timezone.utc).isoformat()
    extra = {
        "git_branch": args.branch or os.environ.get("HAP_NC_BRANCH"),
        "git_commit": args.commit or os.environ.get("HAP_NC_COMMIT"),
        "generated_at": generated_at,
    }

    if os.name != "nt":
        print("Windows certification must run on Windows with Excel.", file=sys.stderr)
        extra["recommendation"] = "NOT_READY_FOR_PRODUCTION"
        extra["blocked_reason"] = "not Windows"
        return 2

    excel_version = _preflight_excel()
    extra["excel_version"] = excel_version

    ticker = (args.ticker or os.environ.get("HAP_NC_TICKER") or "").strip().upper()
    company = (args.company or os.environ.get("HAP_NC_COMPANY") or ticker).strip()
    workbook = Path(args.workbook or os.environ.get("HAP_NC_WORKBOOK") or "")
    crf = Path(args.crf or os.environ.get("HAP_NC_CRF") or "")
    extra["ticker"] = ticker
    extra["workbook"] = str(workbook)
    extra["crf"] = str(crf)
    if not ticker:
        print("Set HAP_NC_TICKER or pass --ticker.", file=sys.stderr)
        return 2
    if not workbook.is_file() or not crf.is_file():
        print(
            "Set HAP_NC_WORKBOOK and HAP_NC_CRF to existing .xlsx files "
            "(Industrial Template + Custom_Run_Filter).",
            file=sys.stderr,
        )
        return 2

    from fastapi.testclient import TestClient

    import main as hap_main

    analysis_service = hap_main.analysis_service
    file_service = hap_main.file_service
    output_service = hap_main.output_service
    orchestrator = hap_main.pipeline_orchestrator
    client = TestClient(hap_main.app)

    created = analysis_service.create(
        CreateAnalysisRequest(company=company or ticker, ticker=ticker, analysis_type="new_company")
    )
    analysis_id = created.analysis_id
    extra["analysis_id"] = analysis_id
    upload_dir = file_service.analysis_upload_dir(analysis_id)
    wb_meta = _copy_upload(workbook, upload_dir / "prefilled_workbook.xlsx")
    crf_meta = _copy_upload(crf, upload_dir / "custom_run_filter.xlsx")
    created.files = AnalysisFiles(prefilled_workbook=wb_meta, custom_run_filter=crf_meta)
    created.status = "uploaded"
    analysis_service.save(created)

    print(f"Created analysis {analysis_id} for {ticker}. Running New Company pipeline (Mode A)...")
    analysis = orchestrator.run(analysis_id)
    print(f"After first pass: status={analysis.status}")

    try:
        rd = output_service.read_json(analysis_id, "rd_useful_life_decision.json")
    except FileNotFoundError:
        rd = {}
    print()
    print("=== R&D USEFUL LIFE (AGENT-SELECTED ANALYST ASSUMPTION) ===")
    print(f"Selected life: {rd.get('selected_useful_life')}")
    print(f"Warning: {rd.get('warning')}")
    print(f"Rationale: {rd.get('rationale')}")

    lease_approval_path = "not_required"
    if analysis.status == "awaiting_analyst_review":
        review = _safe_json(output_service, analysis_id, "lease_rate_review.json")
        extra["proposed_lease_rate"] = review.get("proposed_rate")
        resolved = _resolve_lease_action(args, review.get("proposed_rate"))
        if resolved is None:
            extra["lease_approval_path"] = "BLOCKED — no analyst lease-rate action (non-interactive, no --lease-action)"
            payload = _print_report(analysis_id, analysis, output_service, extra)
            payload["recommendation"] = "NOT_READY_FOR_PRODUCTION"
            payload["lease_approval_path"] = extra["lease_approval_path"]
            _emit_frozen(output_service, analysis_id, payload)
            print("Lease-rate approval BLOCKED. Not simulating approval.", file=sys.stderr)
            return 3
        action, rate, reason = resolved
        body: dict = {"action": action, "reason": reason}
        if rate is not None:
            body["rate"] = rate
        response = client.post(f"/analysis/{analysis_id}/analyst-review/lease-rate", json=body)
        lease_approval_path = f"POST /analysis/{analysis_id}/analyst-review/lease-rate action={action}"
        extra["lease_approval_path"] = lease_approval_path
        if response.status_code >= 400:
            print(response.text, file=sys.stderr)
            payload = _print_report(analysis_id, analysis_service.get(analysis_id), output_service, extra)
            payload["recommendation"] = "NOT_READY_FOR_PRODUCTION"
            _emit_frozen(output_service, analysis_id, payload)
            return 1
        analysis = analysis_service.get(analysis_id)

    extra["lease_approval_path"] = lease_approval_path
    payload = _print_report(analysis_id, analysis, output_service, extra)
    cert = _safe_json(output_service, analysis_id, "new_company_certification_status.json")
    complete = (
        analysis.status == "complete"
        and cert.get("certification_status") == "COMPLETE"
        and cert.get("com_invoked")
    )
    payload["recommendation"] = "READY_FOR_PRODUCTION" if complete else "NOT_READY_FOR_PRODUCTION"
    _emit_frozen(output_service, analysis_id, payload)
    if complete:
        return 0
    print("New Company is not COMPLETE. Excel COM certification did not finish.", file=sys.stderr)
    return 1


def _emit_frozen(output_service, analysis_id: str, payload: dict) -> None:
    out_dir = output_service.analysis_output_dir(analysis_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    gate = _safe_json(output_service, analysis_id, "new_company_output_gate_report.json")
    lease = _safe_json(output_service, analysis_id, "lease_rate_review.json")
    recalc = _safe_json(output_service, analysis_id, "new_company_excel_recalc_report.json")
    val = _safe_json(output_service, analysis_id, "new_company_valuation_report.json")
    circ = _safe_json(output_service, analysis_id, "new_company_circular_reference_report.json")
    deliv = _safe_json(output_service, analysis_id, "new_company_deliverables_report.json")
    payload.setdefault("proposed_lease_rate", lease.get("proposed_rate"))
    payload.setdefault("approved_lease_rate", lease.get("approved_rate"))
    payload.setdefault("lease_action", lease.get("analyst_action"))
    payload.setdefault("com_invoked", recalc.get("com_invoked"))
    payload.setdefault("recalc_status", recalc.get("status"))
    payload.setdefault("recalc_method", recalc.get("method"))
    gate_rows = {
        "Mode A + NewCompanyRunner first pass": {
            "result": "PASS" if payload.get("analysis_id") else "FAIL",
            "evidence": str(out_dir / "new_company_run_state.json"),
        },
        "Ten-year validation": {
            "result": "PASS" if (out_dir / "ten_year_source_coverage.json").exists() else "FAIL",
            "evidence": str(out_dir / "ten_year_source_coverage.json"),
        },
        "Lease-rate proposal": {
            "result": "PASS" if lease.get("proposed_rate") is not None else "BLOCKED",
            "evidence": str(out_dir / "lease_rate_review.json"),
        },
        "Autonomous lease-rate decision": {
            "result": (
                "PASS"
                if lease.get("blocking") is False
                and (lease.get("selected_rate") is not None or lease.get("proposed_rate") is not None)
                and lease.get("decision_class") != "EVIDENCE_INSUFFICIENT"
                else "BLOCKED"
            ),
            "evidence": payload.get("lease_approval_path") or str(out_dir / "lease_rate_review.json"),
        },
        "Genuine Excel COM CalculateFullRebuild": {
            "result": "PASS" if recalc.get("com_invoked") and recalc.get("status") == "ok" else (
                "BLOCKED" if not recalc else "FAIL"
            ),
            "evidence": str(out_dir / "new_company_excel_recalc_report.json"),
        },
        "Valuation judgment (ER/EV/OE/Graham)": {
            "result": (
                "PASS"
                if val.get("original_assumptions_preserved") and val.get("status") in {"ok", "PRE_EXISTING_REVIEW"}
                else ("BLOCKED" if not val else "FAIL")
            ),
            "evidence": str(out_dir / "new_company_valuation_report.json"),
        },
        "No HAP-introduced circular references": {
            "result": (
                "PASS"
                if circ and circ.get("hap_introduced") == []
                else ("BLOCKED" if not circ else "FAIL")
            ),
            "evidence": str(out_dir / "new_company_circular_reference_report.json"),
        },
        "Gates A–L + report authorization": {
            "result": "PASS" if gate.get("report_authorized") else (
                "BLOCKED" if not gate else "FAIL"
            ),
            "evidence": str(out_dir / "new_company_output_gate_report.json"),
        },
        "Authorized Word analysis": {
            "result": "PASS" if deliv.get("authorized") and deliv.get("word_path") else (
                "BLOCKED" if not deliv else "FAIL"
            ),
            "evidence": deliv.get("word_path") or str(out_dir / "new_company_deliverables_report.json"),
        },
    }
    (out_dir / "new_company_windows_certification_manifest.json").write_text(
        json.dumps({"payload": payload, "gates": gate_rows}, indent=2, default=str),
        encoding="utf-8",
    )
    _write_frozen_markdown(out_dir / "NEW_COMPANY_AUTONOMOUS_DECISION_CERTIFICATION.md", payload, gate_rows)
    lnn_copy = out_dir / "NEW_COMPANY_HARDENING_CERTIFICATION.md"
    shutil.copy2(out_dir / "NEW_COMPANY_AUTONOMOUS_DECISION_CERTIFICATION.md", lnn_copy)
    repo_copy = BACKEND_ROOT / "NEW_COMPANY_HARDENING_CERTIFICATION.md"
    shutil.copy2(lnn_copy, repo_copy)


if __name__ == "__main__":
    raise SystemExit(main())
