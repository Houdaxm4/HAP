#!/usr/bin/env python3
"""Windows New Company certification driver.

Creates an analysis, runs the pipeline until the lease-rate pause, accepts
approval through the real FastAPI analyst-review endpoint, then continues
through genuine Excel COM CalculateFullRebuild, save+reopen, validation,
and Word generation only when authorized.

Does not mock Excel COM. Does not substitute LibreOffice or Python formula values.
Does not pull or merge main.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
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


def _print_report(analysis_id: str, analysis, output_service, extra: dict) -> None:
    out_dir = output_service.analysis_output_dir(analysis_id)
    cert = {}
    gate = {}
    try:
        cert = output_service.read_json(analysis_id, "new_company_certification_status.json")
    except FileNotFoundError:
        cert = {}
    try:
        gate = output_service.read_json(analysis_id, "new_company_output_gate_report.json")
    except FileNotFoundError:
        gate = {}
    artifacts = sorted(p.name for p in out_dir.iterdir() if p.is_file()) if out_dir.exists() else []
    payload = {
        **extra,
        "analysis_id": analysis_id,
        "status": analysis.status,
        "pipeline_state": analysis.pipeline.state,
        "certification_status": cert.get("certification_status"),
        "workflow_state": cert.get("workflow_state"),
        "lease_rate_approved": cert.get("lease_rate_approved"),
        "com_invoked": cert.get("com_invoked"),
        "recalc_status": cert.get("recalc_status"),
        "recalc_method": cert.get("recalc_method"),
        "blockers": gate.get("blockers"),
        "warnings": gate.get("warnings"),
        "report_authorized": gate.get("report_authorized"),
        "artifact_dir": str(out_dir),
        "artifact_paths": [str(out_dir / name) for name in artifacts],
    }
    print()
    print("=== NEW COMPANY CERTIFICATION RESULT ===")
    print(json.dumps(payload, indent=2))


def _preflight_excel() -> None:
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
        excel.Quit()
        excel = None
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"Microsoft Excel COM is not available: {exc}") from exc
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Run New Company Windows Excel COM certification.")
    parser.add_argument("--ticker", default="", help="Ticker (or HAP_NC_TICKER)")
    parser.add_argument("--company", default="", help="Company name (or HAP_NC_COMPANY)")
    parser.add_argument("--workbook", default="", help="Prefilled Industrial Template .xlsx")
    parser.add_argument("--crf", default="", help="Bloomberg Custom_Run_Filter .xlsx")
    parser.add_argument("--branch", default="", help="Git branch being certified")
    parser.add_argument("--commit", default="", help="Git commit being certified")
    args = parser.parse_args()

    if os.name != "nt":
        print("Windows certification must run on Windows with Excel.", file=sys.stderr)
        return 2

    _preflight_excel()

    ticker = (args.ticker or os.environ.get("HAP_NC_TICKER") or "").strip().upper()
    company = (args.company or os.environ.get("HAP_NC_COMPANY") or ticker).strip()
    workbook = Path(args.workbook or os.environ.get("HAP_NC_WORKBOOK") or "")
    crf = Path(args.crf or os.environ.get("HAP_NC_CRF") or "")
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
    upload_dir = file_service.analysis_upload_dir(analysis_id)
    wb_meta = _copy_upload(workbook, upload_dir / "prefilled_workbook.xlsx")
    crf_meta = _copy_upload(crf, upload_dir / "custom_run_filter.xlsx")
    created.files = AnalysisFiles(prefilled_workbook=wb_meta, custom_run_filter=crf_meta)
    created.status = "uploaded"
    analysis_service.save(created)

    extra = {
        "git_branch": args.branch or os.environ.get("HAP_NC_BRANCH"),
        "git_commit": args.commit or os.environ.get("HAP_NC_COMMIT"),
        "ticker": ticker,
    }
    print(f"Created analysis {analysis_id} for {ticker}. Running New Company pipeline...")
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

    if analysis.status == "awaiting_analyst_review":
        review = {}
        try:
            review = output_service.read_json(analysis_id, "lease_rate_review.json")
        except FileNotFoundError:
            review = {}
        action, rate, reason = _prompt_lease(review.get("proposed_rate"))
        body: dict = {"action": action, "reason": reason}
        if rate is not None:
            body["rate"] = rate
        response = client.post(f"/analysis/{analysis_id}/analyst-review/lease-rate", json=body)
        if response.status_code >= 400:
            print(response.text, file=sys.stderr)
            _print_report(analysis_id, analysis_service.get(analysis_id), output_service, extra)
            return 1
        analysis = analysis_service.get(analysis_id)

    _print_report(analysis_id, analysis, output_service, extra)
    if analysis.status == "complete":
        cert = {}
        try:
            cert = output_service.read_json(analysis_id, "new_company_certification_status.json")
        except FileNotFoundError:
            cert = {}
        if cert.get("certification_status") == "COMPLETE" and cert.get("com_invoked"):
            return 0
        print("Pipeline status is complete but genuine Excel COM certification was not recorded.", file=sys.stderr)
        return 1
    print("New Company is not COMPLETE. Excel COM certification did not finish.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
