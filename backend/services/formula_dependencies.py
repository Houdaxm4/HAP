"""Which workbook cells feed the metrics we report? Read-only analysis of the workbook's own formulas.

A blank input cell is "important" only if some formula cell on a metric sheet depends on it (directly or through
other formulas). This replaces hand-kept lists of required lines and works for any template.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any

from openpyxl.formula import Tokenizer
from openpyxl.utils.cell import range_boundaries

# Sheets whose formulas are the reported metrics (ratios, ROIC, valuation, expected return).
METRIC_SHEETS = ("Final Metrics", "Expected Returns & Buybacks", "Enterprise Value", "IC & NOPAT & ROIC")
MAX_RANGE_CELLS = 4000  # ignore absurd ranges (whole columns) instead of exploding the graph

Cell = tuple[str, int, int]  # (sheet, row, col)
_SHEET_RE = re.compile(r"^(?:'((?:[^']|'')+)'|([^'!]+))!(.+)$")


def _split(ref: str, current_sheet: str) -> tuple[str, str]:
    match = _SHEET_RE.match(ref)
    if match:
        return (match.group(1) or match.group(2)).replace("''", "'"), match.group(3)
    return current_sheet, ref


def _cells_of(sheet: str, address: str) -> list[Cell]:
    address = address.replace("$", "")
    try:
        min_col, min_row, max_col, max_row = range_boundaries(address)
    except (ValueError, TypeError):
        return []
    if None in (min_col, min_row, max_col, max_row):
        return []
    if (max_col - min_col + 1) * (max_row - min_row + 1) > MAX_RANGE_CELLS:
        return []
    return [(sheet, r, c) for r in range(min_row, max_row + 1) for c in range(min_col, max_col + 1)]


def precedents(workbook) -> dict[Cell, set[Cell]]:
    """formula cell -> cells it reads. ``workbook`` must be loaded with data_only=False."""
    graph: dict[Cell, set[Cell]] = {}
    for ws in workbook.worksheets:
        for (row, col), cell in ws._cells.items():
            value = cell.value
            if not (isinstance(value, str) and value.startswith("=")):
                continue
            reads: set[Cell] = set()
            try:
                tokens = Tokenizer(value).items
            except Exception:  # noqa: BLE001 - an unparsable formula contributes no edges
                continue
            for token in tokens:
                if token.type == "OPERAND" and token.subtype == "RANGE":
                    sheet, address = _split(token.value, ws.title)
                    reads.update(_cells_of(sheet, address))
            graph[(ws.title, row, col)] = reads
    return graph


class MetricDependencies:
    """All cells that the metric sheets depend on, computed once per workbook."""

    def __init__(self, workbook, metric_sheets: tuple[str, ...] = METRIC_SHEETS) -> None:
        graph = precedents(workbook)
        wanted = {name.strip() for name in metric_sheets}
        roots = [cell for cell in graph if cell[0].strip() in wanted]
        needed: set[Cell] = set()
        queue = deque(roots)
        while queue:
            current = queue.popleft()
            for source in graph.get(current, ()):
                if source not in needed:
                    needed.add(source)
                    queue.append(source)
        self.needed = needed
        self.formula_cells = len(graph)

    def feeds_metrics(self, sheet: str, row: int, col: int) -> bool:
        return (sheet, row, col) in self.needed

    def affected_metric_count(self, sheet: str, row: int, col: int) -> bool:  # pragma: no cover - convenience alias
        return self.feeds_metrics(sheet, row, col)


def describe(sheet: str, row: int, col: int, dependencies: MetricDependencies | None) -> dict[str, Any]:
    return {"sheet": sheet, "row": row, "col": col, "important": bool(dependencies and dependencies.feeds_metrics(sheet, row, col))}
