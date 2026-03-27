---
name: cjw-xueqiu-daily-monitor
description: Use when the user wants to manually collect same-day posts from one or more specified Xueqiu account homepages, rerun the same date without duplicate capture, or generate end-of-day Markdown summaries from the collected raw files.
---

# Xueqiu Daily Monitor

## Overview

This skill is the entrypoint for the current Xueqiu daily monitor workflow.

It should be used to identify the right files, respect the current operating model, and follow the documented workflow instead of improvising a new one.

Detailed workflow rules live in `workflow.md`. `SKILL.md` only defines when to use the skill, which files are authoritative, and what boundaries must be respected.

## When To Use

Use this skill when the user wants any of the following:

- start a same-day Xueqiu capture task manually
- collect posts for one or more configured bloggers
- rerun the same day and only add newly published posts
- generate end-of-day Markdown summaries
- inspect where raw files, intermediate files, and final summaries should live

Do not use this skill for generic browser automation unrelated to Xueqiu monitoring.

## Resources

Resolve the skill root as `{baseDir}` and use these files:

- workflow guide and detailed procedure: `{baseDir}/workflow.md`
- account list: `{baseDir}/EXTEND.md`
- browser helpers: `{baseDir}/scripts/utils.py`
- single-account capture: `{baseDir}/scripts/content_task.py`
- task state and dedupe: `{baseDir}/scripts/task_store.py`
- end-of-day summaries: `{baseDir}/scripts/daily_summary.py`
- file layout reference: `{baseDir}/references/file-layout.md`

If you need detailed step-by-step execution order, read `workflow.md` first and treat it as the authoritative process document.

## Core Rules

1. Manual start only
- Do not auto-start capture.

2. Pre-start operator confirmation
- Before any capture preparation, read `EXTEND.md`, list the current configuration to the user, and ask whether any accounts, links, notes, or related manual rules need to be supplemented or corrected.
- Do not proceed until the user confirms no additions are needed or the `EXTEND.md` update is complete.

3. Account source of truth
- Read enabled blogger homepages from `EXTEND.md`.

4. Same-day scope
- Work is scoped to one explicit target date.

5. Same-day rerun is incremental
- Reuse existing state and do not duplicate processed items.

6. Capture and summary are separate
- Raw capture comes first.
- Final summaries are generated afterwards by `daily_summary.py`.

7. Preserve all layers
- Keep raw outputs, intermediate processing outputs, and final summaries.

All detailed behavior for these rules is defined in `workflow.md`.

## Responsibilities By File

- `EXTEND.md`
  - manual account list
  - enabled or disabled status
  - homepage URLs

- `scripts/content_task.py`
  - single-account, single-date raw capture
  - raw `.txt` output and business logs

- `scripts/task_store.py`
  - same-day task state
  - deduplication source of truth
  - scan and failure bookkeeping

- `scripts/daily_summary.py`
  - read raw outputs for one day
  - preserve intermediate files under `output/processing/{yyyymmdd}/`
  - write final Markdown summaries under `output/summaries/{yyyymmdd}/`

- `workflow.md`
  - authoritative step-by-step operating procedure
  - start, rerun, dedupe, summary, and output layout rules

## Summary Structure

Both per-blogger and combined summaries must use Markdown.

Required sections:

1. `核心内容`
- answer what was said
- keep the main viewpoints, signals, and explicit statements

2. `背景语境`
- answer why those statements appeared that day
- include market context, events, earnings, price moves, short-selling pressure, or thread context when available

3. `Spec相关`
- only output when relevant
- split into:
  - `明确相关`
  - `候选相关`

Current implementation may leave `明确相关` empty until real `spec` matching is added.

## Error Policy

When these situations happen, stop and tell the user clearly before continuing:

- login expired
- page abnormal
- content empty
- save failed
- page structure changed
- risk-control prompt appeared

Do not silently continue through these failures. For exact operator flow, fallback handling, and output expectations, follow `workflow.md`.

## Do Not

- Do not auto-start capture
- Do not assume hourly scheduling exists
- Do not overwrite existing raw files for already processed items
- Do not mix intermediate files into `output/summaries/{yyyymmdd}/`
- Do not claim `spec` matching is implemented beyond the current summary heuristics
- Do not treat same-day reruns as fresh tasks
