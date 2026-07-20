# Batch Review Log

Sprint 5.1 — Validation Campaign  
One row (or section) per company in the batch. Keep this file updated as reviews complete.

Campaign name:  
Batch output directory:  
Harness run date:  
Review lead:

---

## Batch snapshot (from harness)

| Metric | Count |
|--------|------:|
| Total companies | |
| Successful analyses | |
| Failed analyses | |
| Average runtime | |
| Companies missing data (harness) | |
| Incomplete module coverage (harness) | |

Hard failures (from `validation_failures.log`):

| Company | Ticker | Failure reason |
|---------|--------|----------------|
| | | |

---

## Review tracker

| Company | Ticker | Industry | BQ | IA | Rec | ER | Conf. | Missing data? | Failed modules? | Anomalies* | Verdict | Reviewer | Notes |
|---------|--------|----------|----|----|-----|----|-------|---------------|-----------------|------------|---------|----------|-------|
| | | | | | | | | | | | | | |

\*Anomaly codes: `S` suspicious scores · `E` empty outputs · `C` contradictory recommendations · `M` missing financial series · `F` failed modules · `-` none

Link each completed row to its company review file under `reviews/`.

---

## Anomaly tally

| Anomaly type | Count | Example tickers |
|--------------|------:|-----------------|
| Suspicious scores | | |
| Empty outputs | | |
| Contradictory recommendations | | |
| Missing financial series | | |
| Failed module executions | | |

---

## Verdict tally

| Verdict | Count |
|---------|------:|
| Accept | |
| Accept with caveats | |
| Reject for re-run | |
| Escalate | |
| Deferred | |

---

## Patterns observed

*(Recurring data issues, recurring engine behaviors, industries that struggle, etc.)*



---

## Escalations (tickets only — no code changes in this campaign)

| ID | Company | Topic | Suspected area (data / coverage / methodology question) |
|----|---------|-------|---------------------------------------------------------|
| | | | |

---

## Campaign close-out

- [ ] All successful runs reviewed or explicitly deferred
- [ ] All hard failures logged
- [ ] Anomaly tally complete
- [ ] Escalations listed
- [ ] Engine left unchanged
- [ ] Close-out memo written (date / author):
