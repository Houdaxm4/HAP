"""Windows/Excel certification for JBSS Annual Update (C121 + CRF + analysis)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

from openpyxl import load_workbook

from pipeline.orchestrator import PipelineOrchestrator
from services.circular_reference_service import CircularReferenceService
from services.excel_recalc_service import genuine_excel_com_recalc
from services.formula_utils import formula_would_self_reference, is_formula
from services.workbook_flag_service import HAP_ANALYSIS_LABEL, STRUCTURAL_COMMENT, SUGGESTION_COMMENT

ANALYSIS_ID = "be01973a-0765-48ba-b4bf-848211f98a20"


def _json(path: Path):
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def inspect(analysis_id: str) -> dict:
    root = BACKEND / "storage"
    uploads = root / "uploads" / analysis_id
    outputs = root / "outputs" / analysis_id
    prev = uploads / "previous_workbook.xlsx"
    tmpl = uploads / "prefilled_workbook.xlsx"
    completed = outputs / "completed_workbook.xlsx"
    report: dict = {"analysis_id": analysis_id, "completed_workbook": str(completed)}

    circ = CircularReferenceService().classify_against_source(
        analysis_id=analysis_id,
        ticker="JBSS",
        current_path=completed,
        source_path=prev,
        template_path=tmpl,
    )
    report["circular"] = circ.model_dump()
    report["hap_introduced_circular_count"] = len(circ.hap_introduced)
    report["pre_existing_circular_count"] = len(circ.pre_existing)

    wb = load_workbook(completed, data_only=False)
    prev_wb = load_workbook(prev, data_only=False)
    try:
        inp = wb["Inputs"]
        pinp = prev_wb["Inputs"]
        c121 = inp["C121"].value
        d121 = inp["D121"].value
        report["c121"] = {
            "value": c121,
            "self_ref": bool(
                isinstance(c121, str)
                and c121.startswith("=")
                and formula_would_self_reference(c121, 3, 121, sheet="Inputs")
            ),
            "d121": d121,
            "previous_d121": pinp["D121"].value,
            "previous_c121": pinp["C121"].value,
        }
        report["crf_newest"] = {
            "PE10_L57": inp["L57"].value,
            "E10_L58": inp["L58"].value,
            "EPS_10y_growth_L59": inp["L59"].value,
            "EPS_10y_direction_L60": inp["L60"].value,
            "Revenue_10y_growth_L61": inp["L61"].value,
        }
        if "Leases" in wb.sheetnames:
            ls = wb["Leases"]
            report["leases"] = {
                "G18": ls["G18"].value if ls["G18"].value is not None else ls.cell(18, 12).value,
                "row18": [ls.cell(18, c).value for c in range(2, 14)],
                "comment": ls["G18"].comment.text if ls["G18"].comment else None,
            }
        if "R&D" in wb.sheetnames:
            rd = wb["R&D"]
            report["rd"] = {
                "B8_life": rd["B8"].value,
                "B2": rd["B2"].value,
                "C2": rd["C2"].value,
                "D2": rd["D2"].value,
                "E2": rd["E2"].value,
                "B3": rd["B3"].value,
                "B4": rd["B4"].value,
            }
        er_name = "Expected Returns & Buybacks"
        if er_name in wb.sheetnames:
            er = wb[er_name]
            hap_cells = []
            for row in er.iter_rows(min_row=1, max_row=40, min_col=7, max_col=16):
                for cell in row:
                    if cell.value not in (None, ""):
                        hap_cells.append({"cell": cell.coordinate, "value": cell.value})
            report["expected_returns"] = {
                "B5": er["B5"].value,
                "E14": er["E14"].value,
                "D17_D26": [er[f"D{r}"].value for r in range(17, 27)],
                "hap_adjacent": hap_cells[:40],
            }
        if "Enterprise Value" in wb.sheetnames:
            ev = wb["Enterprise Value"]
            hap_cells = []
            for row in ev.iter_rows(min_row=1, max_row=50, min_col=7, max_col=16):
                for cell in row:
                    if cell.value not in (None, ""):
                        hap_cells.append({"cell": cell.coordinate, "value": str(cell.value)[:200]})
            report["enterprise_value"] = {
                "B6": ev["B6"].value,
                "C6": ev["C6"].value,
                "B20": ev["B20"].value,
                "B27": ev["B27"].value,
                "B32": ev["B32"].value,
                "hap_adjacent": hap_cells[:50],
            }
        flagged = []
        for ws in wb.worksheets:
            for row in ws.iter_rows(max_row=min(ws.max_row or 1, 160), max_col=min(ws.max_column or 1, 20)):
                for cell in row:
                    if cell.comment and cell.comment.text:
                        text = cell.comment.text
                        if any(
                            s in text
                            for s in (
                                "DISCREPANCY",
                                STRUCTURAL_COMMENT,
                                SUGGESTION_COMMENT,
                                HAP_ANALYSIS_LABEL,
                            )
                        ):
                            flagged.append(
                                {
                                    "cell": f"{ws.title}!{cell.coordinate}",
                                    "value": cell.value if not is_formula(cell.value) else "(formula)",
                                    "comment": text[:500],
                                }
                            )
        report["flagged_or_hap_commented"] = flagged[:80]
        report["flagged_count"] = len(flagged)
    finally:
        wb.close()
        prev_wb.close()

    gate = _json(outputs / "annual_output_gate_report.json")
    recalc = _json(outputs / "annual_excel_recalc_report.json")
    inputs = _json(outputs / "annual_inputs_report.json")
    leases = _json(outputs / "annual_leases_report.json")
    rd = _json(outputs / "annual_rd_report.json")
    judge = _json(outputs / "annual_analyst_judgment_report.json")
    erj = _json(outputs / "annual_expected_return_judgment_report.json")
    circular_art = _json(outputs / "annual_circular_reference_report.json")
    deliv = _json(outputs / "annual_deliverables_report.json")
    report["artifacts"] = {
        "gate": gate,
        "recalc": recalc,
        "inputs": inputs,
        "leases": leases,
        "rd": rd,
        "judgment": judge,
        "expected_return": erj,
        "circular": circular_art,
        "deliverables": deliv,
    }
    report["excel_com_genuine"] = genuine_excel_com_recalc(
        type("R", (), recalc)() if isinstance(recalc, dict) else None  # placeholder
    ) if False else (
        bool(recalc)
        and recalc.get("status") == "ok"
        and recalc.get("method") == "excel_com_calculate_full_rebuild"
    )
    word_name = (deliv or {}).get("word_filename")
    if word_name and (outputs / word_name).exists():
        from docx import Document

        text = "\n".join(p.text for p in Document(outputs / word_name).paragraphs)
        report["word"] = {
            "filename": word_name,
            "has_original": "ORIGINAL WORKBOOK RESULT" in text,
            "has_hap_adjusted": "HAP-ADJUSTED ANALYSIS" in text,
            "excerpt": text[text.find("8. Analyst Judgment") : text.find("8. Analyst Judgment") + 1800]
            if "8. Analyst Judgment" in text
            else text[:1500],
        }
    out_path = outputs / "annual_windows_certification_report.json"
    out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out_path}")
    return report


def main() -> None:
    print("Running Annual Update pipeline for", ANALYSIS_ID)
    analysis = PipelineOrchestrator().run(ANALYSIS_ID)
    print("pipeline state=", analysis.pipeline.state, "status=", analysis.status)
    report = inspect(ANALYSIS_ID)
    print("hap_introduced_circulars=", report["hap_introduced_circular_count"])
    print("pre_existing_circulars=", report["pre_existing_circular_count"])
    print("c121=", report.get("c121"))
    print("crf=", report.get("crf_newest"))
    print("excel_com=", report.get("excel_com_genuine"))


if __name__ == "__main__":
    main()
