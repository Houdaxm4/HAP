"""Workbook Mapping / Classification package (Mode A).

M1.5 produces the Workbook Manifest — the single source of truth for future
Excel operations. Downstream milestones must consume the manifest rather than
re-inspecting Industrial Template workbooks for structure.
"""

from workbook_mapping.manifest_builder import build_manifest_from_path
from workbook_mapping.models import CellClass, SheetRole, WritePolicy

__all__ = [
    "build_manifest_from_path",
    "CellClass",
    "SheetRole",
    "WritePolicy",
]
