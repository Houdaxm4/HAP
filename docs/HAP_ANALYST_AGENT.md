# HAP Analyst agent

The HAP Analyst is a read-only assistant for one analysis at a time. It answers the
analyst's questions by reading the analysis's stored results and citing where each
figure came from. It does not decide anything.

## What it does
- Explains an analysis: status, recommendation, scores and what drove them.
- Finds and explains numbers, flags, discrepancies and validation results.
- Traces a workbook cell back to its source (`get_cell_provenance`).
- Describes pending analyst-judgment items (lease rate, R&D useful life).

## What it never does
- Change workbooks, scores or recommendations, run the pipeline, or approve a review gate.
- Re-score. Scores and the recommendation stay deterministic (`docs/SCORING_SYSTEM.md`).
- Read any other analysis: the toolbox is constructed with one analysis id and tools take no id.

## How it works
- `POST /analysis/{id}/chat` with `{"messages": [{"role": "user", "content": "..."}]}`
  (behind the normal login gate). Returns `reply`, the tools it used, and token counts.
- `backend/agent/runner.py` runs a Claude tool-use loop (default model `claude-sonnet-5-5`,
  effort `medium`, server-side refusal fallback on, at most 10 tool rounds).
- `backend/agent/tools.py` holds seven read-only tools over the analysis's `.json`, `.md`,
  `.txt` and `.csv` artifacts, with size caps and path-safe artifact names.
- `backend/agent/prompts.py` holds the rules: evidence first and cited, no invented numbers,
  decisions go to the analyst, tool output is data and never instructions.
- The web UI has an **Ask HAP** tab on each analysis (`frontend/components/AnalystChat.tsx`).

## Setup
1. `pip install -r requirements.txt` (adds `anthropic`).
2. Set `ANTHROPIC_API_KEY` in the backend environment (never in the repo).
3. Optional: `HAP_AGENT_MODEL`, `HAP_AGENT_EFFORT`, `HAP_AGENT_FALLBACKS`, `HAP_AGENT_MAX_ITERATIONS`.

## Privacy
Chatting sends excerpts of the analysis's stored results (filing data, model outputs) to the
Anthropic API. Do not enable it for analyses that must not leave your environment.

## Ideas for next steps
- Stream answers (Server-Sent Events) and show tool activity live.
- Draft-only suggestions the analyst can accept (still no automatic writes).
- A batch "morning brief" across analyses that need review.
- Evaluation set of analyst questions with expected cited answers.

## Feedback and budget (added)
- **Feedback store** (`services/feedback_service.py`, `storage/feedback/feedback.jsonl`): every review decision
  (lease rate, R&D useful life) is logged automatically with what the agent proposed, what you chose and why.
  Chat answers have Helpful / Not right buttons with an optional reason. API: `POST /analysis/{id}/feedback`,
  `GET /analysis/{id}/feedback`, `GET /feedback/summary` (approval vs correction rates per decision type).
  Nothing learns from it yet: the next step turns repeated corrections into lessons you approve.
- **Budget guard** (`services/budget_service.py`, `storage/usage/`): every Claude call is recorded with an
  estimated cost; the agent refuses to call the API once the month reaches `HAP_MONTHLY_BUDGET_USD` (default $20).
  `GET /budget` shows spend; the chat shows it and warns at 80%.

## Free-first chat (added)
`POST /analysis/{id}/chat` now routes each question in this order (`agent/service.py`):
1. **Built-in answer (free)**: `agent/free_answers.py` answers common questions straight from the stored
   results with fixed code: summary and what needs attention, recommendation and score drivers, validation and
   discrepancies, pending reviews (lease rate, R&D life), risks and opportunities, files, pipeline log, and
   "where does `Sheet!B5` come from". Hypotheticals, comparisons, forecasts and opinion questions are
   deliberately not matched. When the final report and the analysis engine disagree, both are shown with a warning.
2. **Remembered answer (free)**: a previous paid answer to the same question, reused only while the analysis is
   unchanged (any new output or review decision retires it; 30-day expiry; a thumbs-down forgets it).
3. **Ask Claude (paid, only on request)**: `mode: "claude"`. In the default `auto` mode the API never makes a paid
   call; it returns `needs_claude: true` with an estimated cost and the UI shows an **Ask Claude** button.
