# Workbook Mapping Docs (Mode A)

| File | Description |
|------|-------------|
| [`M1_RELEASE_GATE_REPORT.md`](M1_RELEASE_GATE_REPORT.md) | M1 release gate (2026-07-27) |
| [`INDUSTRIAL_TEMPLATE_INVENTORY.md`](INDUSTRIAL_TEMPLATE_INVENTORY.md) | M1 human inventory |
| [`INDUSTRIAL_TEMPLATE_DEPENDENCY_MAP.md`](INDUSTRIAL_TEMPLATE_DEPENDENCY_MAP.md) | M1 formula dependency graph |
| [`INDUSTRIAL_TEMPLATE_RISK_LOG.md`](INDUSTRIAL_TEMPLATE_RISK_LOG.md) | M1 mapping risks |
| [`Workbook_Manifest.json`](Workbook_Manifest.json) | **M1.5 SSoT** — machine workbook metadata |
| [`Workbook_Classification.md`](Workbook_Classification.md) | M1.5 sheet/cell classification summary |
| [`Workbook_Statistics.md`](Workbook_Statistics.md) | M1.5 statistics |
| [`Workbook_Architecture.md`](Workbook_Architecture.md) | M1.5 engine architecture |
| [`CFM_Workbook_Mapping.json`](CFM_Workbook_Mapping.json) | **M2** explicit CFM↔cell mapping spec |
| [`CFM_Workbook_Mapping.md`](CFM_Workbook_Mapping.md) | M2 human mapping table |
| [`Coverage_Report.md`](Coverage_Report.md) | M2 coverage statistics |
| [`Unmapped_CFM_Metrics.md`](Unmapped_CFM_Metrics.md) | M2 unmapped CFM fields |
| [`Unmapped_Workbook_Cells.md`](Unmapped_Workbook_Cells.md) | M2 non-mapped writable cells (still explained) |
| [`industrial_template_v27_inventory.json`](industrial_template_v27_inventory.json) | M1 full inventory (pre-classification) |
| [`industrial_template_v27_fingerprint.json`](industrial_template_v27_fingerprint.json) | M1 regression fingerprints |
| [`suite_structural_diff.json`](suite_structural_diff.json) | M1 cross-ticker structural diff |

**Engines:**
- M1 inventory: `validation_campaign/_inspect_industrial_template.py`
- M1.5 classification: `python -m workbook_mapping` (from `backend/`)
- M2 mapping spec: `python -m workbook_mapping.m2_cli` (from `backend/`)

**Consumer rule (M3+):** Load `Workbook_Manifest.json` + `CFM_Workbook_Mapping.json`. Do not re-inspect Excel for structure or invent fuzzy matches.

**Next:** M3 Mapping Engine (write intents only — still no Excel mutation).
