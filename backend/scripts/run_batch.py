"""Daily batch: run several HAP analyses from the HAP work folder and put the finished files in HAP results.

    python scripts/run_batch.py TKR:new_company SXI:new_company WWD:new_company

Files are matched by name in the work folder (default Downloads\\HAP work):
  workbook      "<TICKER> <YEAR> <Q1-Q4 or FY> ... .xlsx"     (new company: the template; updates: newer period = new, older = previous)
  custom filter "custom_run_filter_<date>_<TICKER>.xlsx"       (latest date wins)
  sheet         the newest .xlsx with an S&P tab               (email fields: Classified as, Status with PE10, TBV/P)
Results (flat folder, default Downloads\\HAP results): "<period> <TICKER> FA.xlsx" and "<period> <TICKER> Email.txt / .eml".
The lease-rate review is approved automatically and the run is marked "lease rate auto-approved, please check".
A company with missing or ambiguous files is skipped and reported; the others still run.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

DOWNLOADS = Path.home() / "Downloads"
PERIOD_RE = re.compile(r"^(?P<t>[A-Za-z][A-Za-z.\-]*)[ _-]+(?P<y>\d{4})[ _-]+(?P<p>Q[1-4]|FY)\b", re.I)
CRF_RE = re.compile(r"^custom_run_filter[_ -]+(?P<d>.+?)[_ -]+(?P<t>[A-Za-z][A-Za-z.\-]*)\.xlsx$", re.I)
TYPES = {"new_company", "annual_update", "quarterly_update"}
PERIOD_ORDER = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 5}


@dataclass
class Match:
    workbook: Path | None = None
    previous: Path | None = None
    crf: Path | None = None
    problems: list[str] = field(default_factory=list)


def _period_key(path: Path) -> tuple[int, int] | None:
    m = PERIOD_RE.match(path.stem)
    return (int(m.group("y")), PERIOD_ORDER[m.group("p").upper()]) if m else None


def match_files(folder: Path, ticker: str, analysis_type: str) -> Match:
    t = ticker.upper()
    out = Match()
    books: list[tuple[tuple[int, int], Path]] = []
    crfs: list[Path] = []
    for p in sorted(folder.glob("*.xlsx")):
        if p.name.startswith("~$"):
            continue
        cm = CRF_RE.match(p.name.replace("(", "").replace(")", "")) if p.name.lower().startswith("custom_run_filter") else None
        if cm:
            if cm.group("t").upper() == t:
                crfs.append(p)
            continue
        m = PERIOD_RE.match(p.stem)
        if m and m.group("t").upper() == t:
            books.append((_period_key(p), p))
    if not crfs:
        out.problems.append(f"no custom run filter for {t} (expected custom_run_filter_<date>_{t}.xlsx)")
    else:
        out.crf = crfs[-1]            # names carry the date, so the last sorted is the latest
    books.sort(key=lambda x: x[0])
    if not books:
        out.problems.append(f"no workbook for {t} (expected '{t} <year> <Q#|FY> ...xlsx')")
    elif analysis_type == "new_company":
        if len(books) > 1:
            out.problems.append(f"{len(books)} workbooks for {t}; a new company needs exactly one: " + ", ".join(p.name for _k, p in books))
        else:
            out.workbook = books[0][1]
    else:
        if len(books) < 2:
            out.problems.append(f"an update needs two workbooks for {t} (new and previous period); found {len(books)}")
        else:
            out.workbook, out.previous = books[-1][1], books[-2][1]
    return out


def _copy_upload(src: Path, dest: Path):
    from models.analysis import UploadedFileMetadata
    from models.common import utc_now_iso

    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return UploadedFileMetadata(filename=src.name, stored_filename=dest.name, size_bytes=dest.stat().st_size, uploaded_at=utc_now_iso())


def _period_of(excel: Path, deliv: dict) -> tuple[int | None, int | None]:
    """Year and quarter of the deliverable, read from the Excel name ('2026 Q2 TKR FA.xlsx'); the report carries no quarter for new companies."""
    m = re.match(r"^(\d{4}) (Q[1-3]|FY) ", excel.name)
    if m:
        return int(m.group(1)), (int(m.group(2)[1]) if m.group(2).startswith("Q") else None)
    return deliv.get("fiscal_year"), deliv.get("fiscal_quarter")


def run_one(ticker: str, analysis_type: str, match: Match, sheet, results: Path) -> dict:
    import main as hap_main
    from models.analysis import AnalysisFiles, CreateAnalysisRequest
    from services.deliverable_naming import business_deliverable_name, email_deliverable_name
    from services.business_doc_service import BusinessDocService
    from services.email_draft_service import EmailDraftService

    analysis_service, file_service, output_service = hap_main.analysis_service, hap_main.file_service, hap_main.output_service
    orchestrator = hap_main.pipeline_orchestrator
    company = sheet.company_name(ticker) if sheet else ""
    created = analysis_service.create(CreateAnalysisRequest(company=company or ticker, ticker=ticker, analysis_type=analysis_type))
    analysis_id = created.analysis_id
    upload_dir = file_service.analysis_upload_dir(analysis_id)
    files = AnalysisFiles(
        prefilled_workbook=_copy_upload(match.workbook, upload_dir / "prefilled_workbook.xlsx"),
        custom_run_filter=_copy_upload(match.crf, upload_dir / "custom_run_filter.xlsx"),
        previous_workbook=_copy_upload(match.previous, upload_dir / "previous_workbook.xlsx") if match.previous else None,
    )
    created.files = files
    created.status = "uploaded"
    analysis_service.save(created)

    notes: list[str] = []
    analysis = orchestrator.run(analysis_id)
    if analysis.status == "awaiting_analyst_review":
        review = {}
        try:
            review = output_service.read_json(analysis_id, "lease_rate_review.json")
        except FileNotFoundError:
            pass
        analysis = orchestrator.finalize_new_company_review(
            analysis, action="approve", rate=None, reason="Daily batch: lease rate auto-approved, please check"
        )
        notes.append(f"lease rate auto-approved, please check (proposed rate {review.get('proposed_rate')})")

    summary = {"ticker": ticker, "type": analysis_type, "analysis_id": analysis_id, "status": analysis.status, "notes": notes}
    key = {"new_company": "new_company_deliverables_report.json", "annual_update": "annual_deliverables_report.json",
           "quarterly_update": "quarterly_deliverables_report.json"}[analysis_type]
    try:
        deliv = output_service.read_json(analysis_id, key)
    except FileNotFoundError:
        summary["problem"] = f"no deliverables were produced (status {analysis.status}); see storage/outputs/{analysis_id}"
        return summary

    out_dir = output_service.analysis_output_dir(analysis_id)
    excel = Path(deliv["excel_path"])
    fy, fq = _period_of(excel, deliv)
    projection = None
    if analysis_type == "quarterly_update":
        try:
            from models.quarterly_update import QuarterlyProjectionReport
            from services.quarterly_deliverables_service import QuarterlyDeliverablesService

            projection = QuarterlyDeliverablesService._email_projection(
                QuarterlyProjectionReport.model_validate(output_service.read_json(analysis_id, "quarterly_projection_report.json"))
            )
        except Exception:  # noqa: BLE001 - the projection lines are optional (Q2 and Q3 only)
            projection = None
    # email again with the daily sheet's fields (the pipeline's own draft has no access to the sheet)
    base = email_deliverable_name(fiscal_year=fy or 0, ticker=ticker, fiscal_quarter=fq)
    email = EmailDraftService().produce_safe(
        analysis_type=analysis_type, ticker=ticker, company=company, workbook_path=excel, output_dir=out_dir,
        sheet=sheet.fields(ticker) if sheet else None, base_name=base, fiscal_year=fy, fiscal_quarter=fq, projection=projection,
    )
    results.mkdir(parents=True, exist_ok=True)
    final = {}
    files = [("excel", excel)]
    if email.get("error"):
        notes.append(f"email draft not produced: {email['error']}")
    else:
        files += [("email_txt", Path(email["text_path"])), ("email_eml", Path(email["eml_path"]))]
    if analysis_type == "new_company":
        biz = BusinessDocService().produce_safe(
            ticker=ticker, company=company, workbook_path=excel, output_dir=out_dir,
            base_name=business_deliverable_name(fiscal_year=fy or 0, ticker=ticker, fiscal_quarter=fq),
            search_dir=out_dir, sheet_fields=sheet.fields(ticker) if sheet else None,
        )
        if biz.get("path"):
            files.append(("business_doc", Path(biz["path"])))
        else:
            notes.append(f"business document not produced: {biz.get('error')}")
    for label, src in files:
        dest = results / src.name
        shutil.copy2(src, dest)
        final[label] = str(dest)
    summary.update(final)
    summary["authorized"] = deliv.get("authorized")
    if sheet and not sheet.has(ticker):
        notes.append("ticker not found in the daily sheet: Classified as and Status with PE10 are marked in the email")
    return summary


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("jobs", nargs="+", help="TICKER:analysis_type, for example WWD:new_company")
    ap.add_argument("--work", default=str(DOWNLOADS / "HAP work"))
    ap.add_argument("--results", default=str(DOWNLOADS / "HAP results"))
    ap.add_argument("--sheet-url", default=None, help="published .xlsx link of the Google Sheet (or set HAP_SHEET_URL); falls back to the newest download")
    args = ap.parse_args()
    work, results = Path(args.work), Path(args.results)

    from services.daily_sheet_service import open_daily_sheet

    sheet, source = open_daily_sheet(work, args.sheet_url or os.environ.get("HAP_SHEET_URL"))
    print(f"Daily sheet: {source if sheet else 'NOT FOUND (email fields will be marked)'}")

    report = []
    for job in args.jobs:
        ticker, _, kind = job.partition(":")
        ticker, kind = ticker.strip().upper(), kind.strip().lower()
        if kind not in TYPES:
            report.append({"ticker": ticker, "problem": f"unknown analysis type '{kind}' (use {', '.join(sorted(TYPES))})"})
            continue
        match = match_files(work, ticker, kind)
        if match.problems:
            report.append({"ticker": ticker, "type": kind, "problem": "; ".join(match.problems)})
            print(f"[{ticker}] skipped: {report[-1]['problem']}")
            continue
        print(f"[{ticker}] {kind}: {match.workbook.name} + {match.crf.name}" + (f" (previous {match.previous.name})" if match.previous else ""), flush=True)
        try:
            result = run_one(ticker, kind, match, sheet, results)
        except Exception as exc:  # noqa: BLE001 - one company must not stop the batch
            traceback.print_exc()
            result = {"ticker": ticker, "type": kind, "problem": f"{type(exc).__name__}: {exc}"}
        report.append(result)
        print(f"[{ticker}] {result.get('status', 'FAILED')}: {result.get('problem') or ', '.join(result.get('notes') or ['done'])}", flush=True)

    results.mkdir(parents=True, exist_ok=True)
    from datetime import datetime

    summary_path = results / f"_batch_summary_{datetime.now():%Y-%m-%d_%H%M%S}.json"
    summary_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print("\nSummary written to", summary_path)
    return 0 if all("problem" not in r for r in report) else 1


if __name__ == "__main__":
    raise SystemExit(main())
