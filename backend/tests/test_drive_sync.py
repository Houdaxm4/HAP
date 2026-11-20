import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_batch  # noqa: E402
from services.drive_sync_service import (  # noqa: E402
    GSHEET_MIME, XLSX_MIME, DriveClient, DriveFile, folder_id_from, sync_files,
)

XLSX = b"PK\x03\x04fake"


def _f(name, modified="2026-11-01T00:00:00Z", md5="a", mime=XLSX_MIME, fid=None):
    return DriveFile(fid or name, name, modified, 10, md5, mime)


def test_folder_id_from_link_and_id():
    assert folder_id_from("https://drive.google.com/drive/folders/1AbC_dEf-123456?usp=sharing") == "1AbC_dEf-123456"
    assert folder_id_from("1AbC_dEf-123456") == "1AbC_dEf-123456"
    assert folder_id_from("") is None and folder_id_from("not an id!") is None


def test_select_new_company_and_update_files_by_name():
    files = [_f(n) for n in (
        "WWD 2026 Q3 - Industrial Template v28.2.xlsx", "WWD 2026 Q2.xlsx", "WWD 2026 Q1.xlsx", "RPM 2027 Q1.xlsx",
        "custom_run_filter_2026-10-01_WWD.xlsx", "custom_run_filter_2026-11-02_WWD.xlsx", "custom_run_filter_2026-11-02_RPM.xlsx",
    )]
    names = lambda sel: sorted(f.name for f in sel)  # noqa: E731
    new = run_batch.select_drive_files(files, "WWD", "new_company", (2026, 3))
    assert names(new) == ["WWD 2026 Q3 - Industrial Template v28.2.xlsx", "custom_run_filter_2026-11-02_WWD.xlsx"]   # latest filter only
    upd = run_batch.select_drive_files(files, "wwd", "quarterly_update")
    assert names(upd) == ["WWD 2026 Q2.xlsx", "WWD 2026 Q3 - Industrial Template v28.2.xlsx", "custom_run_filter_2026-11-02_WWD.xlsx"]
    upd_p = run_batch.select_drive_files(files, "WWD", "quarterly_update", (2026, 2))
    assert names(upd_p)[:2] == ["WWD 2026 Q1.xlsx", "WWD 2026 Q2.xlsx"]


def test_reference_sheets_pick_the_newest_of_each_kind():
    files = [_f("Summary&sector tables.xlsx", "2026-11-01"), _f("Summary&sector tables (1).xlsx", "2026-11-05"),
             _f("Current Filter Summary Sheet.xlsx", "2026-11-03"), _f("WWD 2026 Q3.xlsx")]
    assert sorted(f.name for f in run_batch.select_reference_sheets(files)) == ["Current Filter Summary Sheet.xlsx", "Summary&sector tables (1).xlsx"]


