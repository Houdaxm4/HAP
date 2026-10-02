"""Excel formula helpers: refs, column shifts, self-reference checks."""

from __future__ import annotations

import re
from typing import Any

from openpyxl.utils import column_index_from_string, get_column_letter

_CELL_TOKEN = re.compile(
    r"(?:(?:'([^']+)'|([A-Za-z0-9_. ]+))!)?(\$?)([A-Z]{1,3})(\$?)(\d+)",
    re.IGNORECASE,
)


def is_formula(value: Any) -> bool:
    if value is None:
        return False
    if hasattr(value, "text"):
        text = str(value.text)
        return text.startswith("=")
    return isinstance(value, str) and value.startswith("=")


def formula_text(value: Any) -> str | None:
    if not is_formula(value):
        return None
    if hasattr(value, "text"):
        return str(value.text)
    return str(value)


def parse_cell_refs(formula: str) -> list[dict[str, Any]]:
    """Return referenced cells (sheet optional, row, col, token span)."""
    refs: list[dict[str, Any]] = []
    if not formula:
        return refs
    for match in _CELL_TOKEN.finditer(formula):
        sheet = match.group(1) or match.group(2)
        col_abs = bool(match.group(3))
        col_letters = match.group(4).upper()
        row_abs = bool(match.group(5))
        row = int(match.group(6))
        refs.append(
            {
                "sheet": sheet.strip() if sheet else None,
                "col": column_index_from_string(col_letters),
                "row": row,
                "col_abs": col_abs,
                "row_abs": row_abs,
                "start": match.start(),
                "end": match.end(),
                "text": match.group(0),
            }
        )
    return refs


def formula_references_column(formula: str, col: int, *, sheet: str | None = None) -> bool:
    """True if the formula references ``col`` as a relative/absolute A1 column.

    Used to distinguish year-series formulas (they mention their own FY column)
    from helper formulas that merely occupy a cell in the FY band.
    """
    text = formula_text(formula) or str(formula or "")
    for ref in parse_cell_refs(text):
        if ref["col"] != col:
            continue
        if sheet and ref["sheet"] and ref["sheet"].strip("'") != sheet.strip("'"):
            continue
        return True
    return False


def shift_formula_columns(formula: str, from_col: int, to_col: int) -> str:
    """Shift relative column letters by (to_col - from_col). Absolute $A stay."""
    text = formula_text(formula) or str(formula or "")
    delta = to_col - from_col
    if delta == 0 or not text.startswith("="):
        return text

    pieces: list[str] = []
    last = 0
    for ref in parse_cell_refs(text):
        pieces.append(text[last : ref["start"]])
        if ref["col_abs"]:
            pieces.append(ref["text"])
        else:
            new_col = max(1, ref["col"] + delta)
            prefix = ""
            if ref["sheet"]:
                name = ref["sheet"]
                if " " in name or not name.replace("_", "").isalnum():
                    prefix = f"'{name}'!"
                else:
                    prefix = f"{name}!"
            row_bit = f"${ref['row']}" if ref["row_abs"] else str(ref["row"])
            pieces.append(f"{prefix}{get_column_letter(new_col)}{row_bit}")
        last = ref["end"]
    pieces.append(text[last:])
    return "".join(pieces)


def formula_would_self_reference(formula: str, dest_col: int, dest_row: int, *, sheet: str | None = None) -> bool:
    text = formula_text(formula) or str(formula or "")
    for ref in parse_cell_refs(text):
        if ref["row"] == dest_row and ref["col"] == dest_col:
            if ref["sheet"] is None or (sheet and ref["sheet"].strip("'") == sheet.strip("'")):
                return True
    return False
