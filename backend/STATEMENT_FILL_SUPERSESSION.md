# Supersession — financial-statement filling

The earlier IDCC certification behavior, in which HAP filled or reconstructed financial statements, is obsolete as of this architecture change.

Historical certification files are unchanged. They remain evidence of what that earlier run did. This note does not amend them.

## Obsolete behavior

Prior quarterly IDCC certification cleared Bloomberg income-statement and cash-flow bodies and treated the result as an SEC retrieval task. Gap-fill (`BLOOMBERG_FILL_GAPS`), SEC layout rebuild, and Yahoo basic-template fallback were presentation actions HAP could perform. See, unmodified:

- `backend/QUARTERLY_UPDATE_PRODUCTION_CERTIFICATION.md`
- `backend/storage/certifications/archive-da1765badfd339dfdc3deb2ffc92968ff0012268/quarterly-idcc-q2-cert/`
- `backend/storage/certifications/archive-da1765badfd339dfdc3deb2ffc92968ff0012268/new-company-idcc-edd8ea8f/`

`backend/scripts/certify_quarterly_idcc.py` and `backend/scripts/certify_quarterly_idcc_fill_in_place.py` are not supported execution paths. Both refuse to run, so they cannot clear statement bodies or overwrite the historical outputs.

## Supported behavior

- Supplied annual and quarterly financial statements are validated, not reconstructed.
- Missing required statement data causes `STATEMENT_INCOMPLETE`.
- Material SEC conflicts are flagged and block certification. The supplied value is not overwritten.
- Explicit restatements are flagged for upstream correction.
- SEC remains authoritative for validation and remains available for analytical research and extraction.
