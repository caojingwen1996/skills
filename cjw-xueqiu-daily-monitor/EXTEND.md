# Xueqiu Daily Monitor Extend

This file is the manual configuration layer for the Xueqiu daily monitor skill.

Current scripts only parse the account list format. The other sections are operator preferences and workflow guidance that must be reviewed before each task starts.

## Accounts

Maintain accounts in the following format.

```md
## Accounts

- [enabled] name: 冰冰小美
  url: https://xueqiu.com/u/7143769715

- [enabled] name: 买股票的老木匠
  url: https://xueqiu.com/u/3058599833
```

Rules:

- `name` is the human-readable account name
- `url` must be the Xueqiu homepage URL
- only `enabled` accounts are included in the daily workflow
- `note` is optional and for operator context only

## Weibo Accounts

Maintain Weibo homepage accounts in the following format.

```md
## Weibo Accounts

- [enabled] name: 美股C姐
  url: https://weibo.com/u/2826115500

- [enabled] name: 墅姐
  url: https://weibo.com/u/7796318711
```

Rules:

- `name` is the human-readable account name
- `url` must be the Weibo homepage URL in `https://weibo.com/u/...` format
- only `enabled` accounts are included in the daily workflow
- `note` is optional and for operator context only

## WeChat Article Links

微信公众号抓取支持两种入口：直接文章链接，以及可访问的公众号主页/历史消息页面 `--history-url`。
When the operator provides WeChat article links, keep them as direct article URLs:

```md
## WeChat Article Links

- [enabled] name: 样例公众号
  url: https://mp.weixin.qq.com/s/example
```

Rules:

- `url` must be a `https://mp.weixin.qq.com/s...` article URL
- multiple article links may be provided in a plain text file, one URL per line
- use `scripts/extract_wechat_articles.mjs` before `scripts/content_task.py`
- extracted JSON must keep the fields used by the raw-file writer: `title`, `published_at`, `url`, `author_name`, and `content`

For a history page, pass the page URL as `--history-url`. The page must already be accessible and contain discoverable `mp.weixin.qq.com/s...` article links.

## Start Rules

The workflow is manual-start only.

Current rule set:

1. the operator decides when to start the day's capture
2. one manual start performs one capture pass per enabled account
3. a later start on the same day is treated as a same-day rerun
4. same-day reruns must reuse existing state and only add newly discovered items

## Target Date Rule

The task date must always be explicit.

If the operator uses the default confirmation option `3. 不需要修改，按默认日期抓取`, the workflow must resolve the target date from the local start time before capture starts.

Default target-date rule:

- if the task starts at or after `00:00` and before `08:00` local time, resolve the target date to the previous calendar date
- otherwise, resolve the target date to the current calendar date

Typical usage:

- default before 08:00: collect yesterday's posts
- default from 08:00 onward: collect today's posts
- rerun: collect the same date again and only add new items
- historical capture: manually specify an earlier date when needed

## Output Preferences

The current repo-local convention is:

- preferred output root: `E:/caojingwen/obsidian/source/xueqiu_exports/cjw-xueqiu-daily-monitor`
- preferred Chrome profile: `./scripts/.xueqiu-chrome-profile`
- preferred automation Chrome startup script: `./scripts/start_automation_chrome.sh`
- preferred automation Chrome CDP port: `9333`

These are operator defaults for this repository. Capture and summary commands must point to the same output root for a given task date.

## Output Expectations

Within the configured output root declared by `preferred output root`:

- per-author raw capture Markdown files, `state.json`, `task.log`, intermediate analysis, and `summary.md` live under `{yyyymmdd}/{author}/`
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
3. 不需要修改，按默认日期抓取

If option `3` is chosen, resolve the absolute target date with the default target-date rule before continuing.