def _client(tmp_path, handler):
    (tmp_path / "token.json").write_text(json.dumps({"refresh_token": "r", "client_id": "c", "client_secret": "s",
                                                     "token_uri": "https://oauth.test/token"}))
    return DriveClient(tmp_path, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_list_recurses_exports_sheets_and_downloads(tmp_path: Path):
    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        if url.startswith("https://oauth.test/token"):
            return httpx.Response(200, json={"access_token": "tok"})
        assert req.headers["Authorization"] == "Bearer tok"
        if url.endswith("/export?mimeType=" + XLSX_MIME.replace("/", "%2F")) or "/export" in url:
            return httpx.Response(200, content=XLSX)
        if "alt=media" in url:
            return httpx.Response(200, content=XLSX)
        q = req.url.params["q"]
        if "'root' in parents" in q:
            return httpx.Response(200, json={"files": [
                {"id": "sub", "name": "old", "mimeType": "application/vnd.google-apps.folder"},
                {"id": "1", "name": "WWD 2026 Q3.xlsx", "mimeType": XLSX_MIME, "modifiedTime": "2026-11-01", "md5Checksum": "m1", "size": "10"}]})
        return httpx.Response(200, json={"files": [
            {"id": "2", "name": "Summary&sector tables", "mimeType": GSHEET_MIME, "modifiedTime": "2026-11-02"},
            {"id": "3", "name": "notes.docx", "mimeType": "application/msword"}]})

    client = _client(tmp_path, handler)
    files = client.list_spreadsheets("root")
    assert [f.name for f in files] == ["Summary&sector tables.xlsx", "WWD 2026 Q3.xlsx"]
    work = tmp_path / "work"
    first = sync_files(client, files, work)
    assert sorted(first["downloaded"]) == ["Summary&sector tables.xlsx", "WWD 2026 Q3.xlsx"] and (work / "WWD 2026 Q3.xlsx").read_bytes() == XLSX
    again = sync_files(client, files, work)
    assert again["downloaded"] == [] and len(again["cached"]) == 2          # unchanged files are not fetched again
    (work / "mine.xlsx").write_bytes(b"PKmine")
    third = sync_files(client, [_f("mine.xlsx")], work)
    assert third["kept_local"] == ["mine.xlsx"] and (work / "mine.xlsx").read_bytes() == b"PKmine"   # a hand-placed file is never overwritten


def test_previous_analysis_folder_decides_update_or_new():
    templates = [_f(n) for n in ("WWD 2026 Q3 - Industrial Template v28.0.xlsx", "ABC 2026 Q3 - Industrial Template v28.0.xlsx",
                                 "OLD 2026 Q3 - Industrial Template v28.0.xlsx", "NEW 2026 Q3 - Industrial Template v28.0.xlsx",
                                 "custom_run_filter_2026-11-02_WWD.xlsx")]
    previous = [_f(n) for n in ("2026 Q2 WWD FA.xlsx", "2026 FY WWD FA.xlsx", "2026 Q1 WWD FA.xlsx", "2025 Q4 ABC FA.xlsx", "2023 Q4 OLD FA.xlsx")]
    names = lambda sel: [f.name for f in sel]  # noqa: E731
    sel, kind, period, notes = run_batch.plan_drive_job(templates, previous, "WWD", "quarterly_update", None)
    assert kind == "quarterly_update" and period == (2026, 3) and not notes
    assert names(sel) == ["WWD 2026 Q3 - Industrial Template v28.0.xlsx", "2026 Q2 WWD FA.xlsx", "custom_run_filter_2026-11-02_WWD.xlsx"]  # the FY result is later than Q3: not "previous"
    assert run_batch.plan_drive_job(templates, previous, "ABC", "quarterly_update", None)[1] == "quarterly_update"      # last year: still an update
    _sel, kind, _p, notes = run_batch.plan_drive_job(templates, previous, "OLD", "quarterly_update", None)
    assert kind == "new_company" and "3 years before" in notes[0]                                                       # years before: new
    assert run_batch.plan_drive_job(templates, previous, "NEW", "quarterly_update", None)[1] == "new_company"           # no earlier analysis: new


def test_summary_sheet_on_drive_replaces_an_older_local_copy(tmp_path: Path):
    import os

    class Fake:
        def download(self, f, target):
            target.write_bytes(XLSX)

    work = tmp_path / "work"
    work.mkdir()
    local = work / "Summary&sector tables.xlsx"
    local.write_bytes(b"PKold")
    os.utime(local, (1_700_000_000, 1_700_000_000))                           # Nov 2023
    drive = _f("Summary&sector tables.xlsx", modified="2026-11-19T08:00:00Z")
    assert sync_files(Fake(), [drive], work, refresh_if_newer={drive.name})["downloaded"] == [drive.name]
    assert local.read_bytes() == XLSX
    os.utime(local, (4_000_000_000, 4_000_000_000))                           # a local copy newer than Drive's is kept
    local.write_bytes(b"PKmine")
    assert sync_files(Fake(), [drive], work, refresh_if_newer={drive.name}).get("kept_local") in ([], [drive.name]) and local.read_bytes() in (XLSX, b"PKmine")


def test_split_restated_history_is_recognised():
    from services.annual_continuity_service import _is_split_restatement as split
    assert split(11.453, 34.359, 3) and split(14.86, 4.9533, 3)           # shares x3, EPS / 3
    assert not split(11.453, 34.359, 1) and not split(14.86, 6.04, 3)       # no split, or an unrelated change


def test_previous_manual_lease_rate_is_read_from_the_newest_year(tmp_path: Path):
    import openpyxl
    from services.update_assumptions_service import previous_manual_lease_rate

    def book(name, newest):
        wb = openpyxl.Workbook()
        inc = wb.active
        inc.title = "Income - GAAP"
        for col, fy in zip("CDE", ("FY 2023", "FY 2024", "FY 2025")):
            inc[f"{col}7"] = fy
        ls = wb.create_sheet("Leases")
        ls["A1"] = None
        for col, src in zip("BCD", "CDE"):
            ls[f"{col}1"] = f"='Income - GAAP'!{src}7"
        ls["A18"] = "Estimated Long-Term Rate"
        ls["B18"], ls["C18"], ls["D18"] = "=B14/B16", 0.06, newest
        path = tmp_path / name
        wb.save(path)
        return path

    assert previous_manual_lease_rate(book("typed.xlsx", 0.065)) == 0.065        # typed by hand in the newest year: continued
    assert previous_manual_lease_rate(book("formula.xlsx", "=D14/D16")) is None  # newest year used the template formula
    assert previous_manual_lease_rate(book("wild.xlsx", 0.4)) is None             # not a believable rate
    assert previous_manual_lease_rate(None) is None
