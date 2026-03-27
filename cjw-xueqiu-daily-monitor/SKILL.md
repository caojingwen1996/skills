---
name: cjw-xueqiu-daily-monitor
description: Use when the user wants to manually collect same-day posts from one or more specified Xueqiu account homepages, rerun the same date without duplicate capture, or generate end-of-day Markdown summaries from saved raw files.
---

# Xueqiu Daily Monitor

Manual same-day Xueqiu monitoring workflow for configured account homepages.

Use this skill to load account configuration from `EXTEND.md`, run one manual capture pass per start, reuse state for same-day reruns, and generate Markdown summaries from saved raw files.

## Workflow

```text
- [ ] Step 1: Pre-check `EXTEND.md` and confirm task inputs
- [ ] Step 2: Confirm target date and run mode
- [ ] Step 3: Run one capture pass for each enabled account
- [ ] Step 4: Reuse same-day state for reruns
- [ ] Step 5: Generate Markdown summaries from saved raw files
- [ ] Step 6: Finalize and report output locations
```

## Step 1: Pre-check

### 1.1 Load `EXTEND.md` ⛔ BLOCKING

Before any capture preparation:

- read `EXTEND.md`
- list the current enabled accounts, disabled accounts, URLs, notes, manual rules, date rule, and output preferences
- ask whether the user wants to supplement or correct the configuration

Do not continue until the user explicitly confirms no additions are needed or the `EXTEND.md` update is complete.

Full procedure: [references/workflow.md](references/workflow.md#step-1-pre-check)

### 1.2 Validate task inputs

Confirm:

- at least one account is `enabled`
- each enabled account has a valid Xueqiu homepage URL
- the target date is explicit
- the Chrome persistent profile is available or the operator is ready to log in manually

If configuration or environment is incomplete, stop and ask the user to fix it first.

## Step 2: Confirm run mode

Determine whether this start is:

- a first pass for the date, or
- a same-day rerun that must reuse existing state

Use `scripts/task_store.py` state files as the source of truth for rerun detection.

Full procedure: [references/workflow.md](references/workflow.md#step-2-choose-date-and-run-mode)

## Step 3: Capture

Run exactly one capture pass per manual start.

- use `scripts/content_task.py` for single-account, single-date capture
- only process posts for the target date
- save raw `.txt` files, logs, and state
- do not start automatic loops or hourly scans

Command details: [references/usage.md](references/usage.md#capture-commands)

## Step 4: Same-day reruns

Same-day reruns are incremental only.

- read the existing state
- keep processed items as the deduplication source of truth
- save only newly discovered posts
- do not overwrite existing raw files

Full procedure: [references/workflow.md](references/workflow.md#step-4-same-day-rerun)

## Step 5: Summary generation

After capture is considered complete for the day:

- run `scripts/daily_summary.py`
- preserve intermediate analysis files
- write final Markdown results separately from intermediate files

Summary format: [references/summary-format.md](references/summary-format.md)

## Step 6: Finalize

Report:

- target date
- number of processed authors
- output root
- summary directory
- processing directory
- any failures that still require human follow-up

## Output Directory

All outputs are organized under the selected output root. Repo-local examples in this skill use `{baseDir}/scripts/output`.

```text
{output-root}/
├── {author}_{yyyymmdd}.log
├── {author}_{yyyymmdd}.state.json
├── {author}_{yyyymmdd}/
├── processing/{yyyymmdd}/
└── summaries/{yyyymmdd}/
```

Detailed rules: [references/output-layout.md](references/output-layout.md)

## Do Not

- Do not auto-start capture
- Do not assume scheduling exists
- Do not treat same-day reruns as fresh tasks
- Do not mix intermediate files into `summaries/{yyyymmdd}/`
- Do not claim `spec` matching exists beyond the current summary heuristics
- Do not silently continue through login, page, save, or risk-control failures

## References

| File | Purpose |
|------|---------|
| [EXTEND.md](EXTEND.md) | Manual account configuration and start-of-task confirmation source |
| [references/workflow.md](references/workflow.md) | Detailed operating procedure |
| [references/usage.md](references/usage.md) | Script entrypoints and exact CLI usage |
| [references/output-layout.md](references/output-layout.md) | Output root and directory-layer rules |
| [references/summary-format.md](references/summary-format.md) | Required Markdown summary structure |
| [references/error-policy.md](references/error-policy.md) | Failure handling and stop conditions |
| [references/file-layout.md](references/file-layout.md) | Raw file naming and per-file content format |
| [scripts/content_task.py](scripts/content_task.py) | Single-account capture |
| [scripts/task_store.py](scripts/task_store.py) | State and deduplication utility |
| [scripts/daily_summary.py](scripts/daily_summary.py) | End-of-day summary generator |
