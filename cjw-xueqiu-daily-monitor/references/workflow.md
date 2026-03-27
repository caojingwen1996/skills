# Detailed Workflow

This document is the authoritative operating procedure for the Xueqiu daily monitor skill.

## Step 1: Pre-check

### 1.1 Load `EXTEND.md` ⛔ BLOCKING

Before any capture preparation:

1. read `EXTEND.md`
2. summarize the current configuration for the user
3. explicitly ask whether any accounts, URLs, notes, manual rules, date preferences, or output preferences need to be supplemented or corrected

The summary must include:

- enabled accounts
- disabled accounts
- each account URL
- notes when present
- start rules
- target date rule
- output preferences and output expectations

If the user wants changes, update `EXTEND.md` first and restart the pre-check.

Do not continue until the user confirms the configuration is complete.

### 1.2 Validate task readiness

Confirm:

- there is at least one enabled account
- every enabled account has a valid homepage URL
- the target date is explicit
- the Chrome profile is available, or the operator is ready for manual login

If configuration is incomplete:

- stop the run
- ask the operator to fix `EXTEND.md` or the local runtime setup

## Step 2: Choose date and run mode

The workflow always operates on one explicit target date.

Classify the run as:

- `new-day start`: no state file exists for the account and date
- `same-day rerun`: a state file already exists for the account and date

Use the state file as the source of truth. Do not guess from memory or file names alone.

Related files:

- state and logs: `scripts/task_store.py`
- raw capture: `scripts/content_task.py`

## Step 3: Capture one pass

Each manual start performs one pass only.

For each enabled account:

1. open the homepage
2. scan currently visible posts
3. keep only posts that belong to the target date
4. compare with the processed-items set
5. open only newly discovered items
6. extract content and save raw `.txt` files
7. update state, counters, and logs

Required behavior:

- do not capture non-target-date items
- do not overwrite existing raw files
- do not enter automatic loops
- do not invent scheduling behavior

Command reference: [usage.md](usage.md#capture-commands)

## Step 4: Same-day rerun

Same-day reruns are incremental.

When state already exists for the same account and date:

1. load the existing state
2. reuse the processed-items set
3. scan the homepage again
4. keep only posts not already processed
5. save only the newly discovered content
6. append logs and state events

Never:

- clear the same-day state
- rewrite old raw files
- treat a rerun like a new task

## Step 5: Generate summaries

Run summary generation only after the operator considers the day's raw capture complete enough.

Summary generation must:

- read saved raw `.txt` files only
- preserve intermediate artifacts
- write final Markdown summaries separately

Current generator:

- `scripts/daily_summary.py`

Required output split:

- intermediate artifacts: `processing/{yyyymmdd}/`
- final Markdown results: `summaries/{yyyymmdd}/`

Related references:

- [summary-format.md](summary-format.md)
- [output-layout.md](output-layout.md)

## Step 6: Finalize

At the end of a run, report:

- target date
- enabled accounts covered
- whether this was a new run or rerun
- output root
- summary directory
- processing directory
- unresolved failures, if any

The workflow is considered complete for the date when:

- each required account has completed at least one pass
- same-day reruns are no longer needed
- raw data is stable enough for summary generation
- final summaries have been written
- important failures have been recorded for follow-up

## Stop Conditions

Stop and tell the user before continuing when any of the following happens:

- login expired
- page abnormal
- page structure changed
- extracted content is empty
- save failed
- risk-control prompt appeared

Detailed failure handling: [error-policy.md](error-policy.md)
