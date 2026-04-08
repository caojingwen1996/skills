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

- [enabled] name: 买股票的老木匠
  url: https://xueqiu.com/u/3058599833
  note: 用户追加，待后续补充画像

- [enabled] name: 冰冰小美
  url: https://xueqiu.com/u/7143769715eqiu.com/u/3058599833
  note: 待补充

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

If the operator uses the default confirmation option `3. 不需要修改，按今天抓取`, the workflow must resolve `today` to the current absolute date before capture starts.

Typical usage:

- default: collect today's posts
- rerun: collect the same date again and only add new items
- historical capture: manually specify an earlier date when needed

## Output Preferences

The current repo-local convention is:

- preferred output root: `/Users/cjw/dev/projects/skills_output`
- preferred Chrome profile: `./scripts/.xueqiu-chrome-profile`
- preferred automation Chrome startup script: `./scripts/start_automation_chrome.sh`
- preferred automation Chrome CDP port: `9333`

These are operator defaults for this repository. Capture and summary commands must point to the same output root for a given task date.

## Output Expectations

Within the fixed output root `/Users/cjw/dev/projects/skills_output`:

- per-author raw capture files, `state.json`, `task.log`, intermediate analysis, and `summary.md` live under `{yyyymmdd}/{author}/`
- per-author intermediate artifacts live under `{yyyymmdd}/{author}/processing/`
- the per-author final Markdown summary lives at `{yyyymmdd}/{author}/summary.md`

Full directory rules: [references/output-layout.md](references/output-layout.md)

## Summary Structure Reminder

Final summaries must be Markdown and use these sections:

1. `总观点`
2. `分观点`

`分观点` default rules:

- 3-7 numbered points
- one clear judgment per point
- add `证据：...` only when the point would otherwise be ambiguous

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

Then ask the user to choose one of these pre-start outcomes before capture begins:

1. 需要补充或更正配置
2. 不需要修改，按指定日期抓取 `YYYY-MM-DD`
3. 不需要修改，按今天抓取

If option `3` is chosen, convert `today` to the current absolute date before continuing.
