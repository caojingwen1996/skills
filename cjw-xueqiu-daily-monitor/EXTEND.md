# Xueqiu Daily Monitor Extend

This file is the manual configuration layer for the Xueqiu daily monitor skill.

Current scripts only parse the account list format. The other sections are operator preferences and workflow guidance that must be reviewed before each task starts.

## Accounts

Maintain accounts in the following format.

```md
## Accounts

- [enabled] name: 闵行一霸
  url: https://xueqiu.com/u/9838764557
  note: 泡泡玛特、美团、港股成长股

- [disabled] name: 示例博主
  url: https://xueqiu.com/u/0000000000
  note: 暂不纳入日常跟踪
```

Rules:

- `name` is the human-readable account name
- `url` must be the Xueqiu homepage URL
- only `enabled` accounts are included in the daily workflow
- `note` is optional and for operator context only

## Start Rules

The workflow is manual-start only.

Current rule set:

1. the operator decides when to start the day's capture
2. one manual start performs one capture pass per enabled account
3. a later start on the same day is treated as a same-day rerun
4. same-day reruns must reuse existing state and only add newly discovered items

## Target Date Rule

The task date must always be explicit.

Typical usage:

- default: collect today's posts
- rerun: collect the same date again and only add new items
- historical capture: manually specify an earlier date when needed

## Output Preferences

The current repo-local convention is:

- preferred output root: `./scripts/output`
- preferred Chrome profile: `./scripts/.xueqiu-chrome-profile`

These are operator defaults for this repository. Capture and summary commands must point to the same output root for a given task date.

## Output Expectations

Within the selected output root:

- raw capture files live at the root layer
- intermediate processing files live under `processing/{yyyymmdd}/`
- final Markdown summaries live under `summaries/{yyyymmdd}/`

Full directory rules: [references/output-layout.md](references/output-layout.md)

## Summary Structure Reminder

Final summaries must be Markdown and use these sections:

1. `核心内容`
2. `背景语境`
3. `Spec相关`

`Spec相关` must be split into:

- `明确相关`
- `候选相关`

Full summary rules: [references/summary-format.md](references/summary-format.md)

## Pre-Start Confirmation

Before any capture task starts, the operator must display and confirm:

- enabled accounts
- disabled accounts
- account URLs
- account notes when present
- manual-start rules
- target-date rule
- output preferences and output expectations

Then ask the user whether anything in this file needs to be supplemented or corrected before capture begins.
