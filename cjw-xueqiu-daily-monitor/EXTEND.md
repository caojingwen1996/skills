# Xueqiu Daily Monitor Extend

## Purpose

This file is the manual configuration layer for the Xueqiu daily monitor workflow.

Current scope:

- maintain account homepage URLs
- control which accounts are enabled
- describe manual-start operating rules

Current non-goals:

- no automatic scheduling
- no secret storage
- no runtime state
- no summary output

## Account List

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

- `name` is the human-readable display name
- `url` must be the Xueqiu account homepage URL
- only `enabled` accounts are included in the daily workflow
- `note` is optional and only for operator reference

## Manual Start Rule

The workflow is manual-start only.

Current rule set:

1. the operator decides when to start the day's capture
2. one manual start performs one capture pass per enabled account
3. if the operator starts the task again later on the same day, it is treated as a same-day rerun
4. same-day reruns must reuse existing state and only capture new items

## Target Date Rule

The task date is explicit.

Typical usage:

- default: collect today's posts
- rerun: collect the same date again and only add new items
- historical capture: manually specify an earlier date when needed

## Output Expectations

Raw capture outputs live under:

```text
output/
```

Intermediate processing outputs live under:

```text
output/processing/{yyyymmdd}/
```

Final Markdown summaries live under:

```text
output/summaries/{yyyymmdd}/
```

## Summary Structure Reminder

Final summaries should be Markdown and use these three sections:

1. `核心内容`
2. `背景语境`
3. `Spec相关`

`Spec相关` should be split into:

- `明确相关`
- `候选相关`
