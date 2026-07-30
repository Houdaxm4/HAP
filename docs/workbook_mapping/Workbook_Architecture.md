# Workbook Classification Architecture (M1.5)

## Purpose

M1.5 introduces a **permanent metadata layer** for Mode A Excel work:

**`Workbook_Manifest.json` is the single source of truth.**

From M2 onward, mapping, fill, validation, and reporting modules must **consume the manifest**.
They must **not** re-inspect the Industrial Template to rediscover sheet roles, write policy, or cell classes
when that information already exists in the manifest.

## Package layout

```text
backend/workbook_mapping/
  models.py              # Pydantic schema (CellClass, SheetClassification, WorkbookManifest, …)
  sheet_policies.py      # Structure-level role / write_policy / fill_priority per sheet name
  scanner.py             # WorkbookScanner — raw openpyxl inventory
  classifier.py          # CellClassifier / WorkbookClassifier
  statistics.py          # StatisticsGenerator
  manifest_builder.py    # ManifestBuilder — orchestration
  docs_writer.py         # Markdown renderers
  __main__.py            # CLI entry: python -m workbook_mapping
```

## Pipeline

```text
Industrial Template .xlsx
        │
        ▼
  WorkbookScanner          (used ranges, formulas, objects, named ranges, protection)
        │
        ▼
  WorkbookClassifier       (sheet policies + per-cell CellClass)
        │
        ▼
  StatisticsGenerator
        │
        ▼
  ManifestBuilder ──────► Workbook_Manifest.json
        │
        ├──► Workbook_Classification.md
        ├──► Workbook_Statistics.md
        └──► Workbook_Architecture.md (this file)
```

## Extensibility

- **New template versions:** re-run the CLI; compare `suite_fingerprints` + sheet hashes against prior manifests.
- **New sheets:** add an entry to `sheet_policies.py` (defaults to Hybrid / Read-only / Never if missing).
- **Richer cell rules:** extend `CellClassifier._classify_cell` without changing consumers of the manifest schema.
- **Schema versioning:** `schema_version` on the manifest; bump when fields change incompatibly.

## Consumer contract (M2+)

1. Load `docs/workbook_mapping/Workbook_Manifest.json` (or a versioned copy under `backend/workbook_mapping/manifests/`).
2. Only emit write intents for cells with `writable=true` and classification `Writable Input`.
3. Refuse writes to Formula / Output / Read-only / Historical Data / Helper / Protected / Reserved / Empty.
4. Respect `fill_priority` (`P0` annual first; `P1` LQ later; `Never` excluded).
5. Use `dependency_edges` for impact analysis — do not re-parse all formulas unless validating the manifest itself.

## What M1.5 does *not* do

- No CFM → cell mapping (M2)
- No write intents engine (M3)
- No Excel mutation / fill (M4)
- No Word / email