Each reply says where it came from (`source`: built_in, cache, claude, none).

## Lessons library (added)
HAP learns from your corrections, but only with your approval (`services/lessons_service.py`, page: **Lessons**).
1. Every review decision and chat rating is stored with your reason (feedback store).
2. **Look for new lessons** finds repeated patterns (at least 3 similar cases, `HAP_LESSON_MIN_SUPPORT`), for example
   "the analyst corrected the lease rate in 3 of 4 cases, typically higher", and writes a *proposed* lesson in plain
   English with the evidence. This step is free: no AI call.
3. You approve (optionally editing the wording), reject, or later retire it. Rejected patterns are not proposed again.
4. Approved lessons are **advisory only**: they are added to the analyst chat's instructions and shown next to the
   related review decision. They never change scores, rules or workbook numbers; a lesson that implies a rule change
   remains a note for a developer. Approving or retiring a lesson retires remembered chat answers so stale answers
   are not served.

API: `GET /lessons`, `POST /lessons/propose`, `POST /lessons/{id}/approve|reject|retire`.

## Checkpointed runs, outside research and regression checks

- **Run with checkpoints** (`Agent Run` tab; `POST /analysis/{id}/agent/run`): runs the pipeline, pauses where a human decision is needed (pipeline failure, lease-rate / R&D review gates), then builds a dossier: headline recommendation (final report; engine disagreement flagged), validation flags, labeled outside evidence, and optionally a labeled "my take" (strong model, counts toward the monthly cap). Your approve / needs-changes / stop answer at each checkpoint is stored as feedback and feeds lessons. The agent never approves a gate or changes a score.
- **Outside research** (`backend/research/`): SEC filings, free delayed prices (Yahoo chart endpoint, unofficial), news (Google News RSS) and the company's own IR domain. Allow-listed, https only, every result labeled with source, date and reliability, logged to `research_evidence.jsonl`. `HAP_RESEARCH_ENABLED=0` turns it off; `HAP_RESEARCH_EXTRA_DOMAINS` adds IR domains.
- **Regression** (`python -m regression check`): replays saved analyses offline and compares with approved baselines.

## Flags, fill-from-SEC and report opinions (New Company)

- **Blank cells** in the supplied workbook are filled from SEC (10-K annual, 10-Q latest quarter), shaded, with the source in the cell comment. A blank no source can fill is flagged red only if a reported metric depends on it (`services/formula_dependencies.py` follows the workbook's own formulas); unused blanks are ignored. Supplied values are never overwritten; material differences are flagged.
- **Last-quarter statements** are required only for New Company when the latest period is Q1-Q3 (`quarterly_analysis_required`); never for Annual Update.
- **Word report** (always produced): Flags first (needs attention / filled / corrected / agent decisions / notes, with an authorization status), then the analysis, then the fundamentals verdict, then the cheap/not-cheap discussion only when fundamentals are strong.
- **Analyst opinion** (`POST /analysis/{id}/report/opinion`, Agent Run tab): Claude writes the fundamentals opinion and, if strong, the valuation opinion from online research and the workbook. It is paid (counts toward the cap), labeled as opinion, never changes HAP's scores, and is inserted in place of the "pending" markers. It needs `ANTHROPIC_API_KEY`.

## Yahoo Finance fallback for blank statement cells

When a statement cell is blank in the supplied workbook **and SEC has nothing for that year**, HAP can use Yahoo Finance's free annual fundamentals (`research/yahoo_fundamentals.py`). It is a last resort: SEC always comes first, supplied values are never overwritten, and every Yahoo value is shaded, labelled "indicative", and listed in the Word report's Flags (with a note to verify against the filing). It is enabled only for lines that agreed with real workbook values (revenue, net income, pre-tax income, income tax, total liabilities, debt, EPS, cash, equity, diluted shares; operating cash flow, investing, financing and total assets were checked against SEC) and never for operating income, gross profit or capex. A year is used only if Yahoo's revenue or net income for that period matches the workbook's. Yahoo returns about the last four fiscal years. Turn it off with `HAP_YAHOO_FALLBACK=0`. The endpoint is unofficial: a company deployment may want a licensed data source.
