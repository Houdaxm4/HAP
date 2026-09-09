"""Workbook Mapping / Classification package (Mode A).

M1.5 produces the Workbook Manifest — the single source of truth for future
Excel operations. Downstream milestones must consume the manifest rather than
re-inspecting Industrial Template workbooks for structure.
"""

from workbook_mapping.engine import (
    IntentDecision,
    WriteIntent,
    WriteIntentReport,
    WriteIntentValidationError,
    load_mapping_specification,
    map_model_to_write_intents,
    validate_write_intents,
)
from workbook_mapping.manifest_builder import build_manifest_from_path
from workbook_mapping.models import CellClass, SheetRole, WritePolicy

__all__ = [
    "IntentDecision",
    "WriteIntent",
    "WriteIntentReport",
    "WriteIntentValidationError",
    "build_manifest_from_path",
    "load_mapping_specification",
    "map_model_to_write_intents",
    "validate_write_intents",
    "CellClass",
    "SheetRole",
    "WritePolicy",
]
