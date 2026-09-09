"""Transparent analyst judgment for Expected Return, Owner Earnings, and Graham EPS growth."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.annual_update import (
    AnnualAnalystJudgmentReport,
    AnnualExpectedReturnReport,
    JudgmentRecord,
)

_BV_DEFAULT = "BOOK_VALUE_GROWTH"
_EPS_ALT = "EPS_GROWTH"


def _num(v: Any) -> float | None:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    return None


def _unrealistic_growth(g: float | None) -> bool:
    if g is None:
        return False
    return g > 0.25 or g < -0.05


def _is_formula(val: Any) -> bool:
    return isinstance(val, str) and val.startswith("=")


class AnnualJudgmentService:
    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        context: dict[str, Any] | None = None,
    ) -> tuple[AnnualExpectedReturnReport, AnnualAnalystJudgmentReport]:
        ctx = context or {}
        bv = _num(ctx.get("book_value_growth"))
        er = _num(ctx.get("expected_return"))
        oe = _num(ctx.get("owner_earnings_growth"))
        eps = _num(ctx.get("eps_growth"))
        qualitative = [str(x) for x in ctx.get("evidence") or []]
        bv_class = str(ctx.get("bv_classification") or "UNKNOWN")
        eps_class = str(ctx.get("eps_classification") or "UNKNOWN")
        oe_class = str(ctx.get("oe_classification") or "UNKNOWN")

        er_method = _BV_DEFAULT
        er_selected_g = bv
        er_reason = "Default book-value growth methodology retained; historical BV growth is economically reasonable."
        er_flag = bv_class.lower() if bv_class != "UNKNOWN" else "reasonable"
        er_change = "ACCEPTED"
        if _unrealistic_growth(bv) or bv_class in {
            "AGGRESSIVE",
            "VERY_AGGRESSIVE",
            "DISTORTED",
        }:
            er_flag = "DISTORTED" if bv_class == "DISTORTED" else "AGGRESSIVE"
            if ctx.get("prefer_eps") or (
                eps is not None
                and not _unrealistic_growth(eps)
                and eps_class == "REASONABLE"
            ):
                er_method = _EPS_ALT
                er_selected_g = eps
                er_change = "METHODOLOGY_SWITCH"
                er_reason = (
                    "Historical BV growth is economically distorted; switched to workbook "
                    "EPS-growth methodology as more representative."
                )
            else:
                er_selected_g = _num(ctx.get("normalized_bv_growth")) or 0.08
                er_change = "NORMALIZED"
                er_reason = (
                    "Historical BV growth is not a realistic forward assumption; "
                    f"normalized to {er_selected_g:.1%}."
                )
        elif bv_class == "CONSERVATIVE":
            er_flag = "CONSERVATIVE"

        hist_evidence = {
            "bv_growth": bv,
            "eps_growth_10y": eps,
            "eps_growth_5y": ctx.get("eps_growth_5y"),
            "oe_growth": oe,
            "oe_growth_3y": ctx.get("owner_earnings_3y"),
            "oe_growth_5y": ctx.get("owner_earnings_5y"),
            "oe_growth_10y": ctx.get("owner_earnings_10y"),
        }

        er_report = AnnualExpectedReturnReport(
            analysis_id=analysis_id,
            ticker=ticker,
            default_methodology=_BV_DEFAULT,
            original_growth_rate=bv,
            original_expected_return=er,
            reasonableness=er_flag,
            selected_methodology=er_method,
            selected_growth_rate=er_selected_g if isinstance(er_selected_g, (int, float)) else _num(er_selected_g),
            final_expected_return=er if er_change == "ACCEPTED" else None,
            growth_3y=ctx.get("owner_earnings_3y"),
            growth_5y=ctx.get("eps_growth_5y") or ctx.get("owner_earnings_5y"),
            growth_10y=eps,
            alternative_windows={
                "bv": bv,
                "eps_10y": eps,
                "eps_5y": ctx.get("eps_growth_5y"),
                "oe_3y": ctx.get("owner_earnings_3y"),
                "oe_5y": ctx.get("owner_earnings_5y"),
                "oe_10y": ctx.get("owner_earnings_10y"),
            },
            distortions=[e for e in qualitative if "diverge" in e.lower() or "distort" in e.lower()],
            evidence=qualitative,
            rationale=er_reason,
            confidence=0.75 if er_change == "ACCEPTED" else 0.65,
            summary=er_reason,
        )

        oe_adj = _unrealistic_growth(oe) or oe_class in {
            "AGGRESSIVE",
            "VERY_AGGRESSIVE",
            "DISTORTED",
        }
        oe_sel = _num(ctx.get("normalized_oe_growth")) if oe_adj else oe
        oe_change = "NORMALIZED" if oe_adj else "ACCEPTED"
        oe_reason = (
            f"Owner Earnings 20-year model preserved; growth {oe_class.lower()} "
            + (f"→ normalized to {oe_sel:.1%}." if oe_adj and oe_sel is not None else "retained as sustainable.")
        )

        eps_adj = _unrealistic_growth(eps) or bool(ctx.get("eps_distorted")) or eps_class in {
            "AGGRESSIVE",
            "VERY_AGGRESSIVE",
            "DISTORTED",
        }
        eps_sel = _num(ctx.get("normalized_eps_growth")) if eps_adj else eps
        eps_change = "NORMALIZED" if eps_adj else "ACCEPTED"
        eps_reason = (
            "Graham formula unchanged; EPS growth "
            + (
                f"normalized from {eps:.1%} to {eps_sel:.1%} due to sustainability concerns."
                if eps_adj and eps is not None and eps_sel is not None
                else "retained as historically reasonable."
            )
        )

        self._write_assumptions(
            workbook_path,
            er_selected_g,
            oe_sel if oe_adj else None,
            eps_sel if eps_adj else None,
            ctx.get("assumption_cells") or {},
        )

        judgment = AnnualAnalystJudgmentReport(
            analysis_id=analysis_id,
            ticker=ticker,
            lease_rate=ctx.get("lease_judgment"),
            expected_return=JudgmentRecord(
                metric="expected_return_growth",
                original_value=bv,
                selected_value=er_selected_g,
                original_methodology=_BV_DEFAULT,
                selected_methodology=er_method,
                reasonableness_classification=er_flag,
                historical_evidence=hist_evidence,
                qualitative_evidence=qualitative,
                evidence=qualitative,
                rationale=er_reason,
                workbook_impact="Expected Return growth assumption",
                model_impact="Expected Return terminal value trajectory",
                change_type=er_change,
                source_references=["workbook", "sec_eps_history"],
                confidence=0.75 if er_change == "ACCEPTED" else 0.65,
                adjusted=er_change != "ACCEPTED",
            ),
            owner_earnings_growth=JudgmentRecord(
                metric="owner_earnings_growth",
                original_value=oe,
                selected_value=oe_sel if oe_adj else oe,
                original_methodology="historical_oe_growth",
                selected_methodology="normalized_oe_growth" if oe_adj else "historical_oe_growth",
                reasonableness_classification=oe_class,
                historical_evidence={
                    "oe_3y": ctx.get("owner_earnings_3y"),
                    "oe_5y": ctx.get("owner_earnings_5y"),
                    "oe_10y": ctx.get("owner_earnings_10y"),
                },
                qualitative_evidence=qualitative,
                evidence=qualitative,
                rationale=oe_reason,
                workbook_impact="Enterprise Value Owner Earnings extrapolation growth",
                model_impact="20-year Owner Earnings DCF trajectory",
                change_type=oe_change,
                source_references=["inputs_owner_earnings_series"],
                confidence=0.7,
                adjusted=oe_adj,
            ),
            graham_eps_growth=JudgmentRecord(
                metric="graham_eps_growth",
                original_value=eps,
                selected_value=eps_sel if eps_adj else eps,
                original_methodology="historical_eps_cagr",
                selected_methodology="normalized_eps_growth" if eps_adj else "historical_eps_cagr",
                reasonableness_classification=eps_class,
                historical_evidence={
                    "eps_10y": eps,
                    "eps_5y": ctx.get("eps_growth_5y"),
                },
                qualitative_evidence=qualitative,
                evidence=qualitative,
                rationale=eps_reason,
                workbook_impact="Graham entry price EPS growth input",
                model_impact="Graham intrinsic value and entry price",
                change_type=eps_change,
                source_references=["final_metrics_eps_cagr"],
                confidence=0.7,
                adjusted=eps_adj,
            ),
            summary="Analyst judgments documented; formulas calculate from reviewed assumptions.",
        )
        return er_report, judgment

    def _write_assumptions(
        self,
        path: Path,
        er_g: Any,
        oe_g: Any,
        eps_g: Any,
        cells: dict[str, str],
    ) -> None:
        """Write only to discovered non-formula assumption cells — never valuation outputs."""
        wb = load_workbook(path, data_only=False)
        try:
            if er_g is not None:
                addr = cells.get("er_growth")
                if addr:
                    sheet, cell = addr.split("!")
                    ws = wb[sheet]
                    if not _is_formula(ws[cell].value):
                        ws[cell].value = float(er_g)
                elif "Expected Returns & Buybacks" in wb.sheetnames:
                    ws = wb["Expected Returns & Buybacks"]
                    if not _is_formula(ws["B12"].value):
                        label = str(ws["A12"].value or "").lower()
                        if "growth" in label or ws["A12"].value is None:
                            ws["B12"].value = float(er_g)

            if oe_g is not None:
                for key in ("oe_growth_c", "oe_growth_b"):
                    addr = cells.get(key)
                    if not addr:
                        continue
                    sheet, cell = addr.split("!")
                    ws = wb[sheet]
                    if not _is_formula(ws[cell].value):
                        ws[cell].value = float(oe_g)
                        break

            if eps_g is not None:
                addr = cells.get("graham_eps")
                if addr:
                    sheet, cell = addr.split("!")
                    ws = wb[sheet]
                    if not _is_formula(ws[cell].value):
                        ws[cell].value = float(eps_g)

            wb.save(path)
        finally:
            wb.close()
