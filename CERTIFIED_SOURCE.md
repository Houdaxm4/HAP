# Certified HAP source revision

This commit captures the application source that produced the Annual Update, Quarterly Update, and New Company `READY_FOR_PRODUCTION` certifications.

- Branch: `cursor/new-company-analysis-pipeline-9b4a`
- Parent at the time of certification: `896a3b219686b1a8c02a029e9429bad655145f8f`
- Certified working-tree source SHA-256: `4fb09ec24494678be3a328ed3db2cd66a05c0d9c78a46b346cfd1887d0d9b0dd`

The original Windows Excel COM certification ran on the uncommitted working tree identified by that hash. This commit is source-equivalent for application code, tests, certification scripts, TLS config, and the frozen production-certification markdown reports. It is not a re-execution of those Windows COM runs.

The recorded working-tree hash also included local `backend/.venv` site-packages and gitignored `backend/_*.py` / `backend/_*.json` scratch files. Those are deliberately excluded from this commit.

Workbook binaries, Word reports, SEC caches, and run outputs are not in Git. They are preserved in the local certification archive under `backend/storage/certifications/`.
