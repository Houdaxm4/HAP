"""Refresh Inputs!B63:B75 for quarterly_update.

B63 = live Yahoo (never CRF).
B64:B75 = first-tab CRF A158:B214 matched by label to Inputs!A64:A75.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

from models.quarterly_update import CurrentDataRefreshEntry, CurrentDataRefreshReport
from services.market_price_service import MarketPriceService

_CRF_BLOCK_START = 158
_CRF_BLOCK_END = 214
_INPUTS_START = 63
_INPUTS_END = 75
_PRICE_ROW = 63

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^a-z0-9]+")


def _norm(label: Any) -> str:
    text = _WS_RE.sub(" ", str(label or "").strip().lower())
    return _PUNCT_RE.sub(" ", text).strip()


def _label_match_rank(inputs_label: str, crf_label: str) -> int:
    """Return match quality: 3 exact, 2 CRF-prefix-of-Inputs, 1 PE10-percentile, 0 none."""
    a, b = _norm(inputs_label), _norm(crf_label)
    if not a or not b:
        return 0
    if a == b:
        return 3
    raw_i = str(inputs_label).strip().lower()
    raw_c = str(crf_label).strip().lower()
    # Inputs often adds a parenthetical (e.g. "1st Exit Price (45th Percentile...)")
    if raw_i.startswith(raw_c + " (") or raw_i.startswith(raw_c + "("):
        return 2
    if (
        a.startswith("current pe10")
        and b.startswith("current pe10")
        and "percentile" in a
        and "percentile" in b
    ):
        return 1
    return 0


class CurrentDataRefreshService:
    """Deterministic Inputs current-data refresh from Yahoo + CRF labels."""

    def apply(
        self,
        *,
        analysis_id: str,
        ticker: str,
        workbook_path: Path,
        custom_run_path: Path | None,
        live_price: float | None = None,
        live_price_source: str | None = None,
    ) -> CurrentDataRefreshReport:
        wb = load_workbook(workbook_path)
        entries: list[CurrentDataRefreshEntry] = []
        try:
            if "Inputs" not in wb.sheetnames:
                return CurrentDataRefreshReport(
                    analysis_id=analysis_id,
                    ticker=ticker,
                    summary="Inputs sheet missing; current-data refresh skipped.",
                    missing_required=[f"B{r}" for r in range(_INPUTS_START, _INPUTS_END + 1)],
                )
            inputs = wb["Inputs"]

            # --- B63 live Yahoo ---
            price = live_price
            src = live_price_source
            if price is None:
                price, src = MarketPriceService().get_price(ticker)
            price_label = inputs["A63"].value
            if price is not None:
                inputs["B63"] = float(price)
                entries.append(
                    CurrentDataRefreshEntry(
                        target_cell="B63",
                        target_label=str(price_label) if price_label else "Current Price",
                        source_kind="yahoo_live",
                        source_crf_label=None,
                        source_value=float(price),
                        written_value=float(price),
                        transformation=None,
                        reason=f"Live market price from {src or 'yahoo'}; CRF price not used.",
                    )
                )
            else:
                entries.append(
                    CurrentDataRefreshEntry(
                        target_cell="B63",
                        target_label=str(price_label) if price_label else "Current Price",
                        source_kind="skipped",
                        reason="Live Yahoo price unavailable; left blank (CRF not substituted).",
                    )
                )

            crf_rows = self._load_crf_block(custom_run_path)
            crf_sheet_name = crf_rows[0]["sheet"] if crf_rows else None

            for row in range(64, _INPUTS_END + 1):
                addr = f"B{row}"
                label = inputs[f"A{row}"].value
                label_s = str(label).strip() if label not in (None, "") else ""
                if not label_s:
                    entries.append(
                        CurrentDataRefreshEntry(
                            target_cell=addr,
                            source_kind="skipped",
                            reason="No Inputs label; nothing to map.",
                        )
                    )
                    continue
                match = self._match_crf(label_s, crf_rows)
                if match is None:
                    entries.append(
                        CurrentDataRefreshEntry(
                            target_cell=addr,
                            target_label=label_s,
                            source_kind="skipped",
                            source_crf_sheet=crf_sheet_name,
                            reason=f"No CRF A{_CRF_BLOCK_START}:B{_CRF_BLOCK_END} label match for '{label_s}'.",
                        )
                    )
                    continue
                value = match["value"]
                inputs[addr] = value
                entries.append(
                    CurrentDataRefreshEntry(
                        target_cell=addr,
                        target_label=label_s,
                        source_kind="crf_label",
                        source_crf_sheet=match["sheet"],
                        source_crf_cell=match["cell"],
                        source_crf_label=match["label"],
                        source_value=value,
                        written_value=value,
                        transformation=None,
                        reason=(
                            f"Mapped Inputs!A{row} '{label_s}' to CRF {match['sheet']}!"
                            f"{match['cell']} '{match['label']}'."
                        ),
                    )
                )

            wb.save(workbook_path)
        finally:
            wb.close()

        populated = sum(1 for e in entries if e.written_value is not None)
        missing_required = [e.target_cell for e in entries if e.written_value is None]
        return CurrentDataRefreshReport(
            analysis_id=analysis_id,
            ticker=ticker,
            entries=entries,
            populated_count=populated,
            missing_required=missing_required,
            summary=(
                f"Current-data refresh: {populated}/{len(entries)} cells written "
                f"(B63={'yahoo' if any(e.target_cell=='B63' and e.source_kind=='yahoo_live' for e in entries) else 'missing'})."
            ),
        )

    @staticmethod
    def _load_crf_block(custom_run_path: Path | None) -> list[dict[str, Any]]:
        if custom_run_path is None or not Path(custom_run_path).exists():
            return []
        wb = load_workbook(custom_run_path, data_only=True, read_only=True)
        try:
            sheet = wb[wb.sheetnames[0]]
            sheet_name = wb.sheetnames[0]
            rows: list[dict[str, Any]] = []
            for r in range(_CRF_BLOCK_START, _CRF_BLOCK_END + 1):
                label = sheet.cell(r, 1).value
                value = sheet.cell(r, 2).value
                if label is None or str(label).strip() == "":
                    continue
                rows.append(
                    {
                        "sheet": sheet_name,
                        "cell": f"B{r}",
                        "label": str(label).strip(),
                        "value": value,
                    }
                )
            return rows
        finally:
            wb.close()

    @staticmethod
    def _match_crf(inputs_label: str, crf_rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        ranked: list[tuple[int, dict[str, Any]]] = []
        for row in crf_rows:
            rank = _label_match_rank(inputs_label, row["label"])
            if rank:
                ranked.append((rank, row))
        if not ranked:
            return None
        ranked.sort(key=lambda t: t[0], reverse=True)
        hit = ranked[0][1]
        if hit["value"] is None or hit["value"] == "":
            return None
        return hit
