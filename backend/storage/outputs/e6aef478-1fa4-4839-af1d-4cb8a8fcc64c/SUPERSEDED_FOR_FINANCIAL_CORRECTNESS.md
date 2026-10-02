# Superseded for financial correctness

This note does not change the original certification record.

Run `e6aef478-1fa4-4839-af1d-4cb8a8fcc64c` remains historical evidence. Its original report, `QUARTERLY_FILL_IN_PLACE_CERTIFICATION.md`, and `quarterly_fill_in_place_certification.json` are unchanged. That run recorded status READY_FOR_PRODUCTION against commit `19f3e3e0bb707e543db321e007660a7c8f757acc`.

A later review found that the SEC period selector used by that run treated prior-year comparative facts as the current quarter. Companyfacts tags those comparative columns with the filing's `fy=2026` and `fp=Q2`. The run therefore wrote prior-year amounts into current-quarter cells, including revenue 300.596 (2025-04-01 to 2025-06-30) and operating income 205.427 (2025-04-01 to 2025-06-30). The current-quarter facts in the same filing are revenue 260.17 and operating income 139.239 for 2026-04-01 to 2026-06-30.

The corrected fill-in-place certification is `b636e989-4173-4c5d-b67e-5d994d107374`, recorded in commit `275c82625af3aaf14d5411730fff1e99f6d918fd`. Use that run for financial correctness. Keep this directory as the audit history of the earlier result.
