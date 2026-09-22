"""Workbook-wide circular-reference detection (static formula graph).

CASE A — a proposed HAP write would create a cycle: reject/revert.
CASE B — the source workbook already contains the cycle: flag, do not auto-repair.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from pydantic import BaseModel, Field

from models.write_actions import WriteActionClass
from services.formula_utils import formula_text, is_formula, parse_cell_refs

_MAX_ROW = 200
_MAX_COL = 40


class CircularCycle(BaseModel):
    cells: list[str]
    origin: str = "unknown"  # hap_introduced | pre_existing | proposed
    sheet: str | None = None
    semantic_metric: str | None = None
    destination: str | None = None
    formula: str | None = None
    reason: str = ""


class CircularReferenceReport(BaseModel):
    analysis_id: str
    ticker: str
    hap_introduced: list[CircularCycle] = Field(default_factory=list)
    pre_existing: list[CircularCycle] = Field(default_factory=list)
    template_native: list[CircularCycle] = Field(default_factory=list)
    proposed_rejected: list[CircularCycle] = Field(default_factory=list)
    status: str = "ok"  # ok | BLOCKING_STRUCTURAL_ERROR | PRE_EXISTING_REVIEW
    summary: str = ""


def _cell_key(sheet: str, col: int, row: int) -> str:
    return f"{sheet}!{get_column_letter(col)}{row}"


def _normalize_sheet(name: str | None, default: str) -> str:
    if not name:
        return default
    return name.strip().strip("'")


class CircularReferenceService:
    def scan_workbook(
        self,
        path: Path,
        *,
        analysis_id: str = "",
        ticker: str = "",
        max_row: int = _MAX_ROW,
        max_col: int = _MAX_COL,
    ) -> list[CircularCycle]:
        wb = load_workbook(path, data_only=False)
        try:
            graph = self._graph_from_workbook(wb, max_row=max_row, max_col=max_col)
            return self._cycles_from_graph(graph)
        finally:
            wb.close()

    def scan_open_workbook(self, wb, *, max_row: int = _MAX_ROW, max_col: int = _MAX_COL) -> list[CircularCycle]:
        graph = self._graph_from_workbook(wb, max_row=max_row, max_col=max_col)
        return self._cycles_from_graph(graph)

    def classify_against_source(
        self,
        *,
        analysis_id: str,
        ticker: str,
        current_path: Path,
        source_path: Path | None,
        template_path: Path | None = None,
    ) -> CircularReferenceReport:
        current = self.scan_workbook(current_path, analysis_id=analysis_id, ticker=ticker)
        template_keys: set[tuple[str, ...]] = set()
        previous_keys: set[tuple[str, ...]] = set()
        if template_path is not None and Path(template_path).exists():
            for cycle in self.scan_workbook(template_path, analysis_id=analysis_id, ticker=ticker):
                template_keys.add(tuple(sorted(cycle.cells)))
        if source_path is not None and Path(source_path).exists():
            for cycle in self.scan_workbook(source_path, analysis_id=analysis_id, ticker=ticker):
                previous_keys.add(tuple(sorted(cycle.cells)))
        hap: list[CircularCycle] = []
        preexisting: list[CircularCycle] = []
        template_native: list[CircularCycle] = []
        for cycle in current:
            key = tuple(sorted(cycle.cells))
            if key in template_keys:
                cycle.origin = "template_native"
                template_native.append(cycle)
            elif key in previous_keys:
                cycle.origin = "pre_existing"
                preexisting.append(cycle)
            else:
                cycle.origin = "hap_introduced"
                hap.append(cycle)
        if hap:
            status = "BLOCKING_STRUCTURAL_ERROR"
        elif preexisting:
            status = "PRE_EXISTING_REVIEW"
        else:
            status = "ok"
        return CircularReferenceReport(
            analysis_id=analysis_id,
            ticker=ticker,
            hap_introduced=hap,
            pre_existing=preexisting,
            template_native=template_native,
            status=status,
            summary=(
                f"Circular refs: hap_introduced={len(hap)} pre_existing={len(preexisting)} "
                f"template_native={len(template_native)} status={status}."
            ),
        )

    def write_would_create_cycle(
        self,
        wb,
        *,
        sheet: str,
        cell: str,
        formula: str,
        max_row: int = _MAX_ROW,
        max_col: int = _MAX_COL,
    ) -> CircularCycle | None:
        """Return the cycle that ``formula`` at ``sheet!cell`` would create, if any."""
        graph = self._graph_from_workbook(wb, max_row=max_row, max_col=max_col)
        dest = f"{sheet}!{cell}"
        graph[dest] = self._deps_from_formula(formula, sheet)
        cycles = self._cycles_from_graph(graph)
        for cycle in cycles:
            if dest in cycle.cells:
                cycle.origin = "proposed"
                cycle.destination = dest
                cycle.formula = formula
                cycle.reason = (
                    f"Proposed formula at {dest} creates a circular reference "
                    f"via { ' -> '.join(cycle.cells) }."
                )
                return cycle
        return None

    def _graph_from_workbook(self, wb, *, max_row: int, max_col: int) -> dict[str, set[str]]:
        graph: dict[str, set[str]] = {}
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            rows = min(ws.max_row or 1, max_row)
            cols = min(ws.max_column or 1, max_col)
            for row in range(1, rows + 1):
                for col in range(1, cols + 1):
                    cell = ws.cell(row, col)
                    key = _cell_key(sheet_name, col, row)
                    if not is_formula(cell.value):
                        continue
                    text = formula_text(cell.value) or ""
                    graph[key] = self._deps_from_formula(text, sheet_name)
        return graph

    def _deps_from_formula(self, formula: str, default_sheet: str) -> set[str]:
        deps: set[str] = set()
        for ref in parse_cell_refs(formula):
            sheet = _normalize_sheet(ref["sheet"], default_sheet)
            deps.add(_cell_key(sheet, ref["col"], ref["row"]))
        return deps

    def _cycles_from_graph(self, graph: dict[str, set[str]]) -> list[CircularCycle]:
        WHITE, GRAY, BLACK = 0, 1, 2
        color: dict[str, int] = {}
        parent: dict[str, str | None] = {}
        found: list[CircularCycle] = []
        seen_cycles: set[tuple[str, ...]] = set()

        def dfs(node: str) -> None:
            color[node] = GRAY
            for nxt in graph.get(node, ()):
                if nxt not in color:
                    color[nxt] = WHITE
                    parent[nxt] = None
                if color.get(nxt, WHITE) == WHITE:
                    parent[nxt] = node
                    dfs(nxt)
                elif color.get(nxt) == GRAY:
                    cycle_nodes = [nxt, node]
                    cur = node
                    while cur != nxt and parent.get(cur):
                        cur = parent[cur]  # type: ignore[assignment]
                        cycle_nodes.append(cur)
                    key = tuple(sorted(set(cycle_nodes)))
                    if key not in seen_cycles:
                        seen_cycles.add(key)
                        ordered = list(dict.fromkeys(reversed(cycle_nodes)))
                        found.append(
                            CircularCycle(
                                cells=ordered,
                                origin="unknown",
                                sheet=ordered[0].split("!")[0] if ordered else None,
                                destination=ordered[0] if ordered else None,
                                reason="Circular formula dependency: " + " -> ".join(ordered),
                            )
                        )
            color[node] = BLACK

        for node in list(graph.keys()):
            if color.get(node, WHITE) == WHITE:
                parent[node] = None
                dfs(node)
        return found


def blocking_structural_error(
    *,
    metric: str,
    destination: str,
    formula: str | None,
    cycle: CircularCycle,
) -> dict[str, Any]:
    return {
        "action_class": WriteActionClass.BLOCKING_STRUCTURAL_ERROR.value,
        "semantic_metric": metric,
        "destination": destination,
        "formula": formula,
        "cycle": cycle.cells,
        "reason": cycle.reason or "HAP write would introduce a circular reference.",
    }
